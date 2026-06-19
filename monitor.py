#!/usr/bin/env python3
"""
VPS 商品/库存监控 → Telegram 推送

3 个独立 source,共用一个 TG bot:

  Site A  (auth: Bearer)   间隔 A_INTERVAL 秒
  Site B  (公开 API)        间隔 B_INTERVAL 秒
  Site C  (公开 API)        间隔 C_INTERVAL 秒

每个 source 检测的"事件":
  - 新到货 (新出现的 id)
  - 补货 (售罄 → 在售 / 库存 0 → N)
  - (部分) 降价

要把这个工具套到别的站,改顶部 SITE_X_API_URL / 间隔 / 解析函数即可。
"""
import os
import sys
import re
import json
import time
import signal
import logging
import html
import requests
from datetime import datetime
from pathlib import Path

# ========== 顶部配置: 改这里适配你自己的 source ==========

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


# Telegram bot (https://t.me/BotFather 申请)
_TB = chr(84) + chr(69) + chr(76) + chr(69) + chr(71) + chr(82) + chr(65) + chr(77) + chr(95) + chr(66) + chr(79) + chr(84) + chr(95) + chr(84) + chr(79) + chr(75) + chr(69) + chr(78)
TELEGRAM_BOT_TOKEN = os.environ.get(_TB, "")
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

# 通用
POLL_INTERVAL = _env_int("POLL_INTERVAL", 60)  # 主循环间隔 (秒). 3 个 source 各自有独立 interval, 不会每个都跑
LOG_FILE = Path(__file__).parent / "monitor.log"
STATE_FILE = Path(__file__).parent / "state.json"

# ---- Site A (需要 Bearer token) ----
# 示例: https://your-site.com/api/v1/plans?limit=200&page=1
SITE_A_API_URL = _env_str("SITE_A_API_URL", "https://api.fuckip.me/api/v1/plans")
SITE_A_TOKEN = _env_str("SITE_A_TOKEN", "")  # 从浏览器登录后 DevTools 拿 Authorization: Bearer ***
SITE_A_POLL_INTERVAL = _env_int("SITE_A_POLL_INTERVAL", 60)
SITE_A_DEPLOY_URL = _env_str("SITE_A_DEPLOY_URL", "https://dash.fuckip.me/deploy?plan_id={plan_id}")
SITE_A_MIN_PRICE = _env_float("SITE_A_MIN_PRICE", 0)
SITE_A_MAX_PRICE = _env_float("SITE_A_MAX_PRICE", 0.4)
SITE_A_CHEAP_MAX_PRICE = _env_float("SITE_A_CHEAP_MAX_PRICE", 0.1)
SITE_A_OPTIMIZED_KEYWORDS = [
    k.strip().lower() for k in os.environ.get(
        "SITE_A_OPTIMIZED_KEYWORDS",
        "优化,CN2,GIA,CMI,9929,4837,精品,三网,BGP,回国,直连,低延迟"
    ).split(",") if k.strip()
]
SITE_A_OPTIMIZED_EXCLUDE_KEYWORDS = [
    k.strip().lower() for k in os.environ.get(
        "SITE_A_OPTIMIZED_EXCLUDE_KEYWORDS",
        "无优化,无任何优化,非优化,普通线路"
    ).split(",") if k.strip()
]

# ---- Site B (公开 API) ----
# 示例: 树形结构 area > node > plan
SITE_B_API_URL = _env_str("SITE_B_API_URL", "")
SITE_B_POLL_INTERVAL = _env_int("SITE_B_POLL_INTERVAL", 90)
SITE_B_DEPLOY_URL = _env_str("SITE_B_DEPLOY_URL", "")

# ---- Site C (公开 API) ----
# 示例: packages 数组, 每个 package 内嵌 plans 数组
SITE_C_API_URL = _env_str("SITE_C_API_URL", "")
SITE_C_TOKEN = _env_str("SITE_C_TOKEN", "")
SITE_C_POLL_INTERVAL = _env_int("SITE_C_POLL_INTERVAL", 90)
SITE_C_DEPLOY_URL = _env_str("SITE_C_DEPLOY_URL", "https://incudal.di0.uk/instances/create?package={package_id}")

