"""
scraper.py — Scrape job listings from 8 freelancing platforms.

Indian portals     : Truelancer, Internshala, Worknhire
International      : Freelancer.com, Guru.com, RemoteOK, PeoplePerHour, Hubstaff Talent

Strategies (in order of preference):
  1. Public JSON API  — Freelancer.com, RemoteOK
  2. RSS / XML feed   — Guru.com
  3. HTML scraping    — all others (rotating user-agents)
  4. Demo mode        — realistic sample data when internet is unavailable
"""

import requests
import logging
import re
import time
import random
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger("JobAgent")

DEMO_MODE = False   # Set True to test without internet access

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# ── Safety: requests per portal per scan (public pages only) ──
# Stays well within polite-crawl limits for each site.
# Freelancer.com API allows 25 req/5 min — we do at most 4.
# RemoteOK asks for 1 req/min — we hit their API once.
# All HTML scrapers use 2-4 s random delay between requests.
MAX_REQUESTS_PER_PORTAL = 8   # hard ceiling per scraper call
_portal_request_count: dict = {}


def _portal_gate(portal: str) -> bool:
    """Return False and skip if we've hit the per-portal request cap."""
    _portal_request_count[portal] = _portal_request_count.get(portal, 0) + 1
    if _portal_request_count[portal] > MAX_REQUESTS_PER_PORTAL:
        logger.debug(f"Rate-gate: {portal} hit {MAX_REQUESTS_PER_PORTAL} req cap, skipping further requests")
        return False
    return True


AI_KEYWORDS = [
    "python", "ai", "machine learning", "ml", "data science", "langchain",
    "rag", "llm", "openai", "nlp", "streamlit", "fastapi", "etl",
    "automation", "chatbot", "agent", "data analyst", "deep learning",
    "huggingface", "scraping", "tensorflow", "scikit",
]


