"""
scraper.py — Scrape job listings from Truelancer & Freelancer.com
Strategies (in order of preference):
  1. Freelancer.com public REST API (no key needed, rate-limited to 25 req/5min)
  2. HTML scraping with rotating user-agents
  3. Demo mode (generates realistic sample data for testing)
"""

import requests
import logging
import re
import time
import random
import json
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger("JobAgent")

DEMO_MODE = False   # Set True to test without internet access

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
]

def _headers():
    return {
        "User-Agent": random.choice(UA_LIST),
        "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }

def _safe_get(url, timeout=20, json_mode=False):
    time.sleep(random.uniform(2, 5))
    try:
        r = requests.get(url, headers=_headers(), timeout=timeout)
        r.raise_for_status()
        return r.json() if json_mode else r.text
    except Exception as e:
        logger.warning(f"GET {url[:60]}... → {e}")
        return None


# ─── FREELANCER.COM — Public REST API ──────────────────────────

def scrape_freelancer():
    """Freelancer public project search API."""
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
            # Fallback: HTML scrape
            html = _safe_get(f"https://www.freelancer.com/jobs/?keyword={requests.utils.quote(term)}")
            if html:
                jobs.extend(_parse_freelancer_html(html, term))
            continue

        try:
            projects = data.get("result", {}).get("projects", [])
            for p in projects:
                budget = p.get("budget", {})
                budget_str = f"${budget.get('minimum',0)}-${budget.get('maximum',0)}"
                jobs.append({
                    "id": f"fl_{p.get('id',hash(p.get('title','')))}",
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
            logger.debug(f"Freelancer API parse error: {e}")

    logger.info(f"Freelancer.com: {len(jobs)} jobs")
    return jobs


def _parse_freelancer_html(html, term):
    jobs = []
    soup = BeautifulSoup(html, "lxml")
    for card in soup.select(".JobSearchCard-item")[:20]:
        try:
            title = card.select_one(".JobSearchCard-primary-heading")
            link  = card.select_one("a[href]")
            desc  = card.select_one(".JobSearchCard-primary-description")
            budget= card.select_one(".JobSearchCard-secondary-price")
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


# ─── TRUELANCER — HTML scrape ────────────────────────────────

def scrape_truelancer():
    jobs = []
    search_terms = ["python", "machine-learning", "data-science", "langchain", "nlp"]

    for term in search_terms:
        # Try category browse (less bot-detection than search)
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

        # Multiple possible card selectors
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
                rating_text = rating_el.get_text(strip=True) if rating_el else ""
                rating = _extract_number(rating_text)

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
                logger.debug(f"TL card parse: {e}")

    logger.info(f"Truelancer: {len(jobs)} jobs")
    return jobs


# ─── DEMO MODE ───────────────────────────────────────────────

def _demo_jobs():
    """Realistic sample jobs for testing when internet scraping fails."""
    now = datetime.now().isoformat()
    return [
        {
            "id": "demo_001", "platform": "Truelancer",
            "title": "Build RAG Chatbot for Legal Documents",
            "description": "We need a Python developer to build a RAG-based chatbot using LangChain and FAISS. Documents are PDFs. Need Streamlit UI and OpenAI integration.",
            "budget": "₹25,000", "client_rating": 4.5,
            "link": "https://www.truelancer.com/project/demo-001",
            "found_at": now, "keyword_matched": "langchain",
        },
        {
            "id": "demo_002", "platform": "Freelancer.com",
            "title": "Python AI Agent for Automated Data Analysis",
            "description": "Build an autonomous data analyst agent using LangChain agents and Python. Should connect to our MySQL database and generate insights automatically.",
            "budget": "$500-$1000", "client_rating": None,
            "link": "https://www.freelancer.com/projects/demo-002",
            "found_at": now, "keyword_matched": "python ai",
        },
        {
            "id": "demo_003", "platform": "Truelancer",
            "title": "Machine Learning Model for Customer Churn",
            "description": "Need ML model to predict customer churn using scikit-learn and SHAP for explainability. Streamlit dashboard required.",
            "budget": "₹15,000", "client_rating": 4.2,
            "link": "https://www.truelancer.com/project/demo-003",
            "found_at": now, "keyword_matched": "machine-learning",
        },
        {
            "id": "demo_004", "platform": "Freelancer.com",
            "title": "NLP Text Classification for E-commerce Reviews",
            "description": "Classify product reviews using BERT or HuggingFace transformers. Need REST API (FastAPI) and deployment on cloud.",
            "budget": "$200-$400", "client_rating": None,
            "link": "https://www.freelancer.com/projects/demo-004",
            "found_at": now, "keyword_matched": "nlp",
        },
        {
            "id": "demo_005", "platform": "Truelancer",
            "title": "ETL Pipeline + Power BI Dashboard",
            "description": "Build ETL pipeline in Python to extract data from REST APIs, transform it and load into SQL. Basic data visualization needed.",
            "budget": "₹8,000", "client_rating": 3.5,
            "link": "https://www.truelancer.com/project/demo-005",
            "found_at": now, "keyword_matched": "python",
        },
    ]


# ─── MAIN ────────────────────────────────────────────────────

def _extract_number(text):
    m = re.search(r"(\d+\.?\d*)", text)
    return float(m.group(1)) if m else None


def scrape_all():
    if DEMO_MODE:
        logger.info("🎭 DEMO MODE: returning sample jobs")
        return _demo_jobs()

    jobs = []
    jobs.extend(scrape_truelancer())
    jobs.extend(scrape_freelancer())

    if not jobs:
        logger.warning("⚠️ No jobs scraped from live sites — using demo data as fallback")
        return _demo_jobs()

    return jobs
