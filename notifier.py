"""
notifier.py — Send WhatsApp & Telegram alerts for new matching jobs.
WhatsApp: uses web.whatsapp.com automation (pywhatkit) — FREE
Telegram: uses Bot API — FREE
"""

import logging
import time
import os

logger = logging.getLogger("JobAgent")


# ─── WHATSAPP ────────────────────────────────────────────────

def send_whatsapp(job: dict, phone: str):
    """
    Send WhatsApp message using pywhatkit.
    NOTE: Requires Chrome + WhatsApp Web to be linked on this machine.
    For server/background use, Telegram is more reliable.
    """
    try:
        import pywhatkit as kit
        from datetime import datetime, timedelta

        # Schedule 1 minute from now (pywhatkit needs a future time)
        now = datetime.now() + timedelta(minutes=1)
        msg = _format_message(job)

        kit.sendwhatmsg(
            phone_no=phone,
            message=msg,
            time_hour=now.hour,
            time_min=now.minute,
            wait_time=15,
            tab_close=True,
            close_time=3,
        )
        logger.info(f"WhatsApp sent for: {job['title'][:40]}")
        return True

    except ImportError:
        logger.warning("pywhatkit not installed — skipping WhatsApp")
        return False
    except Exception as e:
        logger.error(f"WhatsApp error: {e}")
        return False


# ─── TELEGRAM ────────────────────────────────────────────────

def send_telegram(job: dict, bot_token: str, chat_id: str):
    """Send Telegram message via Bot API."""
    if not bot_token or not chat_id:
        logger.debug("Telegram not configured — skipping")
        return False

    import requests
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    msg = _format_message(job)

    try:
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }, timeout=10)
        r.raise_for_status()
        logger.info(f"Telegram sent: {job['title'][:40]}")
        return True
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


# ─── FORMAT ──────────────────────────────────────────────────

def _format_message(job: dict) -> str:
    score = job.get("ai_score", "?")
    stars = "⭐" * min(int(score), 5) if isinstance(score, (int, float)) else ""

    budget = job.get("budget", "N/A")
    rating = job.get("client_rating")
    rating_str = f"⭐ {rating}" if rating else "N/A"

    return (
        f"🚀 <b>New Job Match!</b>\n\n"
        f"📌 <b>{job['title']}</b>\n"
        f"🏢 Platform: {job['platform']}\n"
        f"💰 Budget: {budget}\n"
        f"👤 Client Rating: {rating_str}\n"
        f"🤖 AI Score: {score}/10 {stars}\n"
        f"💡 {job.get('ai_reason','')}\n\n"
        f"🔗 {job.get('link','')}"
    )


def notify(job: dict, whatsapp_number: str, telegram_token: str, telegram_chat: str):
    """Try Telegram first (more reliable headless), then WhatsApp."""
    sent = False
    if telegram_token and telegram_chat:
        sent = send_telegram(job, telegram_token, telegram_chat)
    if not sent:
        send_whatsapp(job, whatsapp_number)
