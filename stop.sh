#!/bin/bash
echo "Stopping JK Data Lab Job Agent..."
pkill -f "python agent.py"
pkill -f "streamlit run dashboard.py"
echo "✅ Stopped."
