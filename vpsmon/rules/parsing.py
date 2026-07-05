from __future__ import annotations

import re

FX = {
    "$": 1.0,
    "€": 1.08,
    "¥": 0.139,
    "￥": 0.139,
    "元": 0.139,
}


def parse_ram_gb(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    m = re.match(r"^([\d.]+)\s*(G|GB|M|MB)?", text)
    if not m:
        return None
    amount = float(m.group(1))
    unit = m.group(2) or "G"
    if unit.startswith("M"):
        return amount / 1024
    return amount


def parse_cpu_cores(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    m = re.match(r"([\d.]+)\s*(?:Core|Cores|vCore|vCores|C)?", text, re.I)
    if not m:
        return None
    return float(m.group(1))


def parse_usd_year(price: object) -> float | None:
    if price is None:
        return None
    text = str(price).strip()
    m = re.search(r"([$€¥￥])\s*([\d.]+)", text)
    if m:
        symbol, amount = m.group(1), float(m.group(2))
    else:
        m = re.search(r"([\d.]+)\s*元", text)
        if not m:
            return None
        symbol, amount = "元", float(m.group(1))
    usd = amount * FX.get(symbol, 1.0)
    if "月" in text:
        return usd * 12
    if "季" in text:
        return usd * 4
    return usd


def parse_monthly_usd(price: object) -> float | None:
    yearly = parse_usd_year(price)
    if yearly is None:
        return None
    return yearly / 12
