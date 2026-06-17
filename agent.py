"""
agent.py — Main job search agent loop.
Run: python agent.py
Scans every 2 hours, filters, notifies.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime

import schedule

import config
from scraper import scrape_all
from ai_filter import ai_score_jobs
from notifier import notify

# ─── LOGGING ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("JobAgent")


# ─── STATE ───────────────────────────────────────────────────

def load_seen() -> set:
    if os.path.exists(config.STATE_FILE):
        with open(config.STATE_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    with open(config.STATE_FILE, "w") as f:
        json.dump(list(seen), f)


def load_jobs() -> list:
    if os.path.exists(config.JOBS_FILE):
        try:
            with open(config.JOBS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            logger.warning("jobs_found.json corrupted — resetting to empty list")
            return []
    return []


def save_jobs(jobs: list):
    # Atomic write: write to .tmp then rename so dashboard never reads a half-written file
    tmp = config.JOBS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    os.replace(tmp, config.JOBS_FILE)


# ─── FILTERS ─────────────────────────────────────────────────

def keyword_match(job: dict) -> bool:
    text = (job["title"] + " " + job["description"]).lower()
    return any(kw in text for kw in config.KEYWORDS)


def client_ok(job: dict) -> bool:
    """Apply client quality rules from config."""
    rating = job.get("client_rating")
    budget_str = job.get("budget", "")
    budget_num = _parse_budget(budget_str)

    # If we have a rating and it's too low — skip
    if rating is not None and rating < config.MIN_CLIENT_RATING:
        # Exception: low budget jobs are ok regardless
        if budget_num and budget_num > config.ZERO_RATING_BUDGET_LIMIT:
            return False

    return True


def _parse_budget(s: str) -> float | None:
    import re
    nums = re.findall(r"[\d,]+", str(s).replace(",", ""))
    if nums:
        try:
            return float(nums[-1])
        except:
            pass
    return None


# ─── CORE SCAN ───────────────────────────────────────────────

def run_scan():
    logger.info("=" * 60)
    logger.info(f"🔍 Scan started — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    seen = load_seen()
    existing_jobs = load_jobs()

    # 1. Scrape
    raw_jobs = scrape_all()
    logger.info(f"Total raw jobs scraped: {len(raw_jobs)}")

    # 2. Deduplicate
    new_jobs = [j for j in raw_jobs if j["id"] not in seen]
    logger.info(f"New (unseen) jobs: {len(new_jobs)}")

    if not new_jobs:
        logger.info("No new jobs this scan.")
        return

    # 3. Keyword filter
    kw_filtered = [j for j in new_jobs if keyword_match(j)]
    logger.info(f"After keyword filter: {len(kw_filtered)}")

    # 4. Client quality filter
    quality_filtered = [j for j in kw_filtered if client_ok(j)]
    logger.info(f"After client quality filter: {len(quality_filtered)}")

    if not quality_filtered:
        # Still mark all as seen
        seen.update(j["id"] for j in new_jobs)
        save_seen(seen)
        return

    # 5. AI scoring — score ALL filtered jobs
    scored = ai_score_jobs(quality_filtered)
    apply_count = sum(1 for j in scored if j.get("ai_apply", False))
    logger.info(f"AI scored {len(scored)} jobs — {apply_count} recommended to apply")

    for j in scored:
        logger.info(f"  [{j.get('ai_score','?')}/10] {j['title'][:55]} | {j['platform']}")

    # 6. Save ALL scored jobs to dashboard (no auto-notification)
    # Notifications are sent manually from the dashboard per job.
    all_jobs = scored + existing_jobs
    save_jobs(all_jobs[:500])

    seen.update(j["id"] for j in new_jobs)
    save_seen(seen)

    logger.info(f"✅ Scan complete. {len(scored)} jobs saved to dashboard. Open http://localhost:8501 to review and send alerts.")


# ─── ENTRY ───────────────────────────────────────────────────

if __name__ == "__main__":
    once_mode = "--once" in sys.argv

    logger.info("🤖 JK Data Lab Job Search Agent starting...")
    if not once_mode:
        logger.info(f"   Scanning every {config.SCAN_INTERVAL_MINUTES} minutes")
    logger.info(f"   WhatsApp: {config.WHATSAPP_NUMBER}")
    logger.info(f"   Telegram: {'✅ configured' if config.TELEGRAM_BOT_TOKEN else '❌ not set'}")

    run_scan()

    if once_mode:
        logger.info("✅ --once mode: scan complete, exiting.")
        sys.exit(0)

    # Continuous mode: schedule and loop
    schedule.every(config.SCAN_INTERVAL_MINUTES).minutes.do(run_scan)
    logger.info(f"⏰ Next scan in {config.SCAN_INTERVAL_MINUTES} minutes...")

    while True:
        schedule.run_pending()
        time.sleep(60)
