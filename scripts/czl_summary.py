from __future__ import annotations

import argparse
from collections import OrderedDict
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vpsmon.config import load_config
from vpsmon.notifiers.telegram import format_offer, send_telegram_messages, split_blocks
from vpsmon.rules.filtering import filter_offers, pool_name
from vpsmon.sources.czl import CzlSource


def _fmt_ram(ram_gb):
    if ram_gb is None:
        return "?"
    if ram_gb >= 1 and ram_gb == int(ram_gb):
        return f"{int(ram_gb)}GB"
    if ram_gb >= 1:
        return f"{ram_gb:.1f}GB"
    return f"{ram_gb * 1024:.0f}MB"


def _fmt_cpu(cpu):
    if cpu is None:
        return "?"
    if cpu == int(cpu):
        return f"{int(cpu)}vCore"
    return f"{cpu:g}vCore"


def _stock_text(offer):
    if not offer.available:
        return "🔴 售罄"
    if offer.stock is not None and offer.stock > 0:
        return f"🟢 有货 ×{offer.stock}"
    return "🟢 有货"


def _pool_index(offer, pools):
    name = pool_name(offer, pools)
    if not name:
        return 999, ""
    for idx, pool in enumerate(pools):
        if str(pool.get("name") or "pool") == name:
            return idx, name
    return 998, name


def _tag(provider: str) -> str:
    aliases = {
        "腾讯云": "tencentcloud",
        "搬瓦工": "banwagong",
        "独角鲸云": "dujiaojing",
    }
    text = (provider or "未知厂商").strip()
    clean = aliases.get(text, text).lower()
    clean = re.sub(r"[^a-z0-9_\-]+", "", clean).strip("-_")
    return f"#{clean}" if clean else "#unknown"


def _provider_sort_key(items, pools):
    best = min((_pool_index(offer, pools)[0], offer.price.usd_year if offer.price else 10**9) for offer in items)
    return best


def _provider_header(provider: str, items: list, total_available: int) -> str:
    tag = _tag(provider)
    return f"📊 <b>czl.net 精选 · {provider}</b>\n━━━━━━━━━━━━━━━━━━━━\n🏷️ {tag} · 本段 <b>{len(items)}</b> / 有货 <b>{total_available}</b>"


def _live_available(offer, timeout=12):
    """Best-effort final cart page stock verification for czl summary.

    czl.net isAvailable can be stale when provider stock check is disabled.
    Follow the buy redirect and reject obvious cart/product out-of-stock pages.
    Network failures return False for summary accuracy.
    """
    try:
        resp = requests.get(
            offer.url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (vps-monitor stock verifier)"},
        )
        text = resp.text.lower()
        bad_markers = (
            "out of stock",
            "sold out",
            "currently out of stock",
            "orders for it have been suspended",
            "库存不足",
            "缺货",
            "售罄",
            "無庫存",
            "unavailable",
        )
        if resp.status_code >= 400:
            return False
        return not any(marker in text for marker in bad_markers)
    except Exception:
        return False


def _format_summary_offer(offer, source_rules):
    """Use the shared offer card, but remove repeated provider/tag lines inside a provider section."""
    tag = _tag(offer.provider or "")
    lines = []
    for line in format_offer(offer, source_rules).splitlines():
        stripped = line.strip()
        if "🏷️" in stripped:
            continue
        if tag and stripped.endswith(tag):
            line = line[: -len(tag)].rstrip()
        if stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def build_messages(config_path: str, limit: int):
    config = load_config(config_path)
    source_cfg = config["sources"]["czl"]
    source_rules = config.get("rules", {}).get("czl", {})
    global_rules = config.get("rules", {}).get("global", {})
    pools = source_rules.get("pools", [])

    raw = CzlSource(source_cfg).fetch()
    filtered = filter_offers(raw, source_rules, global_rules)
    available = [offer for offer in filtered if offer.available]
    available.sort(key=lambda offer: (
        _pool_index(offer, pools)[0],
        offer.price.usd_year if offer.price else 10**9,
        (offer.provider or ""),
        offer.offer_id,
    ))
    selected = []
    checked = 0
    skipped_live = 0
    # Verify candidates against the final provider cart page before showing them.
    # This avoids stale czl.net isAvailable entries, especially providers with disabled stock check.
    for offer in available:
        checked += 1
        if _live_available(offer):
            selected.append(offer)
            if len(selected) >= limit:
                break
        else:
            skipped_live += 1
        if checked >= max(limit * 8, 40):
            break

    by_provider: OrderedDict[str, list] = OrderedDict()
    for offer in selected:
        by_provider.setdefault(offer.provider or "未知厂商", []).append(offer)

    ordered_groups = sorted(by_provider.items(), key=lambda item: _provider_sort_key(item[1], pools))
    messages: list[str] = []
    for provider, items in ordered_groups:
        header = _provider_header(provider, items, len(available))
        blocks = [_format_summary_offer(offer, source_rules) for offer in items]
        messages.extend(split_blocks(header, blocks))

    return messages, {"raw": len(raw), "filtered": len(filtered), "available": len(available), "selected": len(selected), "providers": len(ordered_groups), "live_checked": checked, "live_skipped": skipped_live}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/opt/vps-monitor/config.json")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()

    messages, stats = build_messages(args.config, args.limit)
    print("czl_summary", " ".join(f"{k}={v}" for k, v in stats.items()), f"messages={len(messages)}")
    if args.send:
        config = load_config(args.config)
        sent = send_telegram_messages(messages, config.get("telegram", {}))
        print(f"telegram_sent={sent} messages={len(messages)}")
    else:
        for i, message in enumerate(messages, 1):
            print(f"\n--- message {i}/{len(messages)} chars={len(message)} ---")
            print(message[:4000])


if __name__ == "__main__":
    main()
