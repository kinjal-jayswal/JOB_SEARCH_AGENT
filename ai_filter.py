"""
ai_filter.py — Use Claude to score each job's relevance for JK Data Lab.
Sends a batch of jobs and returns scored + filtered list.
"""

import json
import logging
import requests

logger = logging.getLogger("JobAgent")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """You are a job relevance scorer for JK Data Lab, an AI & Data Science consultancy.

JK Data Lab services:
- Multi-Agent AI Systems (LangChain, OpenAI, Python)
- RAG & Document Intelligence (FAISS, Streamlit)
- NLP & Text Analytics (BERT, HuggingFace, scikit-learn)
- BI & Dashboards (Streamlit, Plotly, SQL, FastAPI)
- Predictive Analytics & ML
- Python Automation & ETL

Rate each job 1-10 for relevance. Score 7+ means "apply".
Return ONLY valid JSON, no markdown, no explanation.
Format: [{"id":"...","score":8,"reason":"short reason","apply":true}, ...]"""


def ai_score_jobs(jobs: list) -> list:
    """
    Score jobs with Claude. Returns enriched list with score/apply fields.
    Falls back gracefully if API unavailable.
    """
    if not jobs:
        return []

    # Build compact input to save tokens
    slim = [
        {
            "id": j["id"],
            "title": j["title"],
            "desc": j["description"][:200],
            "budget": j["budget"],
            "platform": j["platform"],
        }
        for j in jobs
    ]

    prompt = f"Score these {len(slim)} jobs:\n{json.dumps(slim, ensure_ascii=False)}"

    try:
        resp = requests.post(
            ANTHROPIC_URL,
            headers={"Content-Type": "application/json"},
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["content"][0]["text"].strip()

        # Strip any accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        scores = json.loads(raw)
        score_map = {s["id"]: s for s in scores}

        for job in jobs:
            s = score_map.get(job["id"], {})
            job["ai_score"] = s.get("score", 5)
            job["ai_reason"] = s.get("reason", "")
            job["ai_apply"] = s.get("apply", job["ai_score"] >= 7)

    except Exception as e:
        logger.warning(f"AI scoring failed ({e}), using keyword fallback")
        # Fallback: keyword match scoring
        for job in jobs:
            text = (job["title"] + " " + job["description"]).lower()
            hits = sum(1 for kw in ["python","ai","machine learning","langchain","rag","nlp","data"] if kw in text)
            job["ai_score"] = min(10, hits * 2)
            job["ai_reason"] = f"Keyword hits: {hits}"
            job["ai_apply"] = hits >= 3

    return jobs
