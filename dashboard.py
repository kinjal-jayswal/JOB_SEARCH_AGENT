"""
dashboard.py — JK Data Lab Job Search Dashboard
Run: streamlit run dashboard.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

import config
from notifier import notify

st.set_page_config(
    page_title="JK Data Lab — Job Agent",
    page_icon="🤖",
    layout="wide",
)

if "notified" not in st.session_state:
    st.session_state.notified = set()

JOBS_FILE = "jobs_found.json"
LOG_FILE  = "agent.log"

# ── Platform config (derived from scraper lists — stays in sync automatically) ─
from scraper import INDIAN_SCRAPERS, INTERNATIONAL_SCRAPERS

INDIAN_PLATFORMS = {name for name, _ in INDIAN_SCRAPERS}
INTL_PLATFORMS   = {name for name, _ in INTERNATIONAL_SCRAPERS}
ALL_PLATFORMS    = sorted(INDIAN_PLATFORMS | INTL_PLATFORMS)

PLATFORM_COLORS = {
    "Truelancer":         "#00c9a7",
    "Internshala":        "#00b4d8",
    "Freelancer.com":     "#4f8bff",
    "Guru.com":           "#f59e0b",
    "RemoteOK":           "#22c55e",
    "Remotive":           "#a855f7",
    "We Work Remotely":   "#f97316",
    "Jobicy":             "#e11d48",
    "PeoplePerHour":      "#06b6d4",
}

PLATFORM_FLAGS = {
    "Truelancer":         "🇮🇳",
    "Internshala":        "🇮🇳",
    "Freelancer.com":     "🌐",
    "Guru.com":           "🌐",
    "RemoteOK":           "🌐",
    "Remotive":           "🌐",
    "We Work Remotely":   "🌐",
    "Jobicy":             "🌐",
    "PeoplePerHour":      "🌐",
}


# ── Data helpers ──────────────────────────────────────────────

def load_jobs():
    if not os.path.exists(JOBS_FILE):
        return []
    try:
        with open(JOBS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        st.warning("⚠️ jobs_found.json was corrupted and has been reset. Run a new scan.")
        with open(JOBS_FILE, "w", encoding="utf-8") as f:
            f.write("[]")
        return []


def load_log_tail(n=50):
    if not os.path.exists(LOG_FILE):
        return "No log yet."
    with open(LOG_FILE) as f:
        lines = f.readlines()
    return "".join(lines[-n:])


# ── Styles ────────────────────────────────────────────────────

st.markdown("""
<style>
    .metric-card {background:#1e2130;border-radius:12px;padding:20px;text-align:center}
    .job-card {background:#1e2130;border-left:4px solid #00c9a7;border-radius:8px;padding:16px;margin:8px 0}
    .badge {display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;margin:2px}
    .badge-indian {background:#00c9a720;color:#00c9a7}
    .badge-intl   {background:#4f8bff20;color:#4f8bff}
    .badge-budget {background:#ff9f4320;color:#ff9f43}
</style>
""", unsafe_allow_html=True)


# ── Header ────────────────────────────────────────────────────

_indian_names = " · ".join(sorted(INDIAN_PLATFORMS))
_intl_names   = " · ".join(sorted(INTL_PLATFORMS))

st.title("🤖 JK Data Lab — Job Search Agent")
st.caption(
    f"Owner: Kinjal Jayantkumar Jayswal | "
    f"Portals: {len(INDIAN_PLATFORMS)} Indian 🇮🇳 ({_indian_names}) + "
    f"{len(INTL_PLATFORMS)} International 🌐 ({_intl_names}) | "
    f"Last refreshed: {datetime.now().strftime('%H:%M:%S')}"
)

# ── Controls ──────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns([1, 1, 1.4, 1.4])
with col1:
    if st.button("🔄 Refresh"):
        st.rerun()
with col2:
    run_now = st.button("▶️ Run Scan")
with col3:
    salary_min = st.number_input(
        "Min expected budget", min_value=0, value=0, step=500,
        help="0 = no minimum. Budgets are mixed currency (₹/$) across platforms — treated as a loose guide, not exact.",
    )
with col4:
    salary_max = st.number_input(
        "Max expected budget", min_value=0, value=0, step=500,
        help="0 = no maximum. Applied as an AI scoring hint, not a hard filter.",
    )

if run_now:
    cmd = [sys.executable, "agent.py", "--once"]
    if salary_min:
        cmd += ["--salary-min", str(salary_min)]
    if salary_max:
        cmd += ["--salary-max", str(salary_max)]
    with st.spinner("Scanning portals in parallel — usually done in ~60 seconds..."):
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=240
        )
        st.success("Scan complete!")
        if result.stdout:
            st.code(result.stdout[-1500:])

st.divider()

# ── Metrics ───────────────────────────────────────────────────

jobs = load_jobs()

total  = len(jobs)
indian = sum(1 for j in jobs if j.get("platform") in INDIAN_PLATFORMS)
intl   = sum(1 for j in jobs if j.get("platform") in INTL_PLATFORMS)
high   = sum(1 for j in jobs if j.get("ai_score", 0) >= 8)

m1, m2, m3, m4 = st.columns(4)
m1.metric("📋 Total Jobs",          total)
m2.metric("🇮🇳 Indian Portals",     indian)
m3.metric("🌐 International",       intl)
m4.metric("⭐ AI Score ≥ 8",        high)

# Per-platform breakdown
with st.expander("📊 Jobs per portal"):
    counts = {}
    for p in ALL_PLATFORMS:
        c = sum(1 for j in jobs if j.get("platform") == p)
        if c:
            counts[p] = c
    if counts:
        df_counts = pd.DataFrame(
            [{"Portal": f"{PLATFORM_FLAGS.get(p,'🌐')} {p}", "Jobs Found": c}
             for p, c in sorted(counts.items(), key=lambda x: -x[1])]
        )
        st.dataframe(df_counts, use_container_width=True, hide_index=True)
    else:
        st.info("No jobs found yet.")

st.divider()

# ── Filters ───────────────────────────────────────────────────

col_f1, col_f2, col_f3, col_f4 = st.columns(4)
with col_f1:
    region = st.multiselect("Region", ["🇮🇳 Indian", "🌐 International"],
                             default=["🇮🇳 Indian", "🌐 International"])
with col_f2:
    plat_filter = st.multiselect("Portal", ALL_PLATFORMS, default=ALL_PLATFORMS)
with col_f3:
    min_score = st.slider("Min AI Score", 0, 10, 3)
with col_f4:
    sort_by = st.selectbox("Sort by", ["AI Score ↓", "Newest ↓"])

# Apply filters
def _region_ok(job):
    p = job.get("platform", "")
    if "🇮🇳 Indian" in region and p in INDIAN_PLATFORMS:
        return True
    if "🌐 International" in region and p in INTL_PLATFORMS:
        return True
    return False

filtered = [
    j for j in jobs
    if j.get("platform") in plat_filter
    and _region_ok(j)
    and j.get("ai_score", 0) >= min_score
]

if sort_by == "AI Score ↓":
    filtered.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
else:
    filtered.sort(key=lambda x: x.get("found_at", ""), reverse=True)

st.subheader(f"📌 Matching Jobs ({len(filtered)})")

# ── Job cards ─────────────────────────────────────────────────

if not filtered:
    st.info("No jobs found yet. Run a scan or wait for the background agent.")
else:
    for job in filtered:
        score    = job.get("ai_score", 0)
        platform = job.get("platform", "")
        color    = PLATFORM_COLORS.get(platform, "#aaa")
        flag     = PLATFORM_FLAGS.get(platform, "🌐")
        badge_cls = "badge-indian" if platform in INDIAN_PLATFORMS else "badge-intl"
        job_id   = job.get("id", "")

        score_color = "#00c9a7" if score >= 8 else "#ff9f43" if score >= 6 else "#aaa"

        st.markdown(f"""
        <div class="job-card" style="border-color:{color}">
            <div style="display:flex;justify-content:space-between;align-items:start">
                <div>
                    <strong style="font-size:16px">{job['title']}</strong><br>
                    <span class="badge {badge_cls}">{flag} {platform}</span>
                    <span class="badge badge-budget">💰 {job.get('budget','N/A')}</span>
                </div>
                <div style="text-align:right">
                    <span style="font-size:28px;font-weight:700;color:{score_color}">{score}</span>
                    <span style="color:#888;font-size:12px">/10</span>
                </div>
            </div>
            <p style="color:#aaa;margin:8px 0 4px 0;font-size:13px">{job.get('description','')[:200]}...</p>
            <p style="color:#888;font-size:12px">🤖 {job.get('ai_reason','')}</p>
            <span style="color:#555;font-size:11px">Found: {job.get('found_at','')[:16]}</span>
        </div>
        """, unsafe_allow_html=True)

        col_link, col_btn, col_status = st.columns([2, 1, 1])
        with col_link:
            st.markdown(f"[🔗 View Job →]({job.get('link', '#')})")
        with col_btn:
            already_sent = job_id in st.session_state.notified
            if not already_sent:
                if st.button("📱 Send Alert", key=f"notify_{job_id}"):
                    try:
                        notify(
                            job,
                            whatsapp_number=config.WHATSAPP_NUMBER,
                            telegram_token=config.TELEGRAM_BOT_TOKEN,
                            telegram_chat=config.TELEGRAM_CHAT_ID,
                        )
                        st.session_state.notified.add(job_id)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Alert failed: {e}")
        with col_status:
            if job_id in st.session_state.notified:
                st.success("✅ Sent")

st.divider()

# ── Table view ────────────────────────────────────────────────

with st.expander("📊 Table View"):
    if filtered:
        df = pd.DataFrame(filtered)
        cols = [c for c in ["title", "platform", "budget", "ai_score", "ai_reason", "found_at", "link"] if c in df.columns]
        df = df[cols]
        df.columns = [c.replace("_", " ").title() for c in cols]
        st.dataframe(df, use_container_width=True)

# ── Logs ──────────────────────────────────────────────────────

with st.expander("📋 Agent Logs (last 50 lines)"):
    st.code(load_log_tail(50), language="text")
