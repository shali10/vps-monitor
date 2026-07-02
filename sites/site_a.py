"""Site A: 独角鲸云 (api.fuckip.me) — Bearer auth, paginated plans, CN2 route detection."""
import logging

import requests

from config import (
    SITE_A_API_URL,
    SITE_A_CHEAP_MAX_PRICE,
    SITE_A_DEPLOY_URL,
    SITE_A_MAX_PRICE,
    SITE_A_MIN_PRICE,
    SITE_A_OPTIMIZED_EXCLUDE_KEYWORDS,
    SITE_A_OPTIMIZED_KEYWORDS,
    SITE_A_TOKEN,
)
from core.notify import send_tg
from core.utils import _fmt_monthly_traffic, _fmt_ram_mb, _html_attr, _html_escape

log = logging.getLogger("vps-monitor")


def fetch_site_a():
    """Fetch all plans (paginated). Returns (items, total)."""
    if not SITE_A_API_URL:
        log.info("site_a disabled (SITE_A_API_URL empty)")
        return [], 0
    items, total, page = [], 0, 1
    while True:
        r = requests.get(
            SITE_A_API_URL,
            params={"limit": 200, "page": page},
            headers={"Authorization": f"Bearer {SITE_A_TOKEN}"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Site A API error: {data}")
        body = data.get("data", {})
        page_items = body.get("plans", []) if isinstance(body, dict) else body
        total = body.get("total", 0) if isinstance(body, dict) else data.get("total", 0)
        items.extend(page_items)
        if len(items) >= total or not page_items:
            break
        page += 1
    return items, total


def _site_a_text_blob(p):
    """Combined text for route keyword scanning."""
    parts = [
        p.get("name", ""),
        p.get("machine_name", ""),
        p.get("machine_description", ""),
        p.get("machine_region", ""),
        p.get("machine_vm_type", ""),
    ]
    return " ".join(str(x) for x in parts if x).lower()


def _site_a_has_optimized_route(p):
    """True if plan matches optimized-keywords AND not matched by exclude-keywords."""
    blob = _site_a_text_blob(p)
    pos = any(kw in blob for kw in SITE_A_OPTIMIZED_KEYWORDS)
    neg = any(kw in blob for kw in SITE_A_OPTIMIZED_EXCLUDE_KEYWORDS)
    return pos and not neg


def _site_a_price_value(p):
    """Numeric monthly price for filtering/comparison."""
    for key in ("price_monthly", "price_cents"):
        v = p.get(key)
        if v is not None:
            try:
                return float(v) / 100 if key == "price_cents" else float(v)
            except (TypeError, ValueError):
                pass
    return None


def _site_a_price_in_range(p):
    """Within user's configured max price."""
    v = _site_a_price_value(p)
    if v is None:
        return True
    return SITE_A_MIN_PRICE <= v <= SITE_A_MAX_PRICE


def _site_a_price_in_cheap_any_range(p):
    """Always- Cheap pool: any price ≤ cheap_max."""
    v = _site_a_price_value(p)
    if v is None:
        return False
    return v <= SITE_A_CHEAP_MAX_PRICE


def _site_a_route_intro(p):
    """Generate route description line from keyword scan or fallback text."""
    blob = _site_a_text_blob(p)
    route_parts = []
    checks = [
        ("三网", "三网"), ("cn2", "CN2"), ("gia", "GIA"), ("cmin2", "CMIN2"),
        ("cmi", "CMI"), ("9929", "9929"), ("4837", "4837"), ("bgp", "BGP"),
        ("移动直连", "移动直连"), ("联通可直连", "联通可直连"), ("直连", "直连"),
        ("低延迟", "低延迟"), ("原生", "原生IP"), ("家宽", "家宽"), ("大流量", "大流量"),
    ]
    for needle, label in checks:
        if needle in blob and label not in route_parts:
            route_parts.append(label)
    tags = [str(t).strip() for t in (p.get("machine_tags") or []) if str(t).strip()]
    for tag in tags:
        if tag not in route_parts:
            route_parts.append(tag)
    if route_parts:
        return " / ".join(route_parts[:6])
    desc = (p.get("machine_description") or "").strip().replace("\n", " ")
    if desc:
        return desc[:80] + ("…" if len(desc) > 80 else "")
    return "未标注，需自行测试"


def _site_a_match_rules(p):
    """Classify plan into promotion tiers."""
    v = _site_a_price_value(p)
    if v is None or v <= 0:
        return []
    out = []
    if v <= SITE_A_CHEAP_MAX_PRICE:
        out.append("any_cheap")
    if v <= SITE_A_MAX_PRICE and _site_a_has_optimized_route(p):
        out.append("promo_optimized")
    if v <= SITE_A_MAX_PRICE:
        out.append("promo_bargain")
    return out


def _site_a_stock_available(p):
    """Check remaining stock > 0."""
    r = p.get("remaining")
    if r is None:
        return True
    try:
        return int(r) > 0
    except (TypeError, ValueError):
        return True


def _site_a_available(p):
    """Available = in-stock AND in price range."""
    return _site_a_stock_available(p) and _site_a_price_in_range(p)


def _site_a_prev_available(prev):
    """Remaining stock from previous poll state."""
    return bool(prev.get("available", False))


def _site_a_state_item(p, available):
    """Build state dict for a single plan."""
    return {"available": available, "price": p.get("price_monthly") or p.get("price_cents")}


def _site_a_group_by_mer(plans):
    """Group plans by machine_name for display."""
    groups = {}
    for p in plans:
        key = p.get("machine_name", "未知母鸡")
        groups.setdefault(key, []).append(p)
    return groups


def _site_a_format(p, show_footer=False):
    """Format single plan → Telegram HTML block."""
    name = _html_escape(p.get("name", "?"))
    machine = _html_escape(p.get("machine_name", "未知母鸡"))
    region = _html_escape(p.get("machine_region", "?"))
    cpu = _html_escape(p.get("cpu", "?"))
    ram = _fmt_ram_mb(p.get("ram_mb"))
    disk = _html_escape(p.get("disk_gb", "?"))
    bw = _html_escape(p.get("bandwidth_mbps", "?"))
    traffic_raw = p.get("monthly_traffic_gb")
    traffic = _fmt_monthly_traffic(traffic_raw)
    price = p.get("price_monthly", "?")
    remaining = p.get("remaining")
    vm = _html_escape(p.get("machine_vm_type", "") or "?")
    pid = p.get("id", "")
    url = _html_attr(SITE_A_DEPLOY_URL.format(plan_id=pid))
    try:
        rem_text = str(remaining) if remaining is not None else "有货"
    except Exception:
        rem_text = "有货"
    spec_parts = [f"{cpu}vCore", ram, f"{disk}GB SSD"]
    if traffic:
        spec_parts.append(f"{bw}Mbps / {traffic}")
    else:
        spec_parts.append(f"{bw}Mbps")
    route_line = _site_a_route_intro(p)
    specs = " / ".join(spec_parts)
    return "\n".join([
        f"📦 <b>{region}: {machine}</b>",
        f"   {name} ({vm})",
        f"   配置: {specs}",
        f"   线路: {route_line}",
        f"   价格: ${price}/月 (余 {rem_text})",
        f'   <a href="{url}">🛍️ 直达链接</a>',
        *([_site_a_footer()] if show_footer else []),
    ])


def _site_a_footer():
    return "\n━━━━━━━━━━━━━━━━━━"


def compare_site_a(state, plans):
    """Diff old vs new plan lists. Returns (new_arrivals, restocked, new_state)."""
    old_plans = state.get("plans", {})
    new_state = {}
    new_arrivals, restocked = [], []

    for p in plans:
        pid = str(p.get("id"))
        available = _site_a_available(p)
        new_state[pid] = _site_a_state_item(p, available)

        if pid not in old_plans:
            if available:
                new_arrivals.append(p)
        elif not _site_a_prev_available(old_plans[pid]) and available:
            restocked.append(p)

    return new_arrivals, restocked, new_state


def _notify_a_group_by_rule(plans, event_label):
    """Classify arriving/restocked plans by rule system."""
    buckets = {"promo_optimized": [], "promo_bargain": [], "any_cheap": []}
    for p in plans:
        for rule in _site_a_match_rules(p):
            if rule in buckets:
                buckets[rule].append(p)
    return buckets


def _notify_a_send_one(event_label, plans, tags, rule_desc):
    """Format a bucket of plans into one push message."""
    if not plans:
        return ""
    parts = [f"<b>{event_label}</b> — {rule_desc} ({len(plans)}):\n"]
    for p in plans:
        parts.append(_site_a_format(p))
    return "\n".join(parts)


def notify_site_a_restocked(restocked):
    """Build restock notification message."""
    grouped = _notify_a_group_by_rule(restocked, "restocked")
    parts = [f"🔔 <b>Site A 补货</b> ({len(restocked)} 个套餐)\n"]

    if grouped["promo_optimized"]:
        parts.append(_notify_a_send_one("🔴 优化线路到货", grouped["promo_optimized"], "optimized", "CN2/GIA/9929 etc."))
    if grouped["promo_bargain"]:
        parts.append(_notify_a_send_one("🟡 合规套餐到货", grouped["promo_bargain"], "bargain", "≤$0.4/month"))
    if grouped["any_cheap"]:
        parts.append(_notify_a_send_one("💰 超低价套餐", grouped["any_cheap"], "any_cheap", "≤$0.1/month"))

    return "\n".join(parts)


def notify_site_a_new_arrival(new_arrivals):
    """Build new-arrival notification message (same layout as restock)."""
    return notify_site_a_restocked(new_arrivals).replace("补货", "新套餐", 1)


def monitor_site_a(state):
    """Full poll cycle: fetch → diff → notify → save state. Returns (n_new, n_restock)."""
    plans, _ = fetch_site_a()
    if not plans:
        return 0, 0

    new_arrivals, restocked, new_state = compare_site_a(state, plans)
    state["plans"] = new_state

    if state.get("first_run", True):
        state["first_run"] = False
        log.info("site-a first run: loaded %d plans (no notify)", len(plans))
        return 0, 0

    total_events = len(new_arrivals) + len(restocked)
    if new_arrivals:
        msg = notify_site_a_new_arrival(new_arrivals)
        send_tg(msg)
    if restocked:
        msg = notify_site_a_restocked(restocked)
        send_tg(msg)
    if total_events:
        log.info("site-a: %d events (new=%d, restock=%d)", total_events, len(new_arrivals), len(restocked))
    else:
        log.info("site-a: no events (stock stable)")

    return len(new_arrivals), len(restocked)
