"""Telegram notification — send message to registered chat IDs."""
import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS
from core.logging import log


def _paginate_push(title, items, formatter, page_size=8):
    """Paginate long lists to avoid Telegram's 4096-char limit."""
    if not items:
        return 0
    full = formatter(items)
    if len(full) <= 4000:
        return 1 if send_tg(full) else 0
    sent_count = 0
    total_pages = (len(items) + page_size - 1) // page_size
    for i in range(0, len(items), page_size):
        chunk = items[i : i + page_size]
        msg = formatter(chunk)
        page_no = i // page_size + 1
        msg = msg.replace(title, f"{title} (第 {page_no}/{total_pages} 页)", 1)
        if send_tg(msg):
            sent_count += 1
    return sent_count


def send_tg(text):
    """Push HTML message to all registered Telegram chat IDs.

    Fails silently: logs warning if token/chat missing, logs error on API failure.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        log.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS missing; skip push")
        return False
    ok_count = 0
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            result = r.json()
            if result.get("ok"):
                ok_count += 1
                log.info("TG push OK: chat_id=%s chars=%d", chat_id, len(text))
            else:
                log.error("TG push failed: chat_id=%s result=%s", chat_id, result)
        except Exception as e:
            log.exception("TG push error: chat_id=%s error=%s", chat_id, e)
    return ok_count > 0