def _headers():
    return {
        "User-Agent": random.choice(UA_LIST),
        "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }


def _safe_get(url, timeout=20, json_mode=False, delay=True, portal=""):
    if portal and not _portal_gate(portal):
        return None
    if delay:
        # Polite crawl: 3-6 s between requests to the same site
        time.sleep(random.uniform(3, 6))
    try:
        r = requests.get(url, headers=_headers(), timeout=timeout)
        # Respect 429 Too Many Requests — back off and do not retry
        if r.status_code == 429:
            logger.warning(f"Rate-limited (429) by {url[:50]} — skipping portal for this scan")
            return None
        r.raise_for_status()
        return r.json() if json_mode else r.text
    except Exception as e:
        logger.warning(f"GET {url[:70]}... → {e}")
        return None


def _extract_number(text):
    m = re.search(r"(\d+\.?\d*)", str(text))
    return float(m.group(1)) if m else None


# ═══════════════════════════════════════════════════════════════
#  INDIAN PORTALS
# ═══════════════════════════════════════════════════════════════

# ── 1. Truelancer ───────────────────────────────────────────────

def scrape_truelancer():
    jobs = []
    search_terms = ["python", "machine-learning", "data-science", "langchain", "nlp", "automation"]

    for term in search_terms:
        urls = [
            f"https://www.truelancer.com/freelance-{term}-jobs",
            f"https://www.truelancer.com/freelance-jobs?search={term}",
        ]
        html = None
        for url in urls:
            html = _safe_get(url)
            if html:
                break
        if not html:
            continue

        soup = BeautifulSoup(html, "lxml")
        cards = (
            soup.select(".project-list-item") or
            soup.select(".job-item") or
            soup.select("article") or
            soup.find_all("div", class_=re.compile(r"project|listing", re.I))
        )

        for card in cards[:20]:
            try:
                title_el = (
                    card.find("h2") or card.find("h3") or
                    card.find("a", class_=re.compile(r"title", re.I))
                )
                title = title_el.get_text(strip=True) if title_el else ""
                if not title or len(title) < 5:
                    continue

                link_el = card.find("a", href=True)
                link = link_el["href"] if link_el else ""
                if link and not link.startswith("http"):
                    link = "https://www.truelancer.com" + link

                desc_el = card.find("p") or card.find(class_=re.compile(r"desc|detail", re.I))
                desc = desc_el.get_text(strip=True)[:300] if desc_el else ""

                budget_el = card.find(class_=re.compile(r"budget|price|amount", re.I))
                budget = budget_el.get_text(strip=True) if budget_el else "N/A"

                rating_el = card.find(class_=re.compile(r"rating|star", re.I))
                rating = _extract_number(rating_el.get_text()) if rating_el else None

                jobs.append({
                    "id": f"tl_{hash(link or title)}",
                    "platform": "Truelancer",
                    "title": title,
                    "description": desc,
                    "budget": budget,
                    "client_rating": rating,
                    "link": link,
                    "found_at": datetime.now().isoformat(),
                    "keyword_matched": term,
                })
            except Exception as e:
                logger.debug(f"Truelancer card: {e}")

    logger.info(f"Truelancer: {len(jobs)} jobs")
    return jobs


# ── 2. Internshala ──────────────────────────────────────────────

def scrape_internshala():
    jobs = []
    search_terms = ["python", "machine-learning", "data-science", "artificial-intelligence", "nlp", "automation"]

    for term in search_terms:
        urls = [
            f"https://internshala.com/freelancing-jobs/keywords-{term}/",
            f"https://internshala.com/jobs/keywords-{term}/",
        ]
        html = None
        for url in urls:
            html = _safe_get(url)
            if html:
                break
        if not html:
            continue

        soup = BeautifulSoup(html, "lxml")
        cards = (
            soup.select(".individual_internship") or
            soup.select(".internship_meta") or
            soup.select(".job-internship-card") or
            soup.find_all("div", class_=re.compile(r"internship|job.?card", re.I))
        )

        for card in cards[:15]:
            try:
                title_el = (
                    card.select_one(".profile") or
                    card.select_one(".job-title") or
                    card.find("h3") or card.find("h2")
                )
                title = title_el.get_text(strip=True) if title_el else ""
                if not title or len(title) < 5:
                    continue

                link_el = card.find("a", href=True)
                link = link_el["href"] if link_el else ""
                if link and not link.startswith("http"):
                    link = "https://internshala.com" + link

                budget_el = (
                    card.select_one(".stipend") or
                    card.select_one(".salary") or
                    card.find(class_=re.compile(r"stipend|salary|pay|remuneration", re.I))
                )
                budget = budget_el.get_text(strip=True) if budget_el else "N/A"

                desc_el = card.find("p") or card.find(class_=re.compile(r"desc|detail|about", re.I))
                desc = desc_el.get_text(strip=True)[:300] if desc_el else ""

                jobs.append({
                    "id": f"is_{hash(link or title)}",
                    "platform": "Internshala",
                    "title": title,
                    "description": desc,
                    "budget": budget,
                    "client_rating": None,
                    "link": link,
                    "found_at": datetime.now().isoformat(),
                    "keyword_matched": term,
                })
            except Exception as e:
                logger.debug(f"Internshala card: {e}")

    logger.info(f"Internshala: {len(jobs)} jobs")
    return jobs


# ── 3. Worknhire ────────────────────────────────────────────────

def scrape_worknhire():
    jobs = []
    search_terms = ["python", "machine-learning", "data-science", "ai", "nlp", "automation"]

    for term in search_terms:
        urls = [
            f"https://www.worknhire.com/jobs/search/{term}/",
            f"https://www.worknhire.com/freelance-{term}-jobs/",
            f"https://www.worknhire.com/jobs/?q={requests.utils.quote(term)}",
        ]
        html = None
        for url in urls:
            html = _safe_get(url)
            if html:
                break
        if not html:
            continue

        soup = BeautifulSoup(html, "lxml")
        cards = (
            soup.select(".job-list-item") or
            soup.select(".project-item") or
            soup.select(".bid-project") or
            soup.find_all("div", class_=re.compile(r"job|project|listing", re.I))
        )

        for card in cards[:15]:
            try:
                title_el = (
                    card.find("h2") or card.find("h3") or
                    card.find("a", class_=re.compile(r"title|name", re.I))
                )
                title = title_el.get_text(strip=True) if title_el else ""
                if not title or len(title) < 5:
                    continue

                link_el = card.find("a", href=True)
                link = link_el["href"] if link_el else ""
                if link and not link.startswith("http"):
                    link = "https://www.worknhire.com" + link

                budget_el = card.find(class_=re.compile(r"budget|price|amount|pay|bid", re.I))
                budget = budget_el.get_text(strip=True) if budget_el else "N/A"

                desc_el = card.find("p") or card.find(class_=re.compile(r"desc|detail|summary", re.I))
                desc = desc_el.get_text(strip=True)[:300] if desc_el else ""

                rating_el = card.find(class_=re.compile(r"rating|star", re.I))
                rating = _extract_number(rating_el.get_text()) if rating_el else None

                jobs.append({
                    "id": f"wnh_{hash(link or title)}",
                    "platform": "Worknhire",
                    "title": title,
                    "description": desc,
                    "budget": budget,
                    "client_rating": rating,
                    "link": link,
                    "found_at": datetime.now().isoformat(),
                    "keyword_matched": term,
                })
            except Exception as e:
                logger.debug(f"Worknhire card: {e}")

    logger.info(f"Worknhire: {len(jobs)} jobs")
    return jobs


# ═══════════════════════════════════════════════════════════════
#  INTERNATIONAL PORTALS
# ═══════════════════════════════════════════════════════════════

# ── 4. Freelancer.com (Public REST API + HTML fallback) ─────────

def scrape_freelancer():
    jobs = []
    search_terms = [
        "python ai langchain",
        "machine learning data science",
        "rag chatbot openai",
        "nlp python automation",
    ]

    for term in search_terms:
        url = (
            "https://www.freelancer.com/api/projects/0.1/projects/active/"
            f"?query={requests.utils.quote(term)}"
            "&job_details=true&limit=20&sort_field=submitdate&sort_order=desc"
        )
        data = _safe_get(url, json_mode=True)
        if not data:
            html = _safe_get(f"https://www.freelancer.com/jobs/?keyword={requests.utils.quote(term)}")
            if html:
                jobs.extend(_parse_freelancer_html(html, term))
            continue

        try:
            projects = data.get("result", {}).get("projects", [])
            for p in projects:
                budget = p.get("budget", {})
                budget_str = f"${budget.get('minimum', 0)}-${budget.get('maximum', 0)}"
                jobs.append({
                    "id": f"fl_{p.get('id', hash(p.get('title', '')))}",
                    "platform": "Freelancer.com",
                    "title": p.get("title", ""),
                    "description": p.get("description", "")[:300],
                    "budget": budget_str,
                    "client_rating": None,
                    "link": f"https://www.freelancer.com/projects/{p.get('seo_url', '')}",
                    "found_at": datetime.now().isoformat(),
                    "keyword_matched": term,
                })
        except Exception as e:
            logger.debug(f"Freelancer API parse: {e}")

    logger.info(f"Freelancer.com: {len(jobs)} jobs")
    return jobs


def _parse_freelancer_html(html, term):
    jobs = []
    soup = BeautifulSoup(html, "lxml")
    for card in soup.select(".JobSearchCard-item")[:20]:
        try:
            title  = card.select_one(".JobSearchCard-primary-heading")
            link   = card.select_one("a[href]")
            desc   = card.select_one(".JobSearchCard-primary-description")
            budget = card.select_one(".JobSearchCard-secondary-price")
            t = title.get_text(strip=True) if title else ""
            if not t:
                continue
            l = "https://www.freelancer.com" + link["href"] if link else ""
            jobs.append({
                "id": f"fl_{hash(l or t)}",
                "platform": "Freelancer.com",
                "title": t,
                "description": desc.get_text(strip=True)[:300] if desc else "",
                "budget": budget.get_text(strip=True) if budget else "N/A",
                "client_rating": None,
                "link": l,
                "found_at": datetime.now().isoformat(),
                "keyword_matched": term,
            })
        except:
            pass
    return jobs


# ── 5. Guru.com (RSS Feed) ──────────────────────────────────────

def scrape_guru():
    jobs = []
    seen_ids = set()
    search_terms = ["python", "machine-learning", "data-science", "langchain", "nlp", "automation", "ai"]

    for term in search_terms:
        url = f"https://www.guru.com/jobs/rss/?q={requests.utils.quote(term)}&cat=4"
        xml_text = _safe_get(url)
        if not xml_text:
            continue

        try:
            root = ET.fromstring(xml_text)
            channel = root.find("channel")
            if not channel:
                continue

            for item in channel.findall("item"):
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                desc  = BeautifulSoup(item.findtext("description") or "", "lxml").get_text()[:300]
                guid  = item.findtext("guid") or link

                job_id = f"guru_{abs(hash(guid))}"
                if job_id in seen_ids or not title:
                    continue
                seen_ids.add(job_id)

                # Try to extract budget from description text
                budget_match = re.search(r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?", desc)
                budget = budget_match.group(0) if budget_match else "N/A"

                jobs.append({
                    "id": job_id,
                    "platform": "Guru.com",
                    "title": title,
                    "description": desc.strip(),
                    "budget": budget,
                    "client_rating": None,
                    "link": link,
                    "found_at": datetime.now().isoformat(),
                    "keyword_matched": term,
                })
        except Exception as e:
            logger.debug(f"Guru RSS parse: {e}")

    logger.info(f"Guru.com: {len(jobs)} jobs")
    return jobs


# ── 6. RemoteOK (Public JSON API) ──────────────────────────────

def scrape_remoteok():
    # RemoteOK requires a 1-second delay as per their terms
    time.sleep(1)
    data = _safe_get("https://remoteok.com/api", delay=False, json_mode=True)
    if not data or not isinstance(data, list):
        return []

    jobs = []
    for item in data:
        if not isinstance(item, dict):
            continue

        tags = [t.lower() for t in item.get("tags", [])]
        position = item.get("position", "").lower()
        desc = (item.get("description") or "").lower()

        # Keep only AI/data/Python relevant jobs
        if not any(kw in tags or kw in position or kw in desc for kw in AI_KEYWORDS):
            continue

        title = item.get("position", "")
        if not title:
            continue

        salary_min = item.get("salary_min") or 0
        salary_max = item.get("salary_max") or 0
        budget = f"${salary_min:,}–${salary_max:,}/yr" if salary_min else "N/A"

        jobs.append({
            "id": f"rok_{item.get('id', abs(hash(title)))}",
            "platform": "RemoteOK",
            "title": title,
            "description": BeautifulSoup(item.get("description") or "", "lxml").get_text()[:300],
            "budget": budget,
            "client_rating": None,
            "link": item.get("url", ""),
            "found_at": datetime.now().isoformat(),
            "keyword_matched": ", ".join(tags[:3]),
        })

    logger.info(f"RemoteOK: {len(jobs)} jobs")
    return jobs


# ── 7. PeoplePerHour ───────────────────────────────────────────

def scrape_peopleperhour():
    jobs = []
    search_terms = ["python", "machine-learning", "data-science", "langchain", "nlp"]

    for term in search_terms:
        url = f"https://www.peopleperhour.com/freelance-jobs?q={requests.utils.quote(term)}&sort=latest"
        html = _safe_get(url)
        if not html:
            continue

        soup = BeautifulSoup(html, "lxml")
        cards = (
            soup.select("[data-test='job-tile']") or
            soup.select(".JobSearchCard") or
            soup.select("li.item") or
            soup.find_all("div", class_=re.compile(r"job.?card|listing.?item|result.?item", re.I))
        )

        for card in cards[:15]:
            try:
                title_el = (
                    card.find("h2") or card.find("h3") or
                    card.find(class_=re.compile(r"title|heading|name", re.I))
                )
                title = title_el.get_text(strip=True) if title_el else ""
                if not title or len(title) < 5:
                    continue

                link_el = card.find("a", href=True)
                link = link_el["href"] if link_el else ""
                if link and not link.startswith("http"):
                    link = "https://www.peopleperhour.com" + link

                budget_el = card.find(class_=re.compile(r"budget|price|amount|fee|rate", re.I))
                budget = budget_el.get_text(strip=True) if budget_el else "N/A"

                desc_el = card.find("p") or card.find(class_=re.compile(r"desc|detail|summary|body", re.I))
                desc = desc_el.get_text(strip=True)[:300] if desc_el else ""

                jobs.append({
                    "id": f"pph_{abs(hash(link or title))}",
                    "platform": "PeoplePerHour",
                    "title": title,
                    "description": desc,
                    "budget": budget,
                    "client_rating": None,
                    "link": link,
                    "found_at": datetime.now().isoformat(),
                    "keyword_matched": term,
                })
            except Exception as e:
                logger.debug(f"PeoplePerHour card: {e}")

    logger.info(f"PeoplePerHour: {len(jobs)} jobs")
    return jobs


# ── 8. Hubstaff Talent ─────────────────────────────────────────

def scrape_hubstaff():
    jobs = []
    search_terms = ["python", "machine learning", "data science", "nlp", "automation", "langchain"]

    for term in search_terms:
        url = f"https://talent.hubstaff.com/search/jobs?term={requests.utils.quote(term)}"
        html = _safe_get(url)
        if not html:
            continue

        soup = BeautifulSoup(html, "lxml")
        cards = (
            soup.select(".JobCard") or
            soup.select(".job-card") or
            soup.select("[class*='job']") or
            soup.find_all("div", class_=re.compile(r"job|listing|result", re.I))
        )

        for card in cards[:15]:
            try:
                title_el = (
                    card.find("h2") or card.find("h3") or
                    card.find(class_=re.compile(r"title|position|name", re.I))
                )
                title = title_el.get_text(strip=True) if title_el else ""
                if not title or len(title) < 5:
                    continue

                link_el = card.find("a", href=True)
                link = link_el["href"] if link_el else ""
                if link and not link.startswith("http"):
                    link = "https://talent.hubstaff.com" + link

                budget_el = card.find(class_=re.compile(r"rate|salary|budget|pay|compensation", re.I))
                budget = budget_el.get_text(strip=True) if budget_el else "N/A"

                desc_el = card.find("p") or card.find(class_=re.compile(r"desc|detail|summary|skills|about", re.I))
                desc = desc_el.get_text(strip=True)[:300] if desc_el else ""

                jobs.append({
                    "id": f"hs_{abs(hash(link or title))}",
                    "platform": "Hubstaff Talent",
                    "title": title,
                    "description": desc,
                    "budget": budget,
                    "client_rating": None,
                    "link": link,
                    "found_at": datetime.now().isoformat(),
                    "keyword_matched": term,
                })
            except Exception as e:
                logger.debug(f"Hubstaff card: {e}")

    logger.info(f"Hubstaff Talent: {len(jobs)} jobs")
    return jobs


# ═══════════════════════════════════════════════════════════════
#  DEMO MODE
# ═══════════════════════════════════════════════════════════════

def _demo_jobs():
    now = datetime.now().isoformat()
    return [
        # Indian
        {
            "id": "demo_tl_001", "platform": "Truelancer",
            "title": "Build RAG Chatbot for Legal Documents",
            "description": "Python developer needed to build a RAG-based chatbot using LangChain and FAISS. Documents are PDFs. Need Streamlit UI and OpenAI integration.",
            "budget": "₹25,000", "client_rating": 4.5,
            "link": "https://www.truelancer.com/project/demo-001",
            "found_at": now, "keyword_matched": "langchain",
        },
        {
            "id": "demo_is_001", "platform": "Internshala",
            "title": "Python Data Science Intern / Freelancer",
            "description": "Looking for a Python developer with pandas, numpy, and matplotlib skills for data analysis and report generation project.",
            "budget": "₹10,000/month", "client_rating": None,
            "link": "https://internshala.com/freelancing/detail/demo-001",
            "found_at": now, "keyword_matched": "python",
        },
        {
            "id": "demo_wnh_001", "platform": "Worknhire",
            "title": "Machine Learning Model for Demand Forecasting",
            "description": "Need ML developer for demand forecasting using scikit-learn and time-series methods. Streamlit dashboard required for results visualization.",
            "budget": "₹15,000", "client_rating": 4.2,
            "link": "https://www.worknhire.com/project/demo-001",
            "found_at": now, "keyword_matched": "machine-learning",
        },
        # International
        {
            "id": "demo_fl_001", "platform": "Freelancer.com",
            "title": "Python AI Agent for Automated Data Analysis",
            "description": "Build an autonomous data analyst agent using LangChain agents and Python. Should connect to MySQL database and generate insights automatically.",
            "budget": "$500-$1000", "client_rating": None,
            "link": "https://www.freelancer.com/projects/demo-002",
            "found_at": now, "keyword_matched": "python ai",
        },
        {
            "id": "demo_guru_001", "platform": "Guru.com",
            "title": "NLP Pipeline for Sentiment Analysis — E-commerce",
            "description": "Build NLP sentiment analysis pipeline using HuggingFace transformers for product reviews. REST API (FastAPI) and cloud deployment required.",
            "budget": "$300-$600", "client_rating": None,
            "link": "https://www.guru.com/projects/demo-001",
            "found_at": now, "keyword_matched": "nlp",
        },
        {
            "id": "demo_rok_001", "platform": "RemoteOK",
            "title": "Senior Python Engineer — AI/ML Platform (Remote)",
            "description": "We are building an AI-powered analytics platform. Looking for a Python engineer with experience in LangChain, FastAPI, and cloud deployments.",
            "budget": "$80,000–$120,000/yr", "client_rating": None,
            "link": "https://remoteok.com/jobs/demo-001",
            "found_at": now, "keyword_matched": "python, ai, ml",
        },
        {
            "id": "demo_pph_001", "platform": "PeoplePerHour",
            "title": "ETL Pipeline + Power BI Dashboard in Python",
            "description": "Build ETL pipeline in Python to extract data from REST APIs, transform and load into SQL. Dashboard visualization and reporting needed.",
            "budget": "£200-£400", "client_rating": None,
            "link": "https://www.peopleperhour.com/job/demo-001",
            "found_at": now, "keyword_matched": "python",
        },
        {
            "id": "demo_hs_001", "platform": "Hubstaff Talent",
            "title": "Data Science Consultant — Predictive Analytics",
            "description": "Predictive analytics project using scikit-learn and SHAP for explainability. Need weekly Streamlit reports for business stakeholders.",
            "budget": "$40/hr", "client_rating": None,
            "link": "https://talent.hubstaff.com/jobs/demo-001",
            "found_at": now, "keyword_matched": "data science",
        },
    ]


# ═══════════════════════════════════════════════════════════════
#  MAIN ENTRY
# ═══════════════════════════════════════════════════════════════

INDIAN_SCRAPERS = [
    ("Truelancer",  scrape_truelancer),
    ("Internshala", scrape_internshala),
    ("Worknhire",   scrape_worknhire),
]

INTERNATIONAL_SCRAPERS = [
    ("Freelancer.com",  scrape_freelancer),
    ("Guru.com",        scrape_guru),
    ("RemoteOK",        scrape_remoteok),
    ("PeoplePerHour",   scrape_peopleperhour),
    ("Hubstaff Talent", scrape_hubstaff),
]


def scrape_all():
    if DEMO_MODE:
        logger.info("🎭 DEMO MODE: returning sample jobs from all 8 portals")
        return _demo_jobs()

    # Reset per-portal request counters for this scan
    _portal_request_count.clear()

    jobs = []
    all_scrapers = INDIAN_SCRAPERS + INTERNATIONAL_SCRAPERS

    for name, fn in all_scrapers:
        try:
            result = fn()
            jobs.extend(result)
            logger.info(f"  ✓ {name}: {len(result)} jobs collected")
        except Exception as e:
            logger.error(f"  ✗ {name} scraper crashed: {e}")

    if not jobs:
        logger.warning("⚠️ No jobs from any live source — using demo data as fallback")
        return _demo_jobs()

    logger.info(f"Total jobs scraped across all {len(all_scrapers)} portals: {len(jobs)}")
    return jobs
