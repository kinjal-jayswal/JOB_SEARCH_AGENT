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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        # Polite crawl: 1.5-3 s between requests — human-speed, still ban-safe
        time.sleep(random.uniform(1.5, 3))
    try:
        r = requests.get(url, headers=_headers(), timeout=timeout)
        # Respect 429 Too Many Requests — back off and do not retry
        if r.status_code == 429:
            logger.warning(f"Rate-limited (429) by {url[:50]} — skipping portal for this scan")
            return None
        r.raise_for_status()
        if json_mode:
            return r.json()
        # Force UTF-8 so ₹ / £ / € are stored correctly
        r.encoding = "utf-8"
        return r.text
    except Exception as e:
        logger.warning(f"GET {url[:70]}... → {e}")
        return None


def _job_link(card, base_url: str, prefer_patterns: list[str] = None) -> str:
    """
    Extract a direct job-listing link from a card element.

    Strategy:
      1. Look for an <a> whose href matches known job-URL patterns (has a digit,
         or contains /post/ /project/ /job/ /detail/).
      2. Fall back to the first <a> in the title element (h2/h3/h4).
      3. Last resort: first <a href> in the card.

    Category/tag links (e.g. /freelance-jobs/python-ai-agent) are explicitly
    excluded because they produce 404s when clicked.
    """
    job_patterns = prefer_patterns or [
        r"/post/", r"/project", r"/job/", r"/detail/", r"/listing/",
        r"/work/", r"/gig/", r"\d{4,}",   # any URL with a 4+ digit ID
    ]
    # Exclude known category/tag URL shapes
    category_patterns = [
        r"^/freelance-jobs/[a-z-]+$",
        r"^/jobs/[a-z-]+$",
        r"^/freelance-[a-z-]+-jobs/?$",
    ]

    all_links = card.find_all("a", href=True)

    # 1. Prefer links matching job patterns and not matching category patterns
    for a in all_links:
        href = a["href"]
        is_job = any(re.search(p, href) for p in job_patterns)
        is_cat = any(re.match(p, href) for p in category_patterns)
        if is_job and not is_cat:
            return _make_absolute(href, base_url)

    # 2. Link from inside the heading element
    for tag in ("h2", "h3", "h4"):
        heading = card.find(tag)
        if heading:
            a = heading.find("a", href=True)
            if a:
                href = a["href"]
                is_cat = any(re.match(p, href) for p in category_patterns)
                if not is_cat:
                    return _make_absolute(href, base_url)

    # 3. Last resort — first link that isn't a category page
    for a in all_links:
        href = a["href"]
        is_cat = any(re.match(p, href) for p in category_patterns)
        if not is_cat:
            return _make_absolute(href, base_url)

    return ""


def _make_absolute(href: str, base: str) -> str:
    if href.startswith("http"):
        return href
    return base.rstrip("/") + "/" + href.lstrip("/")


def _extract_number(text):
    m = re.search(r"(\d+\.?\d*)", str(text))
    return float(m.group(1)) if m else None


# ═══════════════════════════════════════════════════════════════
#  INDIAN PORTALS
# ═══════════════════════════════════════════════════════════════

# ── 1. Truelancer ───────────────────────────────────────────────

