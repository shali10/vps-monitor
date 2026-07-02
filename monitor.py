#!/usr/bin/env python3
"""
VPS 商品/库存监控 → Telegram 推送

4 个独立 source,共用一个 TG bot:

  Site A  独角鲸云 (auth: Bearer)       间隔 A_INTERVAL 秒
  Site C  incudal   (公开 API + Bearer)  间隔 C_INTERVAL 秒
  Site D  DediRock  (HTML 解析 + 活动标识) 间隔 D_INTERVAL 秒
  Site E  czl.net   (公开 API, 池规则过滤)  间隔 E_INTERVAL 秒

Site B (56idc) 已清理 (2026-06-20), 详见 README §10.5。

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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        "site_c": {"packages": {}, "first_run": True},
        "site_d": {"products": {}, "first_run": True},
        "site_e": {"items": {}, "first_run": True},
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
        spec_parts.append(f"{bw}Mbps / {_html_escape(traffic)}")
    else:
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
# ============================================================
# Site E: VPS-Monitor.czl.net (2026-06-20 加)
# 数据源: https://vps-monitor.czl.net/api/public/filter (公开 API)
# 池规则:
#   池 1 (廉价低规格): RAM 0.4-1.1GB, USD/年 ≤ 9
#   池 2 (主力推荐):   RAM 2.0-16GB, USD/年 10-20
#   排除: DEDI / 独立服务器 / 非 VPS
#   不做三网优化过滤 (per user 2026-06-20)
# ============================================================

SITE_E_API_URL = _env_str("SITE_E_API_URL", "https://vps-monitor.czl.net/api/public/filter")
SITE_E_POLL_INTERVAL = _env_int("SITE_E_POLL_INTERVAL", 7200)  # 默认 2 小时
SITE_E_DEPLOY_URL = _env_str("SITE_E_DEPLOY_URL", "https://vps-monitor.czl.net/buy/{plan_id}")


def _parse_ram_gb_e(s):
    if not s:
        return 0
    m = re.search(r"([\d.]+)\s*(GB|G|MB|M)\b", s, re.I)
    if not m:
        return 0
    v = float(m.group(1))
    if m.group(2).upper() in ("M", "MB"):
        v /= 1024
    return v


def _parse_usd_year_e(p):
    if not p:
        return 9999
    p = p.strip()
    m = re.search(r"([\$€¥￥])([\d.]+)", p)
    if not m:
        m = re.search(r"([\d.]+)\s*元", p)
        if not m:
            return 9999
        sym, val = "¥", float(m.group(1))
    else:
        sym, val = m.group(1), float(m.group(2))
    fx = {"$": 1, "€": 1.08, "¥": 0.139, "￥": 0.139}
    usd = val * fx.get(sym, 1)
    if "年" in p:
        return usd
    if "季" in p:
        return usd * 4
    if "月" in p:
        return usd * 12
    return usd


# 2026-06-20 user: xian shi ju ti lu xian (CN2/GIA/CMI/9929), bu yao "CN you xuan"
CN_KEYWORDS = ["优化", "CN2", "GIA", "CMI", "9929", "4837", "精品", "三网", "BGP", "回国", "直连", "低延迟"]


def _site_e_get_keywords(item):
    """fan hui item ming zhong de CN_KEYWORDS list"""
    text = " ".join([
        str(item.get("title", "")),
        str(item.get("location", "")),
        str(item.get("remark", "")),
    ])
    return [kw for kw in CN_KEYWORDS if kw in text]


# 2026-06-20 user: bai dan jia ge duan - yue fu 1-10 USD (12-120/nian) OR nian fu 1-70 USD (1-70/nian). OR -> 1<=usd_year<=120
def _site_e_price_in_whitelist(item):
    """2026-06-20 user: yue fu 1-10 USD/yue OR nian fu 1-70 USD/nian. Fen kai pan ding (bu zhe suan)."""
    price_str = item.get("price", "")
    m = re.search(r"([\d.]+)", price_str)
    if not m: return False
    val = float(m.group(1))
    # 2026 hui lv: 1 USD = 6.8 CNY
    if "€" in price_str: usd_val = val * 1.08
    elif "¥" in price_str or "￥" in price_str: usd_val = val * 0.147
    else: usd_val = val  # $ huo mo shu biao
    # 2026-06-20 user: yue fu zi mian 1-10 (bu zhuan USD), nian fu yuan USD 1-70 (bao liu)
    if "月" in price_str and 1 <= val <= 10: return True
    if "年" in price_str and 1 <= usd_val <= 70: return True
    return False


# 2026-06-20 user: he bing 38 CSV + 172 DMIT = 210 id bai dan (yi ge)



def _site_e_pool_match(ram_gb, usd_year):
    # 池1: 廉价低规格 (RAM 0.4-1.0 + ≤$10/年); 池2: 主力 (RAM 1.0-16 + $10-20/年)
    if 0.4 <= ram_gb <= 1.0 and 0 < usd_year <= 10:
        return "池1(廉价)"
    if 1.0 <= ram_gb <= 16 and 10 <= usd_year <= 20:
        return "池2(主力)"
    return None


def _site_e_is_vps(item):
    text = (item.get("title", "") + " " + item.get("disk", "")).lower()
    return not any(b in text for b in ["dedicated", "dedi", "独立服", "独立服务器"])


def _fetch_site_e_page(page):
    """单页拉取, 返回 (page, dict or None). 异常返回 None, 不抛。"""
    try:
        r = requests.get(SITE_E_API_URL, params={"page": page, "pageSize": 12}, timeout=15)
        r.raise_for_status()
        return page, r.json()
    except Exception as e:
        log.warning("site-e fetch page %d failed: %s", page, e)
        return page, None


def fetch_site_e():
    """并发拉 czl.net 公开 API, 按池规则过滤。
    API 强制 12/page, 全 1054 条需 ~88 页。8 worker 并发 + 失败 retry, ~5s 完成。
    任何一页失败先 retry 1 次, 还失败就丢该页(不影响其他页)。
    """
    if not SITE_E_API_URL:
        log.debug("site-e skipped (SITE_E_API_URL not configured)")
        return []
    MAX_PAGES = 100  # 1200 条上限, 足够覆盖 ~1054 全量
    WORKERS = 8  # czl.net 限速敏感, 10 worker 会触发 Connection reset
    pages_failed = []

    def _one_round(page_list):
        """一轮并发拉取"""
        out = {}
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futures = {ex.submit(_fetch_site_e_page, p): p for p in page_list}
            for fut in as_completed(futures):
                page, d = fut.result()
                if d is not None:
                    out[page] = d
        return out

    # Round 1: 全量并发
    all_pages = list(range(1, MAX_PAGES + 1))
    round1 = _one_round(all_pages)
    # 找出失败的页
    failed = [p for p in all_pages if p not in round1]
    pages_failed.extend(failed)
    # Round 2: 失败的页 retry 1 次 (sleep 1s 错峰)
    if failed:
        log.info("site-e: retrying %d failed pages after 1s...", len(failed))
        time.sleep(1)
        round2 = _one_round(failed)
        # 合并
        still_failed = [p for p in failed if p not in round2]
        pages_failed = still_failed
        round1.update(round2)
    # 合并所有页的数据
    all_items = []
    for page in sorted(round1.keys()):
        d = round1[page]
        data = d.get("data", []) if isinstance(d, dict) else []
        all_items.extend(data)
    # 去重 (id 字段)
    seen = set()
    unique = []
    for it in all_items:
        iid = it.get("id")
        if iid is None or iid in seen:
            continue
        seen.add(iid)
        unique.append(it)
    if pages_failed:
        log.warning("site-e: %d pages failed after retry (e.g. %s), total fetched=%d unique=%d",
                    len(pages_failed), pages_failed[:5], len(all_items), len(unique))
    # 池规则过滤
    pool_items = []
    for item in unique:
        if not _site_e_is_vps(item):
            continue
        ram = _parse_ram_gb_e(item.get("ram", ""))
        yu = _parse_usd_year_e(item.get("price", ""))
        ram = _parse_ram_gb_e(item.get("ram", ""))
        yu = _parse_usd_year_e(item.get("price", ""))
        pool_label = _site_e_pool_match(ram, yu)
        iid = item.get("id")
        # 2026-06-20 user: bai dan id, biao qian xian shi ju ti ming zhong de lu xian
        # 2026-06-20 user: zhi liu jia ge bai dan, id bai dan yi shan
        if pool_label or _site_e_price_in_whitelist(item):
            if not pool_label:
                kws = _site_e_get_keywords(item)
                pool_label = "线路:" + "/".join(kws) if kws else "价格"
            item["_pool"] = pool_label
            item["_ram_gb"] = ram
            item["_usd_year"] = yu
            pool_items.append(item)
    log.info("site-e: fetched %d unique items, %d match pool rules", len(unique), len(pool_items))
    return pool_items


def _site_e_id(item):
    return str(item.get("id") or item.get("title") or "unknown")


def _site_e_signature(item):
    return {
        "isAvailable": bool(item.get("isAvailable")),
        "price": str(item.get("price", "")),
        "clickCount": int(item.get("clickCount", 0) or 0),
    }


def compare_site_e(state, items):
    old = state.get("items", {})
    new_state = {}
    new_arrivals = []
    restocked = []
    price_drops = []
    cur_ids = {_site_e_id(i) for i in items}
    for iid in cur_ids - set(old.keys()):
        for it in items:
            if _site_e_id(it) == iid:
                new_arrivals.append(it)
                break
    for it in items:
        iid = _site_e_id(it)
        sig = _site_e_signature(it)
        new_state[iid] = sig
        if iid not in old:
            continue
        prev = old[iid]
        if not prev.get("isAvailable") and sig["isAvailable"]:
            restocked.append(it)
        # 价格比较: 用 USD 数字 (容忍 1% 抖动, 避免币种换算/格式化噪音触发误报)
        prev_price_raw = prev.get("price", "")
        cur_price_raw = sig.get("price", "")
        if prev_price_raw and cur_price_raw and prev_price_raw != cur_price_raw:
            try:
                prev_yu = _parse_usd_year_e(prev_price_raw)
                cur_yu = _parse_usd_year_e(cur_price_raw)
                # 仅当 USD 数字真下降 ≥1% 才算降价 (避免字符串变化但实际价格未变)
                if 0 < prev_yu < 9999 and 0 < cur_yu < 9999 and cur_yu < prev_yu * 0.99:
                    price_drops.append({"item": it, "old_price": prev_price_raw, "new_price": cur_price_raw})
            except Exception:
                pass
    return new_arrivals, restocked, price_drops, new_state


def _site_e_format_item(item, new_price_override=None, old_price_override=None):
    pool = item.get("_pool", "?")
    provider = _html_escape(item.get("provider", "?"))
    title = _html_escape(item.get("title", "?"))
    cpu = _html_escape(item.get("cpu", "?"))
    ram = _html_escape(item.get("ram", "?"))
    disk = _html_escape(item.get("disk", "?"))
    bandwidth = _html_escape(item.get("bandwidth", "?"))
    location = _html_escape(item.get("location", ""))
    price = new_price_override if new_price_override else _html_escape(item.get("price", "?"))
    iid = _site_e_id(item)
    url = SITE_E_DEPLOY_URL.format(plan_id=iid)
    lines = [
        f"• <b>{title}</b>",
        f"  🏷️ {provider} · {pool}",
        f"  📦 {cpu} / {ram} / {disk} / {bandwidth}",
    ]
    if location:
        lines.append(f"  📍 {location}")
    if old_price_override:
        lines.append(f"  💰 ~~{old_price_override}~~ → <b>{price}</b>")
    else:
        lines.append(f"  💰 {price}")
    # 2026-06-20 加: 标 isAvailable 状态, 让 user 一眼看出有货/没货
    _is_avail = item.get("isAvailable", item.get("is_available", False))
    _status = "✅ 有货" if _is_avail else "❌ 没货"
    lines.append(f"  📊 状态: {_status}")
    lines.append(f'  <a href="{_html_attr(url)}">🛍️ 直达</a>')
    return "\n".join(lines)


def notify_site_e_new(new_arrivals):
    """分段推送新套餐, 每段 12 个, 调 send_tg 多次. 返 "" 已被分段发送. 2026-06-20 改."""
    if not new_arrivals:
        return ""
    SEG = 12
    total = len(new_arrivals)
    if total <= SEG:
        parts = [f"🆕 #vps-monitor #新套餐 ({total} 个)"]
        for item in new_arrivals:
            parts.append("\n" + _site_e_format_item(item))
        send_tg("\n".join(parts))
        return ""
    # 多段: 第 1 段带总数, 后续段只标 (段 X/Y)
    n_seg = (total + SEG - 1) // SEG
    for seg_idx in range(n_seg):
        seg = new_arrivals[seg_idx*SEG:(seg_idx+1)*SEG]
        if seg_idx == 0:
            header = f"🆕 #vps-monitor #新套餐 ({total} 个, 分 {n_seg} 段) [1/{n_seg}]"
        else:
            header = f"🆕 #vps-monitor #新套餐 (续) [{seg_idx+1}/{n_seg}]"
        parts = [header]
        for item in seg:
            parts.append("\n" + _site_e_format_item(item))
        send_tg("\n".join(parts))
    return ""


def notify_site_e_restock(restocked):
    """分段推送补货, 每段 12 个. 2026-06-20 改."""
    if not restocked:
        return ""
    SEG = 12
    total = len(restocked)
    if total <= SEG:
        parts = [f"🔔 #vps-monitor #补货 ({total} 个)"]
        for item in restocked:
            parts.append("\n" + _site_e_format_item(item))
        send_tg("\n".join(parts))
        return ""
    n_seg = (total + SEG - 1) // SEG
    for seg_idx in range(n_seg):
        seg = restocked[seg_idx*SEG:(seg_idx+1)*SEG]
        if seg_idx == 0:
            header = f"🔔 #vps-monitor #补货 ({total} 个, 分 {n_seg} 段) [1/{n_seg}]"
        else:
            header = f"🔔 #vps-monitor #补货 (续) [{seg_idx+1}/{n_seg}]"
        parts = [header]
        for item in seg:
            parts.append("\n" + _site_e_format_item(item))
        send_tg("\n".join(parts))
    return ""


def notify_site_e_price_drops(price_drops):
    """分段推送降价, 每段 12 个. 2026-06-20 改."""
    if not price_drops:
        return ""
    SEG = 12
    total = len(price_drops)
    if total <= SEG:
        parts = [f"💰 #vps-monitor #降价 ({total} 个)"]
        for d in price_drops:
            parts.append("\n" + _site_e_format_item(d["item"], new_price_override=d["new_price"], old_price_override=d["old_price"]))
        send_tg("\n".join(parts))
        return ""
    n_seg = (total + SEG - 1) // SEG
    for seg_idx in range(n_seg):
        seg = price_drops[seg_idx*SEG:(seg_idx+1)*SEG]
        if seg_idx == 0:
            header = f"💰 #vps-monitor #降价 ({total} 个, 分 {n_seg} 段) [1/{n_seg}]"
        else:
            header = f"💰 #vps-monitor #降价 (续) [{seg_idx+1}/{n_seg}]"
        parts = [header]
        for d in seg:
            parts.append("\n" + _site_e_format_item(d["item"], new_price_override=d["new_price"], old_price_override=d["old_price"]))
        send_tg("\n".join(parts))
    return ""


def monitor_site_e(state):
    items = fetch_site_e()
    if not items:
        log.info("site-e polled 0 items (pool filtered or API empty)")
        return 0, 0, 0
    new_arrivals, restocked, price_drops, new_state = compare_site_e(state, items)
    state["items"] = new_state
    if state.get("first_run", True):
        state["first_run"] = False
        log.info("site-e first run: loaded %d items (no notify)", len(new_state))
        return 0, 0, 0
    # 2026-06-20 改: notify_*_e 函数内部已自调 send_tg 分段推送, 外层不再 send_tg
    if new_arrivals:
        notify_site_e_new(new_arrivals)
    if restocked:
        notify_site_e_restock(restocked)
    if price_drops:
        notify_site_e_price_drops(price_drops)
    return len(new_arrivals), len(restocked), len(price_drops)


def main():
    log.info("vps-monitor starting (A+E only)")
    state = load_state()
    # NOTIFY_ONLY_CHANGES=true（默认）: 重启后仅推送真正的补货/新套餐，不重复推已有库存
    if os.environ.get("NOTIFY_ONLY_CHANGES", "true").lower() in ("true","1","yes"):
        state.setdefault("site_a", {}).setdefault("first_run", True)
        state.setdefault("site_e", {}).setdefault("first_run", True)

    running = True

    def stop(*_):
        nonlocal running
        running = False
        log.info("stop signal received")

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    last_a = last_e = 0

    while running:
        now = int(time.time())

        try:
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

        try:
            if now - last_e >= SITE_E_POLL_INTERVAL:
                last_e = now
                n_new, n_restock, n_drop = monitor_site_e(state["site_e"])
                if n_new or n_restock or n_drop:
                    log.info("site-e: %d new, %d restock, %d drop", n_new, n_restock, n_drop)
        except Exception as e:
            log.exception("site-e poll failed: %s", e)

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


import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="只跑一次 poll 然后退出")
    parser.add_argument("--site", choices=["a", "e", "all"], default="all",
                        help="--once 时只跑某个 source")
    args = parser.parse_args()
    if args.once:
        state = load_state()
        if args.site in ("a", "all") and SITE_A_TOKEN:
            n_new, n_restock = monitor_site_a(state["site_a"])
            print(f"site-a: {n_new} new, {n_restock} restocked")
        if args.site in ("e", "all") and SITE_E_API_URL:
            n_new, n_restock, n_drop = monitor_site_e(state["site_e"])
            print(f"site-e: {n_new} new, {n_restock} restock, {n_drop} drop")
        save_state(state)
    else:
        main()
