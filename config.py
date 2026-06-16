# ============================================================
# JK Data Lab — Job Search AI Agent Config
# Owner: Kinjal Jayantkumar Jayswal
# ============================================================

# Your WhatsApp / Telegram number
WHATSAPP_NUMBER = "+919157938887"
TELEGRAM_BOT_TOKEN = ""   # Fill in after creating bot via @BotFather
TELEGRAM_CHAT_ID   = ""   # Fill in after /start with your bot

# How often to scan (minutes)
SCAN_INTERVAL_MINUTES = 120   # every 2 hours

# Keywords to MATCH (any one is enough)
KEYWORDS = [
    "python", "ai", "artificial intelligence", "machine learning", "ml",
    "data science", "langchain", "rag", "llm", "openai", "nlp",
    "streamlit", "fastapi", "etl", "automation", "scraping",
    "chatbot", "agent", "data analyst", "deep learning", "huggingface",
]

# Min client rating (Truelancer uses 1-5)
MIN_CLIENT_RATING = 4.0

# Min client paid projects
MIN_PAID_PROJECTS = 3

# Max budget threshold to skip zero-rating clients
ZERO_RATING_BUDGET_LIMIT = 5000   # INR

# State file to track seen jobs (no duplicates)
STATE_FILE = "seen_jobs.json"

# Streamlit dashboard data file
JOBS_FILE = "jobs_found.json"

# Log file
LOG_FILE = "agent.log"