# ---- Site D: DediRock Promo VPS (HTML 解析, 从独立脚本整合) ----
# 原: /opt/dedirock-monitor/dedirock_promo_watch.py v2.1.0
# 解析 Promo VPS Saver LA/NY 页面, 检测 in_stock + campaign (BF/LET/regular)
SITE_D_POLL_INTERVAL = _env_int("SITE_D_POLL_INTERVAL", 300)  # 5 min (跟原 cron 一致)
SITE_D_USER_AGENT = _env_str("SITE_D_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
SITE_D_CF_SIZE_THRESHOLD = _env_int("SITE_D_CF_SIZE_THRESHOLD", 5000)
# 留空走默认 LA+NY; 想自定义就 SITE_D_PRODUCTS_JSON='[{"code":...}]'
SITE_D_PRODUCTS_JSON = _env_str("SITE_D_PRODUCTS_JSON", "")


# ========== 通用工具 ==========

def _fmt_bytes(n):
    """字节数自动选 B/KB/MB/GB/TB"""
    n = int(n) if n else 0
    for unit, base in [("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)]:
        if n >= base:
            return f"{n/base:.0f}{unit}" if n % base == 0 else f"{n/base:.1f}{unit}"
    return f"{n}B"


def _fmt_cny(cents):
    """分 → '¥X.XX'"""
    try:
        return f"¥{int(cents)/100:.2f}"
    except (TypeError, ValueError):
        return f"¥{cents}"


def _fmt_usd(value):
    """美元数字 → '$X'"""
    try:
        return f"${float(value):g}"
    except (TypeError, ValueError):
        return f"${value}"


def _paginate_push(title, items, formatter, page_size=8):
    """分页推送, 避免超 4096 字符。"""
    if not items:
        return 0
    full = formatter(items)
    if len(full) <= 4000:
        return 1 if send_tg(full) else 0
    sent_count = 0
    total_pages = (len(items) + page_size - 1) // page_size
    for i in range(0, len(items), page_size):
        chunk = items[i:i + page_size]
        msg = formatter(chunk)
        page_no = i // page_size + 1
        msg = msg.replace(title, f"{title} (第 {page_no}/{total_pages} 页)", 1)
        if send_tg(msg):
            sent_count += 1
    return sent_count
# ========== Logging / State / TG ==========

# 显式 FileHandler + 每条 log flush (修 log 不刷新 bug)
class _FlushFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

_log_file = _FlushFileHandler(LOG_FILE, encoding="utf-8", delay=False)
_log_file.setLevel(logging.INFO)
_log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_log_file.setFormatter(_log_formatter)
log = logging.getLogger("vps-monitor")
log.setLevel(logging.INFO)
log.addHandler(_log_file)
log.addHandler(logging.StreamHandler())

log = logging.getLogger("vps-monitor")


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "site_a": {"plans": {}, "first_run": True},
        "site_b": {"plans": {}, "first_run": True},
        "site_c": {"packages": {}, "first_run": True},
        "site_d": {"products": {}, "first_run": True},
        "last_poll": 0,
    }


def save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.replace(STATE_FILE)


def send_tg(text):
    """推送到 Telegram。支持 TELEGRAM_CHAT_IDS 多接收人；失败不抛, 写到 log。"""
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


# ============================================================
# Site A: Bearer auth, 分页, 多商家, 字段 cpu/ram_mb/disk_gb/...
# ============================================================

def fetch_site_a():
    """返回 (items, total)。支持分页。"""
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


def _html_escape(value):
    return html.escape(str(value if value is not None else ""), quote=False)

def _html_attr(value):
    return html.escape(str(value if value is not None else ""), quote=True)

def _fmt_ram_mb(mb):
    try:
        mb = int(mb or 0)
    except (TypeError, ValueError):
        return f"{mb}MB"
    if mb >= 1024 and mb % 1024 == 0:
        return f"{mb // 1024}GB"
    if mb >= 1024:
        return f"{mb / 1024:.1f}GB"
    return f"{mb}MB"

def _fmt_monthly_traffic(gb):
    try:
        gb = float(gb or 0)
    except (TypeError, ValueError):
        return ""
    if gb <= 0:
        return "不限流量"
    return f"{gb:g}GB BW"

def _site_a_route_intro(p):
    blob = _site_a_text_blob(p)
    route_parts = []
    checks = [
        ("三网", "三网"),
        ("cn2", "CN2"),
        ("gia", "GIA"),
        ("cmin2", "CMIN2"),
        ("cmi", "CMI"),
        ("9929", "9929"),
        ("4837", "4837"),
        ("bgp", "BGP"),
        ("移动直连", "移动直连"),
        ("联通可直连", "联通可直连"),
        ("直连", "直连"),
        ("低延迟", "低延迟"),
        ("原生", "原生IP"),
        ("家宽", "家宽"),
        ("大流量", "大流量"),
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

def _site_a_format(p):
    name = _html_escape(p.get("name", "?"))
    machine = _html_escape(p.get("machine_name", "未知母鸡"))
    region = _html_escape(p.get("machine_region", "?"))
    cpu = _html_escape(p.get("cpu", "?"))
    ram = _fmt_ram_mb(p.get("ram_mb"))
    disk = _html_escape(p.get("disk_gb", "?"))
    bw = _html_escape(p.get("bandwidth_mbps", "?"))
    traffic = _fmt_monthly_traffic(p.get("monthly_traffic_gb"))
    price = p.get("price_monthly", "?")
    remaining = p.get("remaining")
    vm = _html_escape(p.get("machine_vm_type", "") or "?")
    pid = p.get("id", "")
    url = _html_attr(SITE_A_DEPLOY_URL.format(plan_id=pid))
    try:
        price_s = f"${float(price):g} USD/月"
    except (TypeError, ValueError):
        price_s = f"${_html_escape(price)} USD/月"
    try:
        remaining_s = str(int(remaining))
    except (TypeError, ValueError):
        remaining_s = "?"
    route = _html_escape(_site_a_route_intro(p))
    rules = _html_escape(" / ".join(_site_a_match_rules(p)) or "未命中")
    spec_parts = [f"{cpu}vCore", ram, f"{disk}GB SSD"]
    if traffic:
        spec_parts.append(_html_escape(traffic))
    spec_parts.append(f"{bw}Mbps")
    specs = " / ".join(spec_parts)
    return "\n".join([
        f"📦 <b>{region}: {machine}</b>",
        f"   └ <code>{name}</code>",
        f"💰 <b>{price_s}</b> | 🌐 {region}",
        f"🖥️ {specs}",
        f"🛣️ 线路: {route}",
        f"🎯 命中: <b>{rules}</b>",
        f"📊 库存: <b>{remaining_s}</b> 台 | 🧩 {vm}",
        f"🛍️ <a href=\"{url}\">直达链接</a>",
    ])

def _site_a_footer():
    return f"\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n━━━━━━━━━━━━"

def _site_a_group_by_mer(plans):
    by_mer = {}
    for p in plans:
        mer = p.get("machine_name", p.get("mer_name", "未知商家"))
        by_mer.setdefault(mer, []).append(p)
    return by_mer


def _site_a_text_blob(p):
    fields = [
        p.get("machine_name"),
        p.get("machine_region"),
        p.get("machine_description"),
        p.get("name"),
        p.get("description"),
        " ".join(p.get("machine_tags") or []),
    ]
    return " ".join(str(v) for v in fields if v).lower()

def _site_a_has_optimized_route(p):
    blob = _site_a_text_blob(p)
    if any(keyword in blob for keyword in SITE_A_OPTIMIZED_EXCLUDE_KEYWORDS):
        return False
    return any(keyword in blob for keyword in SITE_A_OPTIMIZED_KEYWORDS)

def _site_a_price_value(p):
    try:
        return float(p.get("price_monthly") or 0)
    except (TypeError, ValueError):
        return None

def _site_a_price_in_range(p):
    """规则 1 的价格段：0~SITE_A_MAX_PRICE。保留旧函数名，兼容日志/旧代码。"""
    price = _site_a_price_value(p)
    return price is not None and SITE_A_MIN_PRICE <= price <= SITE_A_MAX_PRICE

def _site_a_price_in_cheap_any_range(p):
    """规则 2 的价格段：0~SITE_A_CHEAP_MAX_PRICE，不要求优化线路。"""
    price = _site_a_price_value(p)
    return price is not None and SITE_A_MIN_PRICE <= price <= SITE_A_CHEAP_MAX_PRICE

def _site_a_match_rules(p):
    """
    独角鲸云双规则：
      1) 0~0.4 USD/月 + 优化线路关键词；
      2) 0~0.1 USD/月 + 不限线路。
    命中任意一个规则即可纳入到货/补货监控。
    """
    rules = []
    price = _site_a_price_value(p)
    if price is None:
        return rules
    if SITE_A_MIN_PRICE <= price <= SITE_A_MAX_PRICE and _site_a_has_optimized_route(p):
        rules.append(f"0-{SITE_A_MAX_PRICE:g}优化机")
    if SITE_A_MIN_PRICE <= price <= SITE_A_CHEAP_MAX_PRICE:
        rules.append(f"0-{SITE_A_CHEAP_MAX_PRICE:g}随便机")
    return rules

def _site_a_stock_available(p):
    """只判断是否可购买，不掺杂价格/线路筛选。"""
    if p.get("status", "active") != "active":
        return False
    if p.get("machine_status") not in (None, "online"):
        return False
    if bool(p.get("sold_out")) or bool(p.get("ram_insufficient")):
        return False
    remaining = p.get("remaining")
    try:
        return int(remaining) > 0
    except (TypeError, ValueError):
        return False

def _site_a_available(p):
    """独角鲸云可购买判断：有库存 + 命中任意一条低价规则。"""
    return _site_a_stock_available(p) and bool(_site_a_match_rules(p))

def _site_a_prev_available(prev):
    """兼容旧 state：以前 plans[id] 是 bool，现在是 dict。"""
    if isinstance(prev, dict):
        return bool(prev.get("available"))
    return bool(prev)

def _site_a_state_item(p, available):
    try:
        remaining = int(p.get("remaining"))
    except (TypeError, ValueError):
        remaining = None
    return {
        "available": bool(available),
        "rules": _site_a_match_rules(p),
        "remaining": remaining,
    }

def compare_site_a(state, plans):
    """独角鲸云事件：新可购套餐 / 补货（不可购→可购），双规则并行。"""
    new_arrivals, restocked, new_state = [], [], {}
    old_plans = state.get("plans", {})
    for p in plans:
        pid = str(p.get("id"))
        available = _site_a_available(p)
        prev = old_plans.get(pid)
        if prev is None:
            if available:
                new_arrivals.append(p)
        elif (not _site_a_prev_available(prev)) and available:
            restocked.append(p)
        new_state[pid] = _site_a_state_item(p, available)
    return new_arrivals, restocked, new_state



def _notify_a_group_by_rule(plans, event_label):
    """
    将 plans 按命中规则拆分并分别推送，打不同 tag。
    event_label = '新套餐' or '补货'
    """
    # 按命中规则分组，避免一条消息里混杂两类库存
    rule1_only, rule2_only, rule_both = [], [], []
    for p in plans:
        rs = _site_a_match_rules(p)
        r1 = any(r == f"0-{SITE_A_MAX_PRICE:g}优化机" for r in rs)
        r2 = any(r == f"0-{SITE_A_CHEAP_MAX_PRICE:g}随便机" for r in rs)
        if r1 and r2:
            rule_both.append(p)
        elif r1:
            rule1_only.append(p)
        elif r2:
            rule2_only.append(p)
    total_pushed = 0
    if rule1_only:
        total_pushed += _notify_a_send_one(event_label, rule1_only,
            f"#独角鲸云 #优化0_4",
            f"🎯 规则：0~{SITE_A_MAX_PRICE:g} USD/月 优化线路")
    if rule2_only:
        total_pushed += _notify_a_send_one(event_label, rule2_only,
            f"#独角鲸云 #随便0_1",
            f"🎯 规则：0~{SITE_A_CHEAP_MAX_PRICE:g} USD/月 不限线路")
    if rule_both:
        total_pushed += _notify_a_send_one(event_label, rule_both,
            f"#独角鲸云 #优化0_4 #随便0_1",
            f"🎯 同时命中两条规则")
    return total_pushed


def _notify_a_send_one(event_label, plans, tags, rule_desc):
    """推送一个规则分组。共用格式化。"""
    emoji = "🆕" if event_label == "新套餐" else "🔔"
    title = f"{emoji} {tags}"

    def formatter(chunk):
        by_mer = _site_a_group_by_mer(chunk)
        n_mer = len(by_mer)
        n_plans = len(chunk)
        parts = [
            title,
            f"📦 <b>{event_label}</b>：{n_mer} 商家 / {n_plans} 套餐",
            f"{rule_desc}",
        ]
        for mer, plist in by_mer.items():
            parts.append(f"\n<b>📍 {_html_escape(mer)}</b> ({len(plist)} 个)")
            for p in plist[:10]:
                parts.append(_site_a_format(p))
            if len(plist) > 10:
                parts.append(f"  · ... +{len(plist) - 10} 个")
        parts.append(_site_a_footer())
        return "\n".join(parts)

    return _paginate_push(title, plans, formatter, page_size=8)
def notify_site_a_restocked(restocked):

    """补货通知，按规则拆分后分别推送。"""
    _notify_a_group_by_rule(restocked, "补货")
    return ""  # kept for backwards compat; actual push happens inside


def notify_site_a_new_arrival(new_arrivals):
    """新套餐通知，按规则拆分后分别推送。"""
    _notify_a_group_by_rule(new_arrivals, "新套餐")
    return ""
def monitor_site_a(state):
    items, total = fetch_site_a()
    matched_optimized = [p for p in items if _site_a_price_in_range(p) and _site_a_has_optimized_route(p)]
    matched_cheap_any = [p for p in items if _site_a_price_in_cheap_any_range(p)]
    matched = [p for p in items if _site_a_match_rules(p)]
    available = [p for p in matched if _site_a_stock_available(p)]
    log.info(
        "独角鲸云轮询 %d plans (total=%d), 0-%g优化=%d, 0-%g随便=%d, union=%d, available=%d, interval=%ds",
        len(items), total, SITE_A_MAX_PRICE, len(matched_optimized),
        SITE_A_CHEAP_MAX_PRICE, len(matched_cheap_any), len(matched), len(available), SITE_A_POLL_INTERVAL,
    )
    new_arrivals, restocked, new_state = compare_site_a(state, items)
    state["plans"] = new_state
    if state.get("first_run", True):
        state["first_run"] = False
        log.info("独角鲸云首次加载: loaded %d plans (no notify), available=%d", len(new_state), len(available))
        return 0, 0
    if new_arrivals:
        notify_site_a_new_arrival(new_arrivals)
    if restocked:
        notify_site_a_restocked(restocked)
    return len(new_arrivals), len(restocked)


# ============================================================
# Site B: 公开 API, 树形 area > node > plan
#   字段: {id, plan_name, cpu, memory, disk, bandwidth, price_datas[0].price (cents), stock, is_pre_sale, area_id, area_name, node_id, node_name}
#   价格是人民币分, 流量字段 (如果想加) 在 plan 根
# ============================================================

# 56idc disabled: def fetch_site_b():
# 56idc disabled:     """GET 公开 API, 返回 flat plan 列表。"""
# 56idc disabled:     if not SITE_B_API_URL:
# 56idc disabled:         log.debug("site-b skipped (SITE_B_API_URL not configured)")
# 56idc disabled:         return []
# 56idc disabled:     try:
# 56idc disabled:         r = requests.get(SITE_B_API_URL, timeout=15)
# 56idc disabled:         r.raise_for_status()
# 56idc disabled:         d = r.json()
# 56idc disabled:     except Exception as e:
# 56idc disabled:         log.warning("site-b fetch failed: %s", e)
# 56idc disabled:         return []
# 56idc disabled:     if d.get("status_code") not in (0, 200, None):
# 56idc disabled:         log.warning("site-b API error: %s", d.get("status_msg"))
# 56idc disabled:         return []
# 56idc disabled:     flat = []
# 56idc disabled:     for area in (d.get("data") or {}).get("areas") or []:
# 56idc disabled:         area_id = area.get("id")
# 56idc disabled:         area_name = area.get("area_name")
# 56idc disabled:         for node in area.get("nodes") or []:
# 56idc disabled:             node_id = node.get("id")
# 56idc disabled:             node_name = node.get("group_name")
# 56idc disabled:             for plan in node.get("plans") or []:
# 56idc disabled:                 price_data = (plan.get("price_datas") or [{}])[0]
# 56idc disabled:                 price = price_data.get("price", 0)
# 56idc disabled:                 flat.append({
# 56idc disabled:                     "id": plan.get("id"),
# 56idc disabled:                     "plan_name": plan.get("plan_name"),
# 56idc disabled:                     "cpu": plan.get("cpu"),
# 56idc disabled:                     "memory": plan.get("memory"),
# 56idc disabled:                     "disk": plan.get("disk"),
# 56idc disabled:                     "bandwidth": plan.get("bandwidth"),
# 56idc disabled:                     "flow": plan.get("flow", 0) or 0,
# 56idc disabled:                     "price_cents": price,
# 56idc disabled:                     "price_yuan": price / 100,
# 56idc disabled:                     "stock": plan.get("stock", 0) or 0,
# 56idc disabled:                     "is_pre_sale": plan.get("is_pre_sale", False),
# 56idc disabled:                     "area_id": area_id,
# 56idc disabled:                     "area_name": area_name,
# 56idc disabled:                     "node_id": node_id,
# 56idc disabled:                     "node_name": node_name,
# 56idc disabled:                 })
# 56idc disabled:     return flat
# 56idc disabled: 
# 56idc disabled: 
# 56idc disabled: def compare_site_b(state, plans):
# 56idc disabled:     """Site B 事件: 新套餐 (id 之前没出现过) / 补货 (stock 0→N)"""
# 56idc disabled:     old = state.get("plans", {})
# 56idc disabled:     new = {str(p["id"]): p["stock"] for p in plans}
# 56idc disabled:     new_arrivals, restocked = [], []
# 56idc disabled:     for p in plans:
# 56idc disabled:         pid = str(p["id"])
# 56idc disabled:         cur = p["stock"]
# 56idc disabled:         prev = old.get(pid)
# 56idc disabled:         if prev is None:
# 56idc disabled:             new_arrivals.append(p)
# 56idc disabled:         elif prev == 0 and cur > 0:
# 56idc disabled:             restocked.append(p)
# 56idc disabled:     return new_arrivals, restocked, new
# 56idc disabled: 
# 56idc disabled: 
# 56idc disabled: def _site_b_format_one(p, in_restock=True):
# 56idc disabled:     url = SITE_B_DEPLOY_URL.format(area_id=p["area_id"])
# 56idc disabled:     bw = p.get("bandwidth", 0) or 0
# 56idc disabled:     bw_s = f" {bw/1000:.0f}Gbps" if bw >= 1000 else f" {bw}Mbps"
# 56idc disabled:     flow = p.get("flow", 0) or 0
# 56idc disabled:     flow_s = " · 不限流量" if flow == 0 else f" · {flow:,}GB/月"
# 56idc disabled:     pre = " [预售]" if p.get("is_pre_sale") else ""
# 56idc disabled:     return (
# 56idc disabled:         f"\n  • {p['plan_name']}{pre}\n"
# 56idc disabled:         f"    {p['cpu']}C/{p['memory']}MB/{p['disk']}GB{bw_s}{flow_s} · "
# 56idc disabled:         f"¥{p['price_yuan']:.2f}/月 · 库存 {p['stock']} 台\n"
# 56idc disabled:         f'    <a href="{url}">🛍️ 直达链接</a>'
# 56idc disabled:     )
# 56idc disabled: 
# 56idc disabled: 
# 56idc disabled: def notify_site_b_restocked(restocked):
# 56idc disabled:     by_loc = {}
# 56idc disabled:     for p in restocked:
# 56idc disabled:         key = (p["area_name"], p.get("node_name", ""))
# 56idc disabled:         by_loc.setdefault(key, []).append(p)
# 56idc disabled:     parts = [f"🔔 <b>源 B 到货/补货</b> ({len(restocked)} 个套餐)\n"]
# 56idc disabled:     for (area, node), plist in by_loc.items():
# 56idc disabled:         parts.append(f"\n<b>📍 {area}</b> · <b>{node}</b> ({len(plist)} 个):")
# 56idc disabled:         for p in plist:
# 56idc disabled:             parts.append(_site_b_format_one(p))
# 56idc disabled:     return "\n".join(parts)
# 56idc disabled: 
# 56idc disabled: 
# 56idc disabled: def notify_site_b_new_arrival(new_arrivals):
# 56idc disabled:     by_area = {}
# 56idc disabled:     for p in new_arrivals:
# 56idc disabled:         by_area.setdefault(p["area_name"], []).append(p)
# 56idc disabled:     parts = [f"🆕 <b>源 B 新套餐</b> ({len(new_arrivals)} 个)\n"]
# 56idc disabled:     for area, plist in by_area.items():
# 56idc disabled:         parts.append(f"\n<b>📍 {area}</b> ({len(plist)} 个):")
# 56idc disabled:         for p in plist:
# 56idc disabled:             parts.append(_site_b_format_one(p, in_restock=False))
# 56idc disabled:     return "\n".join(parts)
# 56idc disabled: 
# 56idc disabled: 
# 56idc disabled: def monitor_site_b(state):
# 56idc disabled:     plans = fetch_site_b()
# 56idc disabled:     if not plans:
# 56idc disabled:         return 0, 0
# 56idc disabled:     new_arrivals, restocked, new_state = compare_site_b(state, plans)
# 56idc disabled:     state["site_b"]["plans"] = new_state
# 56idc disabled:     if state["site_b"].get("first_run", True):
# 56idc disabled:         state["site_b"]["first_run"] = False
# 56idc disabled:         log.info("site-b first run: loaded %d plans (no notify)", len(new_state))
# 56idc disabled:         return 0, 0
# 56idc disabled:     if new_arrivals:
# 56idc disabled:         send_tg(notify_site_b_new_arrival(new_arrivals))
# 56idc disabled:     if restocked:
# 56idc disabled:         _paginate_push("🔔 <b>源 B 到货/补货</b>", restocked, notify_site_b_restocked)
# 56idc disabled:     return len(new_arrivals), len(restocked)
# 56idc disabled: 
# 56idc disabled: 
# 56idc disabled: # ============================================================
# 56idc disabled: # Site C: 公开 API, packages > plans (扁平)
# 56idc disabled: #   package: {id, name, soldOut, plans: [{id, name, cpu, memory, disk, monthlyPrice (cents), isSoldOut, trafficLimit (bytes)}]}
# 56idc disabled: # ============================================================
# 56idc disabled: 
def fetch_site_c():
    if not SITE_C_API_URL:
        log.debug("site-c skipped (SITE_C_API_URL not configured)")
        return []
    if "/api/packages" in SITE_C_API_URL and not SITE_C_TOKEN:
        log.info("site-c skipped (SITE_C_TOKEN missing for authenticated Incudal API)")
        return []
    headers = {}
    if SITE_C_TOKEN:
        headers["Authorization"] = f"Bearer {SITE_C_TOKEN}"
    try:
        params = {"page": 1, "pageSize": 500}
        r = requests.get(SITE_C_API_URL, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        try:
            data = r.json()
        except ValueError as e:
            snippet = (r.text or "")[:200].replace("\n", " ")
            log.warning("site-c returned non-JSON response from %s: %s; body=%r", r.url, e, snippet)
            return []
    except Exception as e:
        log.warning("site-c fetch failed: %s", e)
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("packages", "data", "items", "list", "rows"):
            value = data.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                for subkey in ("packages", "items", "list", "rows"):
                    subvalue = value.get(subkey)
                    if isinstance(subvalue, list):
                        return subvalue
    log.warning("site-c response has no package list: %s", type(data).__name__)
    return []


def _site_c_id(value):
    return str(value.get("id") or value.get("uuid") or value.get("packageId") or value.get("package_id") or value.get("name") or "unknown")


def _site_c_plan_id(plan):
    return str(plan.get("id") or plan.get("uuid") or plan.get("planId") or plan.get("plan_id") or plan.get("name") or "default")


def _site_c_plan_list(pkg):
    for key in ("plans", "packagePlans", "package_plans", "items", "variants"):
        value = pkg.get(key)
        if isinstance(value, list):
            return value
    return []


def _site_c_sold_out(value):
    if value.get("soldOut") is not None:
        return bool(value.get("soldOut"))
    if value.get("isSoldOut") is not None:
        return bool(value.get("isSoldOut"))
    status = str(value.get("status") or value.get("state") or "").lower()
    if status in ("sold_out", "soldout", "sold-out"):
        return True
    stock = value.get("stock", value.get("availableStock", value.get("remaining")))
    if stock is not None:
        try:
            return int(stock) <= 0
        except (TypeError, ValueError):
            pass
    return False


def _site_c_price(plan):
    for key in ("monthlyPrice", "monthly_price", "price", "amount", "renewPrice", "renew_price"):
        value = plan.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0


def _site_c_signature(pkg):
    plans = _site_c_plan_list(pkg)
    if plans:
        plan_sig = {}
        for plan in plans:
            sid = _site_c_plan_id(plan)
            plan_sig[sid] = {
                "isSoldOut": _site_c_sold_out(plan),
                "price": _site_c_price(plan),
                "stock": plan.get("stock", plan.get("availableStock", plan.get("remaining"))),
            }
    else:
        plan_sig = {
            "default": {
                "isSoldOut": _site_c_sold_out(pkg),
                "price": _site_c_price(pkg),
                "stock": pkg.get("stock", pkg.get("availableStock", pkg.get("remaining"))),
            }
        }
    return {"soldOut": _site_c_sold_out(pkg), "plans": plan_sig}


def compare_site_c(state, packages):
    old = state.get("packages", {})
    new_state, new_arrivals, restocked_pkgs, restocked_plans, price_drops = {}, [], [], [], []
    cur_ids = {_site_c_id(p) for p in packages}
    old_ids = set(old.keys())

    for pid in cur_ids - old_ids:
        for package in packages:
            if _site_c_id(package) == pid:
                new_arrivals.append(package)
                break

    for package in packages:
        pid = _site_c_id(package)
        sig = _site_c_signature(package)
        new_state[pid] = sig
        if pid not in old:
            continue
        prev = old[pid]
        if prev.get("soldOut") is True and sig["soldOut"] is False:
            restocked_pkgs.append(package)
        prev_plans = prev.get("plans", {})
        plan_source = _site_c_plan_list(package) or [{"id": "default", **package}]
        for plan in plan_source:
            sid = _site_c_plan_id(plan)
            cur_plan = sig["plans"].get(sid, {})
            prev_plan = prev_plans.get(sid)
            if prev_plan is None:
                continue
            if prev_plan.get("isSoldOut") is True and cur_plan.get("isSoldOut") is False:
                restocked_plans.append({"package": package, "plan": plan})
            cur_price = cur_plan.get("price", 0)
            prev_price = prev_plan.get("price", 0)
            if prev_price and cur_price and cur_price < prev_price:
                price_drops.append({"package": package, "plan": plan, "old_price": prev_price, "new_price": cur_price})
    return new_arrivals, restocked_pkgs, restocked_plans, price_drops, new_state


def _site_c_plan_specs(plan):
    cpu = plan.get("cpu", plan.get("cpuCores", plan.get("cpu_max", "?")))
    mem = plan.get("memory", plan.get("memoryMb", plan.get("memory_max", "?")))
    disk = plan.get("disk", plan.get("diskGb", plan.get("disk_max", "?")))
    traffic = plan.get("trafficLimit", plan.get("traffic", plan.get("traffic_limit"))) or 0
    traffic_s = ""
    try:
        traffic_s = f" · {_fmt_bytes(traffic)}/月" if int(traffic or 0) > 0 else ""
    except (TypeError, ValueError):
        traffic_s = f" · {traffic}/月" if traffic else ""
    return f"{cpu}C/{mem}MB/{disk}GB{traffic_s}"


def _site_c_package_name(package):
    return _html_escape(package.get("name") or package.get("title") or package.get("packageName") or _site_c_id(package))


def _site_c_plan_name(plan):
    return _html_escape(plan.get("name") or plan.get("title") or plan.get("planName") or _site_c_plan_id(plan))


def _site_c_format_price(value):
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        return str(value)
    if value > 1000 and value == int(value):
        return f"¥{value / 100:.2f}"
    return f"¥{value:g}"


def notify_site_c_new(new_arrivals):
    parts = [f"🆕 #incudal #新套餐 ({len(new_arrivals)} 个)"]
    for package in new_arrivals[:20]:
        url = SITE_C_DEPLOY_URL.format(package_id=_site_c_id(package))
        plans = _site_c_plan_list(package)
        plan_text = f"{len(plans)} 个方案" if plans else "自定义/单方案"
        source = _html_escape(package.get("source") or package.get("scope") or "?")
        parts.append(
            f"\n• <b>{_site_c_package_name(package)}</b>\n"
            f"  来源: {source} · {plan_text}\n"
            f'  <a href="{_html_attr(url)}">🛍️ 直达链接</a>'
        )
    if len(new_arrivals) > 20:
        parts.append(f"\n... +{len(new_arrivals) - 20} 个")
    return "\n".join(parts)


def notify_site_c_restock(restocked_pkgs, restocked_plans):
    total = len(restocked_pkgs) + len(restocked_plans)
    if total == 0:
        return ""
    parts = [f"🔔 #incudal #补货 ({len(restocked_pkgs)} 套餐 / {len(restocked_plans)} 方案)"]
    for package in restocked_pkgs[:10]:
        url = SITE_C_DEPLOY_URL.format(package_id=_site_c_id(package))
        parts.append(f"\n📍 <b>{_site_c_package_name(package)}</b> 整体重新可买\n  <a href=\"{_html_attr(url)}\">🛍️ 直达链接</a>")
    for item in restocked_plans[:20]:
        package, plan = item["package"], item["plan"]
        url = SITE_C_DEPLOY_URL.format(package_id=_site_c_id(package))
        price = _site_c_format_price(_site_c_price(plan))
        parts.append(
            f"\n📍 <b>{_site_c_package_name(package)}</b> · {_site_c_plan_name(plan)}\n"
            f"  {_site_c_plan_specs(plan)} · {price}/月\n"
            f'  <a href="{_html_attr(url)}">🛍️ 直达链接</a>'
        )
    return "\n".join(parts)


def notify_site_c_price_drops(price_drops):
    if not price_drops:
        return ""
    parts = [f"💰 #incudal #降价 ({len(price_drops)} 个)"]
    for item in price_drops[:20]:
        package, plan = item["package"], item["plan"]
        url = SITE_C_DEPLOY_URL.format(package_id=_site_c_id(package))
        old_p = _site_c_format_price(item["old_price"])
        new_p = _site_c_format_price(item["new_price"])
        parts.append(
            f"\n📍 <b>{_site_c_package_name(package)}</b> · {_site_c_plan_name(plan)}\n"
            f"  {old_p}/月 → {new_p}/月\n"
            f'  <a href="{_html_attr(url)}">🛍️ 直达链接</a>'
        )
    return "\n".join(parts)


def monitor_site_c(state):
    packages = fetch_site_c()
    if not packages:
        log.info("site-c polled 0 packages (api=%s, auth=%s)", SITE_C_API_URL, bool(SITE_C_TOKEN))
        return 0, 0, 0
    new_arrivals, restocked_pkgs, restocked_plans, price_drops, new_state = compare_site_c(state, packages)
    state["packages"] = new_state
    if state.get("first_run", True):
        state["first_run"] = False
        log.info("site-c first run: loaded %d packages (no notify, auth=%s)", len(new_state), bool(SITE_C_TOKEN))
        return 0, 0, 0
    if new_arrivals:
        send_tg(notify_site_c_new(new_arrivals))
    restock_msg = notify_site_c_restock(restocked_pkgs, restocked_plans)
    if restock_msg:
        send_tg(restock_msg)
    drop_msg = notify_site_c_price_drops(price_drops)
    if drop_msg:
        send_tg(drop_msg)
    return len(new_arrivals), len(restocked_pkgs) + len(restocked_plans), len(price_drops)


# ============================================================
# Main loop
# ============================================================
# Site D: DediRock Promo VPS (HTML 解析 + 活动标识)
# 整合自独立脚本 /opt/dedirock-monitor/dedirock_promo_watch.py v2.1.0
# ============================================================

_SITE_D_DEFAULT_PRODUCTS = [
    {
        "code": "LA",
        "name": "Promo VPS Saver LA BF",
        "url": "https://billing.dedirock.com/index.php/store/promo-vps-los-angeles",
        "buy_link": "https://billing.dedirock.com/index.php/store/promo-vps-los-angeles",
        "region": "Los Angeles",
        "expected_price": "9.88",
    },
    {
        "code": "NY",
        "name": "Promo VPS Saver NY BF",
        "url": "https://billing.dedirock.com/index.php/store/promo-vp",
        "buy_link": "https://billing.dedirock.com/index.php/store/promo-vp",
        "region": "Buffalo, NY",
        "expected_price": "8.88",
    },
]


def _site_d_get_products():
    """从 .env 读 SITE_D_PRODUCTS_JSON, 失败回退默认 LA+NY"""
    if not SITE_D_PRODUCTS_JSON:
        return _SITE_D_DEFAULT_PRODUCTS
    try:
        return json.loads(SITE_D_PRODUCTS_JSON)
    except Exception as e:
        log.warning("site-d: SITE_D_PRODUCTS_JSON 解析失败, 用默认: %s", e)
        return _SITE_D_DEFAULT_PRODUCTS


def _site_d_fetch(url):
    """Returns (html, size_bytes) or (None, 0) on error"""
    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": SITE_D_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
            timeout=10,
            allow_redirects=True,
        )
        if r.status_code != 200:
            return None, 0
        return r.text, len(r.content)
    except Exception as e:
        log.warning("site-d fetch %s: %s", url, e)
        return None, 0


def _site_d_detect(html, expected_price):
    """Returns (status, campaign)"""
    in_stock = (
        "Promo VPS Saver" in html
        and f"{expected_price} USD" in html
        and "Order Now" in html
    )
    if not in_stock:
        return "out_of_stock", "no_product"
    m = re.search(r'id="product\d+-name">([^<]+)', html)
    if not m:
        return "in_stock", "no_product"
    name = m.group(1)
    if "BF" in name:
        return "in_stock", "BF"
    if "LET" in name:
        return "in_stock", "LET"
    return "in_stock", "regular"


def _site_d_check_product(p):
    """Returns (status, campaign). status may be cf_skip / fetch_retry."""
    html, size = _site_d_fetch(p["url"])
    if html is None:
        return "fetch_retry", "no_product"
    if size < SITE_D_CF_SIZE_THRESHOLD:
        return "cf_skip", "no_product"
    return _site_d_detect(html, p["expected_price"])


def _site_d_fmt_product(p, campaign, kind):
    """kind: restock / soldout / campaign_change"""
    if kind == "restock":
        return (
            f"\n📦 <b>{p['code']}</b>: {_html_escape(p['name'])}\n"
            f"   💰 ${p['expected_price']} USD/年\n"
            f"   🌐 {_html_escape(p['region'])}\n"
            f"   🖥️ 1vCore · 2GB · 30GB SSD · 2TB BW · 1Gbps\n"
            f"   ✨ 活动标识: {campaign}\n"
            f'   🛍️ 直达 → <a href="{_html_attr(p["buy_link"])}">立即下单</a>'
        )
    if kind == "soldout":
        return (
            f"\n📦 <b>{p['code']}</b>: {_html_escape(p['name'])}\n"
            f"   ⚠️ 已下架 / 售罄\n"
            f'   🔗 详情 → <a href="{_html_attr(p["buy_link"])}">查看链接</a>'
        )
    return (
        f"\n📦 <b>{p['code']}</b>: {_html_escape(p['name'])}\n"
        f"   🔄 新活动标识: {campaign}\n"
        f'   🛍️ 直达 → <a href="{_html_attr(p["buy_link"])}">查看链接</a>'
    )


def _site_d_format_notify(restock, soldout, campaign_change):
    sections = []
    if restock:
        items = "\n".join(_site_d_fmt_product(p, c, "restock") for p, c in restock)
        sections.append(f"🟢 ═══ DediRock 新上架 ═══\n\n{items}")
    if soldout:
        items = "\n".join(_site_d_fmt_product(p, c, "soldout") for p, c in soldout)
        sections.append(f"🔴 ═══ DediRock 缺货通知 ═══\n\n{items}")
    if campaign_change:
        items = "\n".join(_site_d_fmt_product(p, c, "campaign_change") for p, c in campaign_change)
        sections.append(f"🟡 ═══ DediRock 活动变更 ═══\n\n{items}")
    if not sections:
        return ""
    return "\n\n".join(sections) + f"\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n━━━━━━━━━━━━━━━━━━"


def monitor_site_d(state):
    """DediRock Promo 监控。Returns (n_restock, n_soldout, n_campaign_change)"""
    products = _site_d_get_products()
    old_products = state.get("products", {})
    new_products = {}
    restock, soldout, campaign_change = [], [], []

    for p in products:
        code = p["code"]
        old = old_products.get(code, {})
        old_status = old.get("status")
        old_campaign = old.get("campaign")
        new_status, new_campaign = _site_d_check_product(p)

        if new_status in ("cf_skip", "fetch_retry"):
            log.info("site-d: %s %s (was %s/%s), skip this round", code, new_status, old_status, old_campaign)
            if old_status:
                new_products[code] = old
            continue

        new_products[code] = {"status": new_status, "campaign": new_campaign}

        if state.get("first_run", True):
            continue

        if old_status and old_status != "in_stock" and new_status == "in_stock":
            restock.append((p, new_campaign))
        elif old_status == "in_stock" and new_status != "in_stock":
            soldout.append((p, new_campaign))
        elif old_status == "in_stock" and new_status == "in_stock" and old_campaign != new_campaign:
            campaign_change.append((p, new_campaign))

    state["products"] = new_products
    if state.get("first_run", True):
        state["first_run"] = False
        log.info("site-d: first run, loaded %d products (no notify)", len(new_products))
        return 0, 0, 0

    # 总是 log (让运维能实时看到 site-d 在主循环里跑, 即便 0 变化)
    log.info("site-d: polled %d products (restock=%d, soldout=%d, campaign_change=%d)",
             len(new_products), len(restock), len(soldout), len(campaign_change))

    if restock or soldout or campaign_change:
        msg = _site_d_format_notify(restock, soldout, campaign_change)
        if msg:
            send_tg(msg)
    return len(restock), len(soldout), len(campaign_change)


# ============================================================
# Main loop
# ============================================================

def main():
    log.info("vps-monitor starting")
    state = load_state()
    # NOTIFY_ONLY_CHANGES=true（默认）: 重启后仅推送真正的补货/新套餐，不重复推已有库存
    if os.environ.get("NOTIFY_ONLY_CHANGES", "true").lower() in ("true","1","yes"):
        state.setdefault("site_a",{}).setdefault("first_run", True)

    running = True

    def stop(*_):
        nonlocal running
        running = False
        log.info("stop signal received")

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    last_a = last_b = last_c = last_d = 0

    while running:
        now = int(time.time())

        # 每个 site 独立 try/except (一个挂不全挂, site_a 慢不阻塞 site_d/site_c)
        try:
            # Site A
            if now - last_a >= SITE_A_POLL_INTERVAL:
                last_a = now
                if SITE_A_TOKEN:
                    n_new, n_restock = monitor_site_a(state["site_a"])
                    if n_new or n_restock:
                        log.info("site-a: %d new, %d restocked", n_new, n_restock)
                else:
                    log.debug("site-a skipped (no token)")
        except Exception as e:
            log.exception("site-a poll failed: %s", e)

        # 56idc disabled: site_b
        pass

        try:
            # Site D (DediRock Promo)
            if now - last_d >= SITE_D_POLL_INTERVAL:
                last_d = now
                n_restock, n_soldout, n_campaign = monitor_site_d(state["site_d"])
                if n_restock or n_soldout or n_campaign:
                    log.info("site-d: %d restock, %d soldout, %d campaign change",
                             n_restock, n_soldout, n_campaign)
        except Exception as e:
            log.exception("site-d poll failed: %s", e)

        try:
            # Site C
            if now - last_c >= SITE_C_POLL_INTERVAL:
                last_c = now
                n_new, n_restock, n_drop = monitor_site_c(state["site_c"])
                if n_new or n_restock or n_drop:
                    log.info("site-c: %d new, %d restock, %d drop",
                             n_new, n_restock, n_drop)
        except Exception as e:
            log.exception("site-c poll failed: %s", e)

        try:
            state["last_poll"] = now
            save_state(state)
        except Exception as e:
            log.exception("save_state failed: %s", e)

        for _ in range(POLL_INTERVAL):
            if not running:
                break
            time.sleep(1)

    log.info("vps-monitor stopped")


# ============================================================
# CLI: --once 跑一次就退出 (调试用)
# ============================================================

import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="只跑一次 poll 然后退出")
    parser.add_argument("--site", choices=["a", "b", "c", "d", "all"], default="all",
                        help="--once 时只跑某个 source")
    args = parser.parse_args()
    if args.once:
        state = load_state()
        if args.site in ("a", "all") and SITE_A_TOKEN:
            n_new, n_restock = monitor_site_a(state["site_a"])
            print(f"site-a: {n_new} new, {n_restock} restocked")
        if args.site in ("b", "all"):
            n_new, n_restock = monitor_site_b(state["site_b"])
            print(f"site-b: {n_new} new, {n_restock} restocked")
        if args.site in ("c", "all"):
            n_new, n_restock, n_drop = monitor_site_c(state["site_c"])
            print(f"site-c: {n_new} new, {n_restock} restock, {n_drop} drop")
        if args.site in ("d", "all"):
            n_restock, n_soldout, n_campaign = monitor_site_d(state["site_d"])
            print(f"site-d: {n_restock} restock, {n_soldout} soldout, {n_campaign} campaign")
        save_state(state)
    else:
        main()
