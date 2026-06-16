# 🤖 JK Data Lab — Job Search AI Agent

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35%2B-red)
![Claude AI](https://img.shields.io/badge/AI-Claude%20Sonnet-purple)
![License](https://img.shields.io/badge/License-MIT-green)

> Autonomous job search agent that scrapes Truelancer & Freelancer.com every 2 hours, scores each listing with Claude AI, and sends instant Telegram or WhatsApp alerts — with a live Streamlit dashboard.

---

## What It Does

- **Scrapes** Truelancer and Freelancer.com for Python / AI / ML / LangChain / Data Science jobs
- **Filters** by keyword match and minimum client rating (4.0★)
- **Scores** every job 1–10 with Claude Sonnet, auto-applying for scores ≥ 7
- **Alerts** you in real time via Telegram Bot or WhatsApp Web (pywhatkit)
- **Visualises** all matched jobs on a searchable, sortable Streamlit dashboard at `http://localhost:8501`

---

## Architecture

```
┌──────────────┐     every 2 hrs      ┌──────────────────┐
│  agent.py    │ ──── run_scan() ────► │  scraper.py      │
│  (scheduler) │                       │  Truelancer +    │
└──────┬───────┘                       │  Freelancer.com  │
       │ raw_jobs                      └────────┬─────────┘
       ▼                                        │ job list
┌──────────────┐   scored_jobs    ┌─────────────▼────────┐
│ ai_filter.py │ ◄──────────────  │  keyword & client    │
│ Claude API   │                  │  quality filters      │
└──────┬───────┘                  └──────────────────────┘
       │ apply=True
       ▼
┌──────────────┐    jobs_found.json
│ notifier.py  │ ──────────────────► dashboard.py (Streamlit)
│ Telegram /   │
│ WhatsApp     │
└──────────────┘
```

---

## Quick Start

### 1. Clone & install

```bash
git clone <repo-url>
cd Job_search_agent

python -m venv venv
# Windows
.\venv\Scripts\Activate.ps1
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure

Edit [config.py](config.py):

```python
TELEGRAM_BOT_TOKEN = "1234567890:ABC..."   # from @BotFather
TELEGRAM_CHAT_ID   = "9876543210"          # from /getUpdates
WHATSAPP_NUMBER    = "+91XXXXXXXXXX"       # your number with country code
```

### 3. Run

**All-in-one (Linux/macOS):**
```bash
bash start.sh
```

**Windows (separate terminals):**
```powershell
# Terminal 1 — background agent
python agent.py

# Terminal 2 — dashboard
streamlit run dashboard.py
```

Dashboard opens at **http://localhost:8501**

Stop everything:
```bash
bash stop.sh
```

---

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `SCAN_INTERVAL_MINUTES` | `120` | How often to scrape (minutes) |
| `MIN_CLIENT_RATING` | `4.0` | Minimum Truelancer client rating |
| `ZERO_RATING_BUDGET_LIMIT` | `5000` | Skip unrated clients above this budget (INR) |
| `KEYWORDS` | `python, ai, ml, ...` | Any match triggers candidate status |
| `TELEGRAM_BOT_TOKEN` | `""` | Create via @BotFather on Telegram |
| `TELEGRAM_CHAT_ID` | `""` | Your personal Telegram chat ID |
| `WHATSAPP_NUMBER` | `+91...` | Your WhatsApp number (with country code) |

---

## Project Structure

```
Job_search_agent/
├── agent.py          # Main scheduler — runs scan loop every 2 hours
├── scraper.py        # Scrapes Truelancer & Freelancer.com (API + HTML)
├── ai_filter.py      # Claude Sonnet scores each job 1–10
├── notifier.py       # Sends Telegram Bot / WhatsApp Web alerts
├── dashboard.py      # Streamlit UI — view, filter, and sort matched jobs
├── config.py         # All settings (edit this before first run)
├── start.sh          # Launches agent + dashboard in background
├── stop.sh           # Kills both processes
├── requirements.txt  # Python dependencies
├── jobs_found.json   # Matched jobs store (auto-created)
├── seen_jobs.json    # Dedup tracker (auto-created)
└── agent.log         # Full scan log (auto-created)
```

---

## Requirements

| Package | Purpose |
|---------|---------|
| `schedule` | Cron-style job scheduling for the scan loop |
| `requests` | HTTP calls to Freelancer API and Telegram Bot API |
| `beautifulsoup4` | HTML parsing of Truelancer and Freelancer pages |
| `lxml` | Fast HTML parser used by BeautifulSoup |
| `streamlit` | Web dashboard UI |
| `pandas` | DataFrame for the dashboard table view |
| `pywhatkit` | WhatsApp Web automation for message delivery |

---

## Setting Up Telegram (Recommended)

Telegram works headlessly — no browser required, ideal for servers.

1. Open Telegram → search **@BotFather** → send `/newbot`
2. Copy the token → paste into `TELEGRAM_BOT_TOKEN` in `config.py`
3. Start a chat with your bot → send `/start`
4. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` → copy `chat.id`
5. Paste into `TELEGRAM_CHAT_ID` in `config.py`

---

## WhatsApp Alerts (Optional)

WhatsApp via `pywhatkit` requires Chrome and an active WhatsApp Web session:

1. Open Chrome → go to [web.whatsapp.com](https://web.whatsapp.com) → scan QR
2. Keep Chrome open while the agent runs
3. Your number `+91 9157938887` is already set in `config.py`

> Telegram is more reliable for background/headless use.

---

## How AI Scoring Works

Each candidate job is sent to **Claude Sonnet** (`claude-sonnet-4-6`) with a system prompt describing JK Data Lab's service portfolio. Claude returns a JSON array with a `score` (1–10) and `reason` per job. Scores ≥ 7 trigger an alert. If the API is unavailable, a keyword-hit fallback scores locally.

---

## License

MIT © [Kinjal Jayantkumar Jayswal](mailto:jayswal1bsnl@gmail.com)

---

<p align="center">
  Built by <strong>Kinjal Jayantkumar Jayswal</strong> · JK Data Lab · June 2026
</p>
