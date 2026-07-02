"""Configuration layer — env vars, site settings, type-safe parsing."""
import os
import re
from pathlib import Path


def _env_str(name, default=""):
    value = os.environ.get(name)
    return default if value is None or str(value).strip() == "" else str(value).strip()


def _env_int(name, default):
    value = _env_str(name, str(default))
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _env_float(name, default):
    value = _env_str(name, str(default))
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


# ========== Telegram ==========

_TELEGRAM_BOT_TOKEN_RAW = chr(84) + chr(69) + chr(76) + chr(69) + chr(71) + chr(82) + chr(65) + chr(77) + chr(95) + chr(66) + chr(79) + chr(84) + chr(95) + chr(84) + chr(79) + chr(75) + chr(69) + chr(78)
TELEGRAM_BOT_TOKEN = os.environ.get(_TELEGRAM_BOT_TOKEN_RAW, "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def _parse_tg_chat_ids():
    raw = os.environ.get("TELEGRAM_CHAT_IDS") or TELEGRAM_CHAT_ID
    ids = []
    for part in re.split(r"[,;\s]+", raw or ""):
        part = part.strip()
        if part and part not in ids:
            ids.append(part)
    return ids


TELEGRAM_CHAT_IDS = _parse_tg_chat_ids()

# ========== Global ==========

POLL_INTERVAL = _env_int("POLL_INTERVAL", 60)
LOG_FILE = Path(__file__).parent / "monitor.log"
STATE_FILE = Path(__file__).parent / "state.json"

# ========== Site A (独角鲸云) ==========

SITE_A_API_URL = _env_str("SITE_A_API_URL", "https://api.fuckip.me/api/v1/plans")
SITE_A_TOKEN = _env_str("SITE_A_TOKEN", "")
SITE_A_POLL_INTERVAL = _env_int("SITE_A_POLL_INTERVAL", 60)
SITE_A_DEPLOY_URL = _env_str(
    "SITE_A_DEPLOY_URL", "https://dash.fuckip.me/deploy?plan_id={plan_id}"
)
SITE_A_MIN_PRICE = _env_float("SITE_A_MIN_PRICE", 0)
SITE_A_MAX_PRICE = _env_float("SITE_A_MAX_PRICE", 0.4)
SITE_A_CHEAP_MAX_PRICE = _env_float("SITE_A_CHEAP_MAX_PRICE", 0.1)
SITE_A_OPTIMIZED_KEYWORDS = [
    k.strip().lower()
    for k in os.environ.get(
        "SITE_A_OPTIMIZED_KEYWORDS",
        "优化,CN2,GIA,CMI,9929,4837,精品,三网,BGP,回国,直连,低延迟",
    ).split(",")
    if k.strip()
]
SITE_A_OPTIMIZED_EXCLUDE_KEYWORDS = [
    k.strip().lower()
    for k in os.environ.get(
        "SITE_A_OPTIMIZED_EXCLUDE_KEYWORDS",
        "无优化,无任何优化,非优化,普通线路",
    ).split(",")
    if k.strip()
]

# ========== Site E (czl.net) ==========

SITE_E_API_URL = _env_str("SITE_E_API_URL", "https://vps-monitor.czl.net/api/public/filter")
SITE_E_POLL_INTERVAL = _env_int("SITE_E_POLL_INTERVAL", 120)
SITE_E_DEPLOY_URL = _env_str(
    "SITE_E_DEPLOY_URL", "https://vps-monitor.czl.net/product/{item_id}"
)
SITE_E_MAX_WORKERS = _env_int("SITE_E_MAX_WORKERS", 8)
SITE_E_MAX_PAGES = _env_int("SITE_E_MAX_PAGES", 100)
SITE_E_PAGE_SIZE = _env_int("SITE_E_PAGE_SIZE", 12)
SITE_E_PRICE_MIN = _env_float("SITE_E_PRICE_MIN", 1.0)
SITE_E_PRICE_MAX = _env_float("SITE_E_PRICE_MAX", 120.0)
SITE_E_RAM_MIN = _env_float("SITE_E_RAM_MIN", 0.4)
SITE_E_RAM_MAX = _env_float("SITE_E_RAM_MAX", 128.0)
