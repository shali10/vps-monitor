"""Pure utility functions — formatting, parsing, HTML escaping, pooling logic."""
import html
import re


def _fmt_bytes(n):
    """Auto-scale bytes to B/KB/MB/GB/TB."""
    n = int(n) if n else 0
    for unit, base in [("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)]:
        if n >= base:
            return f"{n/base:.0f}{unit}" if n % base == 0 else f"{n/base:.1f}{unit}"
    return f"{n}B"


def _fmt_cny(cents):
    """Cents (分) → '¥X.XX'."""
    try:
        return f"¥{int(cents)/100:.2f}"
    except (TypeError, ValueError):
        return f"¥{cents}"


def _fmt_usd(value):
    """USD number → '$X'."""
    try:
        return f"${float(value):g}"
    except (TypeError, ValueError):
        return f"${value}"


def _html_escape(value):
    """HTML-escape for text content (no quotes)."""
    return html.escape(str(value if value is not None else ""), quote=False)


def _html_attr(value):
    """HTML-escape for attribute values (with quotes)."""
    return html.escape(str(value if value is not None else ""), quote=True)


def _fmt_ram_mb(mb):
    """Format RAM in MB; upgrade to GB if ≥ 1024 and round."""
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
    """Format monthly traffic in GB; '不限流量' if ≤ 0."""
    try:
        gb = float(gb or 0)
    except (TypeError, ValueError):
        return ""
    if gb <= 0:
        return "不限流量"
    return f"{gb:g}GB BW"


# CN route keywords detectable in plan titles/descriptions
CN_KEYWORDS = ["优化", "CN2", "GIA", "CMI", "9929", "4837", "精品", "三网", "BGP", "回国", "直连", "低延迟"]


# ========== Site-E specific utils ==========

def _parse_ram_gb_e(s):
    """Parse RAM string like '1G' / '2048M' / '512MB' → float GB."""
    if s is None:
        return 0.0
    s = str(s).strip().upper()
    m = re.match(r"^([\d.]+)\s*(G|GB|M|MB)?$", s)
    if not m:
        return 0.0
    val = float(m.group(1))
    unit = m.group(2) or "G"
    if unit.startswith("M"):
        return val / 1024
    return val


_FX = {
    "$": 1,
    "€": 1.08,
    "¥": 0.139,
    "￥": 0.139,
    "元": 0.139,
}


def _parse_usd_year_e(p):
    """Convert any raw price string to USD/year.

    Supports $, €, ¥, ￥, 元. Handles 年/季/月 period conversion.
    Returns 9999 for unparseable values (safely out of any pool range).
    """
    if not p:
        return 9999
    p = p.strip()
    m = re.search(r"([$€¥￥])([\d.]+)", p)
    if not m:
        m = re.search(r"([\d.]+)\s*元", p)
        if not m:
            return 9999
        sym, val = "¥", float(m.group(1))
    else:
        sym, val = m.group(1), float(m.group(2))
    usd = val * _FX.get(sym, 1)
    if "年" in p:
        return usd
    if "季" in p:
        return usd * 4
    if "月" in p:
        return usd * 12
    return usd


def _site_e_get_keywords(item):
    """Return list of CN_KEYWORDS found in item's text fields."""
    text = " ".join([
        str(item.get("title", "")),
        str(item.get("location", "")),
        str(item.get("remark", "")),
    ])
    return [kw for kw in CN_KEYWORDS if kw in text]


def _site_e_price_in_whitelist(item):
    """Yearly plan: 1-70 USD/year; Monthly plan: 1-10 USD/month."""
    price_str = item.get("price", "")
    m = re.search(r"([\d.]+)", price_str)
    if not m:
        return False
    val = float(m.group(1))
    if "€" in price_str:
        usd_val = val * 1.08
    elif "¥" in price_str or "￥" in price_str:
        usd_val = val * 0.139
    else:
        usd_val = val
    if "月" in price_str and 1 <= val <= 10:
        return True
    if "年" in price_str and 1 <= usd_val <= 70:
        return True
    return False


def _site_e_pool_match(ram_gb, usd_year):
    """Map (RAM, price) → pool label.

    - 池1(廉价): 0.4 ≤ RAM ≤ 1.0, 0 < price ≤ $10/年
    - 池2(主力): 1.0 ≤ RAM ≤ 16, $10 ≤ price ≤ $20/年
    - None: outside all pools
    """
    if 0.4 <= ram_gb <= 1.0 and 0 < usd_year <= 10:
        return "池1(廉价)"
    if 1.0 <= ram_gb <= 16 and 10 <= usd_year <= 20:
        return "池2(主力)"
    return None
