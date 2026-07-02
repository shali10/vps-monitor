#!/usr/bin/env python3
"""
VPS商品/库存监控 → Telegram 推送 (模块化重构版)

本模块为向后兼容的入口 shim。实际逻辑已拆分至 core/ + sites/。
新代码请直接从具体模块 import:

    from sites.site_a import monitor_site_a, fetch_site_a
    from sites.site_e import monitor_site_e, fetch_site_e
    from core.utils import _parse_usd_year_e
    from core.notify import send_tg
    from core.state import load_state, save_state
    from config import SITE_A_TOKEN

Site A: 独角鲸云 (Bearer auth, paginated)
Site E: czl.net (public API, pool-filtered)

Entry point: python main.py [--once] [--site a|e|all]
"""
# Re-export everything from submodules for backward compatibility with tests
from config import *  # noqa: F401,F403  — env vars, site config
from core.logging import log  # noqa: F401
from core.notify import _paginate_push, send_tg  # noqa: F401
from core.state import load_state, save_state  # noqa: F401
from core.utils import (  # noqa: F401
    CN_KEYWORDS,
    _fmt_bytes,
    _fmt_cny,
    _fmt_monthly_traffic,
    _fmt_ram_mb,
    _fmt_usd,
    _html_attr,
    _html_escape,
    _parse_ram_gb_e,
    _parse_usd_year_e,
    _site_e_get_keywords,
    _site_e_pool_match,
    _site_e_price_in_whitelist,
)
from main import main  # noqa: F401
from sites.site_a import (  # noqa: F401
    _notify_a_group_by_rule,
    _notify_a_send_one,
    _site_a_available,
    _site_a_footer,
    _site_a_format,
    _site_a_group_by_mer,
    _site_a_has_optimized_route,
    _site_a_match_rules,
    _site_a_prev_available,
    _site_a_price_in_cheap_any_range,
    _site_a_price_in_range,
    _site_a_price_value,
    _site_a_route_intro,
    _site_a_state_item,
    _site_a_stock_available,
    _site_a_text_blob,
    compare_site_a,
    fetch_site_a,
    monitor_site_a,
    notify_site_a_new_arrival,
    notify_site_a_restocked,
)
from sites.site_e import (  # noqa: F401
    _fetch_site_e_page,
    _site_e_format_item,
    _site_e_id,
    _site_e_is_vps,
    _site_e_signature,
    compare_site_e,
    fetch_site_e,
    monitor_site_e,
    notify_site_e_new,
    notify_site_e_price_drops,
    notify_site_e_restock,
)

__all__ = [
    # config
    "SITE_A_API_URL", "SITE_A_TOKEN", "SITE_A_POLL_INTERVAL", "SITE_A_DEPLOY_URL",
    "SITE_A_MAX_PRICE", "SITE_A_CHEAP_MAX_PRICE", "SITE_A_OPTIMIZED_KEYWORDS",
    "SITE_A_OPTIMIZED_EXCLUDE_KEYWORDS",
    "SITE_E_API_URL", "SITE_E_POLL_INTERVAL", "SITE_E_DEPLOY_URL",
    "POLL_INTERVAL", "LOG_FILE", "STATE_FILE",
    # core/logging
    "log",
    # core/state
    "load_state", "save_state",
    # core/notify
    "send_tg", "_paginate_push",
    # core/utils
    "_fmt_bytes", "_fmt_cny", "_fmt_usd", "_html_escape", "_html_attr",
    "_fmt_ram_mb", "_fmt_monthly_traffic",
    "_parse_ram_gb_e", "_parse_usd_year_e",
    "_site_e_get_keywords", "_site_e_price_in_whitelist", "_site_e_pool_match",
    # sites/site_a
    "fetch_site_a", "_site_a_route_intro", "_site_a_format", "_site_a_footer",
    "_site_a_group_by_mer", "_site_a_text_blob",
    "_site_a_has_optimized_route", "_site_a_price_value",
    "_site_a_price_in_range", "_site_a_price_in_cheap_any_range",
    "_site_a_match_rules", "_site_a_stock_available", "_site_a_available",
    "_site_a_prev_available", "_site_a_state_item",
    "compare_site_a", "_notify_a_group_by_rule", "_notify_a_send_one",
    "notify_site_a_restocked", "notify_site_a_new_arrival", "monitor_site_a",
    # sites/site_e
    "_fetch_site_e_page", "fetch_site_e",
    "_site_e_id", "_site_e_signature", "_site_e_is_vps",
    "compare_site_e", "_site_e_format_item",
    "notify_site_e_new", "notify_site_e_restock", "notify_site_e_price_drops",
    "monitor_site_e",
    # main
    "main",
]
