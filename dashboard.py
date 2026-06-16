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

st.set_page_config(
    page_title="JK Data Lab — Job Agent",
    page_icon="🤖",
    layout="wide",
)

JOBS_FILE = "jobs_found.json"
LOG_FILE  = "agent.log"

# ── Platform config ───────────────────────────────────────────
INDIAN_PLATFORMS = {"Truelancer", "Internshala", "Worknhire"}
INTL_PLATFORMS   = {"Freelancer.com", "Guru.com", "RemoteOK", "PeoplePerHour", "Hubstaff Talent"}
ALL_PLATFORMS    = sorted(INDIAN_PLATFORMS | INTL_PLATFORMS)

PLATFORM_COLORS = {
    # Indian
    "Truelancer":   "#00c9a7",
    "Internshala":  "#00b4d8",
    "Worknhire":    "#0077b6",
    # International
    "Freelancer.com":  "#4f8bff",
    "Guru.com":        "#a855f7",
    "RemoteOK":        "#22c55e",
    "PeoplePerHour":   "#f97316",
    "Hubstaff Talent": "#eab308",
}

PLATFORM_FLAGS = {
    "Truelancer":      "🇮🇳",
    "Internshala":     "🇮🇳",
    "Worknhire":       "🇮🇳",
    "Freelancer.com":  "🌐",
    "Guru.com":        "🌐",
    "RemoteOK":        "🌐",
    "PeoplePerHour":   "🌐",
    "Hubstaff Talent": "🌐",
}


# ── Data helpers ──────────────────────────────────────────────

def load_jobs():
    if not os.path.exists(JOBS_FILE):
        return []
    with open(JOBS_FILE) as f:
        return json.load(f)


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

st.title("🤖 JK Data Lab — Job Search Agent")
st.caption(
    f"Owner: Kinjal Jayantkumar Jayswal | "
    f"Portals: 3 Indian 🇮🇳 + 5 International 🌐 | "
    f"Last refreshed: {datetime.now().strftime('%H:%M:%S')}"
)

# ── Controls ──────────────────────────────────────────────────

col1, col2, col3 = st.columns([1, 1, 4])
with col1:
    if st.button("🔄 Refresh"):
        st.rerun()
with col2:
    run_now = st.button("▶️ Run Scan")

if run_now:
    with st.spinner("Running scan across all 8 portals..."):
        result = subprocess.run(
            [sys.executable, "agent.py", "--once"],
            capture_output=True, text=True, timeout=300
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
    min_score = st.slider("Min AI Score", 0, 10, 6)
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

        # Score colour
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
            <a href="{job.get('link','#')}" target="_blank" style="color:#4f8bff;font-size:13px">🔗 View Job →</a>
            &nbsp;&nbsp;
            <span style="color:#555;font-size:11px">Found: {job.get('found_at','')[:16]}</span>
        </div>
        """, unsafe_allow_html=True)

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
