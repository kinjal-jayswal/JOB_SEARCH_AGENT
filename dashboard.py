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

# ─── PAGE CONFIG ─────────────────────────────────────────────
st.set_page_config(
    page_title="JK Data Lab — Job Agent",
    page_icon="🤖",
    layout="wide",
)

JOBS_FILE = "jobs_found.json"
LOG_FILE  = "agent.log"


# ─── LOAD DATA ───────────────────────────────────────────────
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


# ─── HEADER ──────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {background:#1e2130;border-radius:12px;padding:20px;text-align:center}
    .job-card {background:#1e2130;border-left:4px solid #00c9a7;border-radius:8px;padding:16px;margin:8px 0}
    .badge {display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600}
    .badge-green {background:#00c9a720;color:#00c9a7}
    .badge-blue  {background:#4f8bff20;color:#4f8bff}
    .badge-orange{background:#ff9f4320;color:#ff9f43}
</style>
""", unsafe_allow_html=True)

st.title("🤖 JK Data Lab — Job Search Agent")
st.caption(f"Owner: Kinjal Jayantkumar Jayswal | Last refreshed: {datetime.now().strftime('%H:%M:%S')}")

# ─── CONTROLS ────────────────────────────────────────────────
col1, col2, col3 = st.columns([1, 1, 4])
with col1:
    if st.button("🔄 Refresh Dashboard"):
        st.rerun()
with col2:
    run_now = st.button("▶️ Run Scan Now")

if run_now:
    with st.spinner("Running scan..."):
        result = subprocess.run(
            [sys.executable, "agent.py", "--once"],
            capture_output=True, text=True, timeout=120
        )
        st.success("Scan complete!")
        if result.stdout:
            st.code(result.stdout[-1000:])

st.divider()

# ─── JOBS ────────────────────────────────────────────────────
jobs = load_jobs()

# Metrics
total  = len(jobs)
tl     = sum(1 for j in jobs if j.get("platform") == "Truelancer")
fl     = sum(1 for j in jobs if j.get("platform") == "Freelancer.com")
high   = sum(1 for j in jobs if j.get("ai_score", 0) >= 8)

m1, m2, m3, m4 = st.columns(4)
m1.metric("📋 Total Jobs Found", total)
m2.metric("🟢 Truelancer",       tl)
m3.metric("🔵 Freelancer.com",   fl)
m4.metric("⭐ Score ≥ 8",        high)

st.divider()

# Filters
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    plat_filter = st.multiselect("Platform", ["Truelancer", "Freelancer.com"], default=["Truelancer", "Freelancer.com"])
with col_f2:
    min_score = st.slider("Min AI Score", 0, 10, 6)
with col_f3:
    sort_by = st.selectbox("Sort by", ["AI Score ↓", "Newest ↓"])

# Apply filters
filtered = [
    j for j in jobs
    if j.get("platform") in plat_filter
    and j.get("ai_score", 0) >= min_score
]

if sort_by == "AI Score ↓":
    filtered.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
else:
    filtered.sort(key=lambda x: x.get("found_at", ""), reverse=True)

st.subheader(f"📌 Matching Jobs ({len(filtered)})")

if not filtered:
    st.info("No jobs found yet. Run a scan or wait for the background agent.")
else:
    for job in filtered:
        score = job.get("ai_score", 0)
        color = "#00c9a7" if score >= 8 else "#ff9f43" if score >= 6 else "#aaa"
        platform_badge = "badge-green" if job["platform"] == "Truelancer" else "badge-blue"

        st.markdown(f"""
        <div class="job-card" style="border-color:{color}">
            <div style="display:flex;justify-content:space-between;align-items:start">
                <div>
                    <strong style="font-size:16px">{job['title']}</strong><br>
                    <span class="badge {platform_badge}">{job['platform']}</span>
                    &nbsp;
                    <span class="badge badge-orange">💰 {job.get('budget','N/A')}</span>
                </div>
                <div style="text-align:right">
                    <span style="font-size:28px;font-weight:700;color:{color}">{score}</span>
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

# ─── TABLE VIEW ──────────────────────────────────────────────
with st.expander("📊 Table View"):
    if filtered:
        df = pd.DataFrame(filtered)[["title", "platform", "budget", "ai_score", "ai_reason", "found_at", "link"]]
        df.columns = ["Title", "Platform", "Budget", "AI Score", "Reason", "Found At", "Link"]
        st.dataframe(df, use_container_width=True)

# ─── LOGS ────────────────────────────────────────────────────
with st.expander("📋 Agent Logs (last 50 lines)"):
    st.code(load_log_tail(50), language="text")