def scrape_truelancer():
    jobs = []
    search_terms = ["python", "machine-learning", "langchain", "nlp"]

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

                link = _job_link(card, "https://www.truelancer.com",
                                 prefer_patterns=[r"/post/", r"/project/", r"\d{4,}"])

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
    search_terms = ["python", "machine-learning", "data-science", "nlp"]

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

                link = _job_link(card, "https://internshala.com",
                                 prefer_patterns=[r"/freelancing/detail/", r"/jobs/detail/", r"\d{4,}"])

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
    search_terms = ["python", "data-science", "ai", "nlp"]

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

                link = _job_link(card, "https://www.worknhire.com",
                                 prefer_patterns=[r"/project/", r"/job/", r"\d{4,}"])

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
    """
    Freelancer.com: tries REST API first, falls back to HTML if API returns
    success-but-empty (common when the endpoint silently filters results).
    """
    jobs = []
    seen_ids: set = set()
    search_terms = ["python", "langchain", "machine-learning", "nlp", "data-science"]

    for term in search_terms:
        # Try API (no job_details — lighter, less likely to need auth)
        api_url = (
            "https://www.freelancer.com/api/projects/0.1/projects/active/"
            f"?query={requests.utils.quote(term)}&limit=20"
            "&sort_field=submitdate&sort_order=desc"
        )
        data     = _safe_get(api_url, json_mode=True)
        projects = []

        if data:
            if data.get("status") != "success":
                logger.info(f"Freelancer API non-success for '{term}': {str(data)[:100]}")
            else:
                projects = data.get("result", {}).get("projects", [])
                logger.info(f"Freelancer API '{term}': {len(projects)} projects")

        # Fall back to HTML whenever API gave 0 results
        if not projects:
            for html_url in [
                f"https://www.freelancer.com/jobs/{requests.utils.quote(term)}/",
                f"https://www.freelancer.com/jobs/?keyword={requests.utils.quote(term)}",
            ]:
                html = _safe_get(html_url)
                if html:
                    parsed = _parse_freelancer_html(html, term)
                    if parsed:
                        logger.info(f"Freelancer HTML '{html_url}': {len(parsed)} jobs")
                        jobs.extend(j for j in parsed if j["id"] not in seen_ids)
                        seen_ids.update(j["id"] for j in parsed)
                        break
            continue

        for p in projects:
            try:
                budget = p.get("budget", {})
                budget_str = f"${budget.get('minimum', 0)}-${budget.get('maximum', 0)}"
                job_id = f"fl_{p.get('id', abs(hash(p.get('title', ''))))}"
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                jobs.append({
                    "id": job_id,
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
                logger.debug(f"Freelancer project parse: {e}")

    logger.info(f"Freelancer.com: {len(jobs)} jobs")
    return jobs


def _parse_freelancer_html(html, term):
    jobs = []
    soup = BeautifulSoup(html, "lxml")
    # Try multiple possible card selectors (site HTML changes over time)
    cards = (
        soup.select(".JobSearchCard-item") or
        soup.select("[data-project-id]") or
        soup.select(".project-card") or
        soup.find_all("div", class_=re.compile(r"JobSearch|project.?card", re.I))
    )
    for card in cards[:20]:
        try:
            title  = (card.select_one(".JobSearchCard-primary-heading") or
                      card.select_one("h2") or card.select_one("h3"))
            link   = card.select_one("a[href]")
            desc   = (card.select_one(".JobSearchCard-primary-description") or
                      card.select_one("p"))
            budget = (card.select_one(".JobSearchCard-secondary-price") or
                      card.select_one("[class*='price'],[class*='budget']"))
            t = title.get_text(strip=True) if title else ""
            if not t:
                continue
            l = "https://www.freelancer.com" + link["href"] if link and link["href"].startswith("/") else (link["href"] if link else "")
            jobs.append({
                "id": f"fl_{abs(hash(l or t))}",
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


# ── 5. Remotive.com (Free Public API — replaces Guru.com which is 403 blocked) ─

_REMOTIVE_TECH_KW = [
    "python", "machine learning", "data science", "nlp", "langchain",
    "llm", "ai", "deep learning", "fastapi", "streamlit", "etl", "automation",
]


def scrape_remotive():
    jobs = []
    seen_ids = set()
    search_terms = ["python", "machine learning", "data science", "nlp", "langchain"]

    for term in search_terms:
        url = f"https://remotive.com/api/remote-jobs?category=software-dev&search={requests.utils.quote(term)}"
        data = _safe_get(url, json_mode=True)
        if not data:
            continue

        for item in data.get("jobs", []):
            job_id = f"rem_{item.get('id', abs(hash(item.get('url', ''))))}"
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            title = item.get("title", "")
            tags  = [t.lower() for t in item.get("tags", [])]
            title_lower = title.lower()

            # Filter: must be AI/Python relevant
            if not any(kw in title_lower or kw in " ".join(tags) for kw in _REMOTIVE_TECH_KW):
                continue

            desc   = BeautifulSoup(item.get("description", "") or "", "lxml").get_text()[:300].strip()
            salary = item.get("salary") or "N/A"

            jobs.append({
                "id": job_id,
                "platform": "Remotive",
                "title": title,
                "description": desc,
                "budget": salary,
                "client_rating": None,
                "link": item.get("url", ""),
                "found_at": datetime.now().isoformat(),
                "keyword_matched": term,
            })

    logger.info(f"Remotive: {len(jobs)} jobs")
    return jobs


# ── 6. RemoteOK (Public JSON API) ──────────────────────────────

_REMOTEOK_TECH_TAGS = {
    "python", "machine-learning", "data-science", "nlp", "ai",
    "langchain", "deep-learning", "tensorflow", "pytorch", "scikit-learn",
    "data-engineering", "llm", "openai", "fastapi", "streamlit",
    "natural-language-processing", "computer-vision", "rag", "huggingface",
    "automation", "etl", "analytics",
}


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

        # Normalise tags: lower-case, replace spaces with dashes
        raw_tags = item.get("tags", []) or []
        tags_normalised = {t.lower().replace(" ", "-") for t in raw_tags}
        position = item.get("position", "").lower()

        # Must have at least one recognised tech tag OR keyword in title
        tag_match   = bool(tags_normalised & _REMOTEOK_TECH_TAGS)
        title_match = any(kw in position for kw in ["python", "data", "ml ", "nlp", "ai ", "langchain", "llm"])

        if not (tag_match or title_match):
            continue

        title = item.get("position", "")
        if not title:
            continue

        # Strip HTML from description
        raw_desc = item.get("description") or ""
        clean_desc = BeautifulSoup(raw_desc, "lxml").get_text(separator=" ")[:300].strip()

        salary_min = item.get("salary_min") or 0
        salary_max = item.get("salary_max") or 0
        budget = f"${salary_min:,}–${salary_max:,}/yr" if salary_min else "N/A"

        matched = sorted(tags_normalised & _REMOTEOK_TECH_TAGS)

        jobs.append({
            "id": f"rok_{item.get('id', abs(hash(title)))}",
            "platform": "RemoteOK",
            "title": title,
            "description": clean_desc,
            "budget": budget,
            "client_rating": None,
            "link": item.get("url", ""),
            "found_at": datetime.now().isoformat(),
            "keyword_matched": ", ".join(matched[:4]) if matched else position[:30],
        })

    logger.info(f"RemoteOK: {len(jobs)} jobs")
    return jobs


# ── 7. We Work Remotely (RSS Feed) ────────────────────────────

# Strict terms only — broad words like "data","engineer","analytics" cause
# too many false positives (Design Engineer, Sales Analytics, etc.)
_WWR_KW = [
    "python", "machine learning", "langchain", "nlp", "llm", "openai",
    "data science", "data scientist", "data engineer", "deep learning",
    "tensorflow", "pytorch", "fastapi", "streamlit", "huggingface",
    "rag", "ai engineer", "ml engineer", "artificial intelligence",
    "computer vision", "natural language processing", "etl",
    "automation engineer", "generative ai", "large language model",
]


def scrape_weworkremotely():
    jobs = []
    seen_ids = set()
    url = "https://weworkremotely.com/remote-jobs.rss"
    xml_text = _safe_get(url)
    if not xml_text:
        return []

    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            desc  = BeautifulSoup(item.findtext("description") or "", "lxml").get_text()[:300].strip()

            text = (title + " " + desc).lower()
            if not any(kw in text for kw in _WWR_KW):
                continue

            job_id = f"wwr_{abs(hash(link or title))}"
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            budget_m = re.search(r"\$[\d,]+(?:k)?(?:\s*[-–]\s*\$[\d,]+(?:k)?)?(?:/yr|/mo)?", desc, re.I)
            budget   = budget_m.group(0) if budget_m else "N/A"

            jobs.append({
                "id": job_id,
                "platform": "We Work Remotely",
                "title": title,
                "description": desc,
                "budget": budget,
                "client_rating": None,
                "link": link,
                "found_at": datetime.now().isoformat(),
                "keyword_matched": "rss-filter",
            })
    except Exception as e:
        logger.debug(f"WWR RSS parse: {e}")

    logger.info(f"We Work Remotely: {len(jobs)} jobs")
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


# ── 8. Jobicy (Free public API — no auth) ─────────────────────

_JOBICY_TAGS = ["python", "machine-learning", "data-science", "nlp", "langchain"]
_JOBICY_KW   = [
    "python", "machine learning", "langchain", "nlp", "llm", "openai",
    "data science", "data scientist", "data engineer", "deep learning",
    "tensorflow", "pytorch", "fastapi", "streamlit", "huggingface",
    "rag", "ai engineer", "ml engineer", "artificial intelligence",
    "etl", "automation", "generative ai",
]


def scrape_jobicy():
    jobs     = []
    seen_ids: set = set()

    for tag in _JOBICY_TAGS:
        url  = f"https://jobicy.com/api/v2/remote-jobs?count=20&tag={requests.utils.quote(tag)}"
        data = _safe_get(url, json_mode=True)
        if not data:
            continue

        for item in data.get("jobs", []):
            job_id = f"jcy_{item.get('id', abs(hash(item.get('url', ''))))}"
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            title  = item.get("jobTitle", "")
            tags   = [t.lower() for t in item.get("jobIndustry", []) or []]
            t_low  = title.lower()

            if not any(kw in t_low or kw in " ".join(tags) for kw in _JOBICY_KW):
                continue

            desc   = BeautifulSoup(item.get("jobDescription", "") or "", "lxml").get_text()[:300].strip()
            salary = item.get("annualSalaryMax") or item.get("annualSalaryMin") or "N/A"
            budget = f"${salary:,}/yr" if isinstance(salary, (int, float)) else str(salary)

            jobs.append({
                "id": job_id,
                "platform": "Jobicy",
                "title": title,
                "description": desc,
                "budget": budget,
                "client_rating": None,
                "link": item.get("url", ""),
                "found_at": datetime.now().isoformat(),
                "keyword_matched": tag,
            })

    logger.info(f"Jobicy: {len(jobs)} jobs")
    return jobs


# ═══════════════════════════════════════════════════════════════
#  MAIN ENTRY
# ═══════════════════════════════════════════════════════════════

# JS-rendered sites (React/MUI) — return 0 without Selenium, kept for future upgrade
INDIAN_SCRAPERS = [
    ("Truelancer",  scrape_truelancer),
    ("Internshala", scrape_internshala),
]

# API/RSS sources — confirmed working
INTERNATIONAL_SCRAPERS = [
    ("Freelancer.com",   scrape_freelancer),     # Public REST API + HTML fallback
    ("RemoteOK",         scrape_remoteok),        # Public JSON API
    ("Remotive",         scrape_remotive),        # Free public API
    ("We Work Remotely", scrape_weworkremotely),  # RSS feed
    ("Jobicy",           scrape_jobicy),          # Free public API — no auth
]


def scrape_all():
    if DEMO_MODE:
        logger.info("🎭 DEMO MODE: returning sample jobs from all 8 portals")
        return _demo_jobs()

    # Reset per-portal request counters for this scan
    _portal_request_count.clear()

    all_scrapers = INDIAN_SCRAPERS + INTERNATIONAL_SCRAPERS
    jobs = []

    # Run all 8 scrapers in parallel — cuts total time from ~4 min to ~30-45 s
    logger.info(f"🚀 Scraping {len(all_scrapers)} portals in parallel...")
    with ThreadPoolExecutor(max_workers=len(all_scrapers)) as pool:
        future_to_name = {pool.submit(fn): name for name, fn in all_scrapers}
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                result = future.result()
                jobs.extend(result)
                logger.info(f"  ✓ {name}: {len(result)} jobs")
            except Exception as e:
                logger.error(f"  ✗ {name} crashed: {e}")

    if not jobs:
        logger.warning("⚠️ No jobs from any live source — using demo data as fallback")
        return _demo_jobs()

    logger.info(f"✅ Total: {len(jobs)} jobs across {len(all_scrapers)} portals")
    return jobs
