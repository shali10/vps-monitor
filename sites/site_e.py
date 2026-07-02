"""Site E: vps-monitor.czl.net — public API with pool-based filtering."""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from config import (
    SITE_E_API_URL,
    SITE_E_DEPLOY_URL,
    SITE_E_MAX_PAGES,
    SITE_E_MAX_WORKERS,
    SITE_E_PAGE_SIZE,
)
from core.notify import send_tg
from core.utils import (
    _html_attr,
    _html_escape,
    _parse_ram_gb_e,
    _parse_usd_year_e,
    _site_e_get_keywords,
    _site_e_pool_match,
    _site_e_price_in_whitelist,
)

log = logging.getLogger("vps-monitor")


def _site_e_is_vps(item):
    """Filter out dedicated servers."""
    text = (item.get("title", "") + " " + item.get("disk", "")).lower()
    return not any(b in text for b in ["dedicated", "dedi", "独立服", "独立服务器"])


def _fetch_site_e_page(page):
    """Fetch single page, return (page, dict_or_None). Exception → None."""
    try:
        r = requests.get(
            SITE_E_API_URL,
            params={"page": page, "pageSize": SITE_E_PAGE_SIZE},
            timeout=15,
        )
        r.raise_for_status()
        return page, r.json()
    except Exception as e:
        log.warning("site-e fetch page %d failed: %s", page, e)
        return page, None


def fetch_site_e():
    """Concurrent paginated fetch with retry. Returns filtered item list."""
    if not SITE_E_API_URL:
        log.debug("site-e skipped (SITE_E_API_URL not configured)")
        return []

    def _one_round(page_list):
        out = {}
        with ThreadPoolExecutor(max_workers=SITE_E_MAX_WORKERS) as ex:
            futures = {ex.submit(_fetch_site_e_page, p): p for p in page_list}
            for fut in as_completed(futures):
                page, d = fut.result()
                if d is not None:
                    out[page] = d
        return out

    all_pages = list(range(1, SITE_E_MAX_PAGES + 1))
    round1 = _one_round(all_pages)
    failed = [p for p in all_pages if p not in round1]
    if failed:
        log.info("site-e: retrying %d failed pages after 1s...", len(failed))
        time.sleep(1)
        round2 = _one_round(failed)
        for page, data in round2.items():
            round1[page] = data

    # Flatten pages → items
    items = []
    for page_num in sorted(round1.keys()):
        body = round1[page_num]
        rows = body.get("data", body) if isinstance(body, dict) else body
        if isinstance(rows, dict):
            rows = rows.get("items", rows.get("rows", []))
        if isinstance(rows, list):
            items.extend(rows)

    # Filter: real VPS + in whitelist
    filtered = []
    for item in items:
        if not _site_e_is_vps(item):
            continue
        if not _site_e_price_in_whitelist(item):
            continue
        filtered.append(item)

    log.info("site-e: fetched %d raw → %d after filter", len(items), len(filtered))
    return filtered


def _site_e_id(item):
    """Stable unique ID for diff tracking."""
    return str(item.get("id") or item.get("item_id") or item.get("uuid") or item.get("title") or "unknown")


def _site_e_signature(item):
    """State snapshot for diff: soldOut/price/stock."""
    sold_out = item.get("soldOut")
    if sold_out is None:
        stock = item.get("stock", item.get("available", item.get("remaining")))
        sold_out = stock is not None and int(stock or 0) <= 0
    return {
        "soldOut": bool(sold_out),
        "price": item.get("price"),
        "ram": item.get("ram", item.get("memory")),
    }


def compare_site_e(state, items):
    """Diff old signatures vs new items. Returns (new_arrivals, restocked, price_drops, new_state)."""
    old = state.get("items", {})
    new_state = {}
    cur_ids = set()

    new_arrivals, restocked, price_drops = [], [], []

    for item in items:
        iid = _site_e_id(item)
        cur_ids.add(iid)
        sig = _site_e_signature(item)
        new_state[iid] = sig

        if iid not in old:
            if not sig["soldOut"]:
                new_arrivals.append(item)
            continue

        prev = old[iid]
        if prev.get("soldOut") and not sig["soldOut"]:
            restocked.append(item)

        prev_yu = _parse_usd_year_e(prev.get("price", ""))
        cur_yu = _parse_usd_year_e(sig.get("price", ""))
        if prev_yu and cur_yu < prev_yu * 0.99:
            price_drops.append({
                "item": item,
                "old_price": prev.get("price", ""),
                "new_price": sig.get("price", ""),
            })

    return new_arrivals, restocked, price_drops, new_state


