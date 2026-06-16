#!/bin/bash
# ============================================================
# JK Data Lab — Job Search Agent Launcher
# ============================================================
# Usage: bash start.sh
# Starts agent in background + opens dashboard in browser

cd "$(dirname "$0")"

echo "============================================"
echo "  JK Data Lab — Job Search Agent"
echo "  Owner: Kinjal Jayantkumar Jayswal"
echo "============================================"

# Install dependencies if needed
echo "📦 Checking dependencies..."
pip install requests beautifulsoup4 schedule streamlit plotly pandas \
    python-telegram-bot==13.15 lxml pywhatkit --break-system-packages -q

# Kill any existing agent
pkill -f "python agent.py" 2>/dev/null
pkill -f "streamlit run dashboard.py" 2>/dev/null
sleep 1

# Start background agent
echo "🤖 Starting background agent (scans every 2 hours)..."
nohup python agent.py > /dev/null 2>&1 &
echo "   Agent PID: $!"

# Start dashboard
echo "📊 Starting dashboard at http://localhost:8501 ..."
sleep 2
streamlit run dashboard.py --server.port 8501 --server.headless true &

echo ""
echo "✅ Everything running!"
echo "   Dashboard → http://localhost:8501"
echo "   Logs      → tail -f agent.log"
echo "   Stop all  → bash stop.sh"