def _site_e_format_item(item, new_price_override=None, old_price_override=None):
    """Format single item → Telegram HTML block."""
    title = _html_escape(item.get("title") or item.get("name") or "未知套餐")
    location = _html_escape(item.get("location", ""))
    price_raw = new_price_override or item.get("price", "?")
    pool = _site_e_pool_match(_parse_ram_gb_e(item.get("ram", "")), _parse_usd_year_e(price_raw))

    # Specs
    ram_gb = _parse_ram_gb_e(item.get("ram", ""))
    ram_s = f"{ram_gb:.1f}" if ram_gb < 1 else f"{int(ram_gb)}" if ram_gb == int(ram_gb) else f"{ram_gb:.1f}".rstrip("0").rstrip(".")
    disk_s = _html_escape(item.get("disk", "?"))
    bw_s = _html_escape(item.get("bandwidth", item.get("bw", "?")))

    url = _html_attr(SITE_E_DEPLOY_URL.format(item_id=_site_e_id(item)))
    kw_part = ""
    item_kws = _site_e_get_keywords(item)
    if item_kws:
        kw_part = f"\n   线路: {' / '.join(item_kws[:4])}"

    pool_part = f"\n   池: {pool}" if pool else ""
    return "\n".join([
        f"📦 <b>{title}</b>",
        f"   {ram_s}GB / {disk_s} / {bw_s} · {price_raw}/年",
        f"   🌍 {location}{kw_part}{pool_part}",
        f'   <a href="{url}">🛍️ 链接</a>',
    ])


def notify_site_e_new(new_arrivals):
    """Build new-arrival notification."""
    parts = [f"🆕 <b>Site E 新套餐</b> ({len(new_arrivals)} 个)\n"]
    for item in new_arrivals[:20]:
        parts.append(_site_e_format_item(item))
    if len(new_arrivals) > 20:
        parts.append(f"\n... +{len(new_arrivals) - 20} 个")
    return "\n".join(parts)


def notify_site_e_restock(restocked):
    """Build restock notification."""
    parts = [f"🔔 <b>Site E 补货</b> ({len(restocked)} 个)\n"]
    for item in restocked[:20]:
        parts.append(_site_e_format_item(item))
    if len(restocked) > 20:
        parts.append(f"\n... +{len(restocked) - 20} 个")
    return "\n".join(parts)


def notify_site_e_price_drops(price_drops):
    """Build price-drop notification with before/after prices."""
    parts = [f"💰 <b>Site E 降价</b> ({len(price_drops)} 个)\n"]
    for entry in price_drops[:20]:
        item = entry["item"]
        old_p = entry.get("old_price", "?")
        new_p = entry.get("new_price", "?")
        parts.append(
            f"📦 <b>{_html_escape(item.get('title') or item.get('name') or '未知套餐')}</b>\n"
            f"   {old_p} → {new_p}/年\n"
            f'   <a href="{_html_attr(SITE_E_DEPLOY_URL.format(item_id=_site_e_id(item)))}">🛍️ 链接</a>'
        )
    if len(price_drops) > 20:
        parts.append(f"\n... +{len(price_drops) - 20} 个")
    return "\n".join(parts)


def monitor_site_e(state):
    """Full poll cycle: fetch → diff → notify → save state. Returns (n_new, n_restock, n_drop)."""
    items = fetch_site_e()
    if not items:
        log.info("site-e polled 0 items (api=%s)", SITE_E_API_URL)
        return 0, 0, 0

    new_arrivals, restocked, price_drops, new_state = compare_site_e(state, items)
    state["items"] = new_state

    if state.get("first_run", True):
        state["first_run"] = False
        log.info("site-e first run: loaded %d items (no notify)", len(new_state))
        return 0, 0, 0

    total_events = len(new_arrivals) + len(restocked) + len(price_drops)
    if new_arrivals:
        send_tg(notify_site_e_new(new_arrivals))
    if restocked:
        send_tg(notify_site_e_restock(restocked))
    if price_drops:
        send_tg(notify_site_e_price_drops(price_drops))

    log.info("site-e: %d events (new=%d, restock=%d, drop=%d, api=%s)",
             total_events, len(new_arrivals), len(restocked), len(price_drops), SITE_E_API_URL)

    return len(new_arrivals), len(restocked), len(price_drops)
