from __future__ import annotations

from collections import OrderedDict
import html
import os
import re

import requests

from vpsmon.models import Event, EventType, VpsOffer
from vpsmon.rules.filtering import pool_name

SOURCE_LABELS = {
    "dujiaojing": "独角鲸云",
    "czl": "czl.net",
}


def _source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def _fmt_ram(ram_gb: float | None) -> str:
    if ram_gb is None:
        return "?"
    if ram_gb >= 1 and ram_gb == int(ram_gb):
        return f"{int(ram_gb)}GB"
    if ram_gb >= 1:
        return f"{ram_gb:.1f}GB"
    return f"{ram_gb * 1024:.0f}MB"


def _fmt_cpu(cpu: float | None) -> str:
    if cpu is None:
        return "?"
    if cpu == int(cpu):
        return f"{int(cpu)}vCore"
    return f"{cpu:g}vCore"


def _stock_text(offer: VpsOffer) -> str:
    if not offer.available:
        return "🔴 售罄"
    if offer.stock is not None and offer.stock > 0:
        return f"🟢 有货 ×{offer.stock}"
    return "🟢 有货"


def _compact(value: str, max_len: int = 64) -> str:
    text = re.sub(r"https?://\S+", "", value or "")
    text = re.sub(r"(?:NQ)\s*[:：]\s*", "", text, flags=re.I)
    text = re.sub(r"(?:测试\s*ip|测试IP|Test IP)\s*[:：]\s*\S+", "", text, flags=re.I)
    text = re.sub(r"更新时间\s*,?\s*\d{4}-\d{2}-\d{2}T\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ，,;；:：")
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def _tag(provider: str) -> str:
    clean = provider.replace("搬瓦工", "banwagong").lower()
    clean = re.sub(r"[^a-z0-9_\-]+", "", clean).strip("-_")
    if len(clean) < 3 or clean in {"hk", "us", "de", "ip", "vps"}:
        return ""
    return f"#{clean}"


def format_offer(offer: VpsOffer, source_rules: dict | None = None) -> str:
    source_rules = source_rules or {}
    pool = pool_name(offer, source_rules.get("pools", []))
    pool_part = f" · {pool}" if pool else ""
    price = offer.price.raw if offer.price else "?"
    route = _compact(offer.route, 72) or "未标注"
    specs = " / ".join(
        part for part in [
            _fmt_cpu(offer.cpu_cores),
            _fmt_ram(offer.ram_gb),
            offer.disk or "?",
            offer.bandwidth or "",
            offer.traffic or "",
        ] if part
    )
    title_bits = [_compact(offer.title, 54)]
    if offer.location:
        title_bits.append(_compact(offer.location, 42))
    lines = [
        f"📦 <b>{' · '.join(title_bits)}</b>",
        f"   💻 {_compact(specs, 118)}",
    ]
    if offer.provider:
        lines.append(f"   🏷️ {_compact(offer.provider, 42)}")
    lines.extend([
        f"   💰 {price} · {_stock_text(offer)}",
        f'   🛍️ <a href="{html.escape(offer.url, quote=True)}">直达购买</a>',
        f"   🌐 {route}{pool_part}",
    ])
    tag = _tag(offer.provider)
    if tag:
        lines.append(f"   {tag}")
    return "\n".join(lines)


def render_events(events: list[Event], rules_by_source: dict) -> list[str]:
    groups: OrderedDict[tuple[str, str, EventType], list[Event]] = OrderedDict()
    for event in events:
        key = (event.offer.source, event.offer.provider or "未知商家", event.event_type)
        groups.setdefault(key, []).append(event)

    messages: list[str] = []
    for (_source, provider, event_type), group in groups.items():
        title = {
            EventType.NEW: "新套餐",
            EventType.RESTOCK: "补货",
            EventType.PRICE_DROP: "降价",
        }[event_type]
        provider_label = _compact(provider, 42) or "未知商家"
        header = f"🔔 【{provider_label}】{title} ({len(group)} 个)"
        blocks = []
        for event in group:
            if event.event_type == EventType.PRICE_DROP:
                blocks.append(f"{format_offer(event.offer, rules_by_source.get(event.offer.source, {}))}\n   ↘ {event.old_price_raw} → {event.new_price_raw}")
            else:
                blocks.append(format_offer(event.offer, rules_by_source.get(event.offer.source, {})))
        messages.extend(split_blocks(header, blocks))
    return messages


def render_summary(events: list[Event]) -> list[str]:
    if not events:
        return []
    by_source: OrderedDict[str, dict[str, int]] = OrderedDict()
    by_provider: OrderedDict[str, int] = OrderedDict()
    for event in events:
        counts = by_source.setdefault(event.offer.source, {"new": 0, "restock": 0, "price_drop": 0})
        counts[event.event_type.value] += 1
        provider = event.offer.provider or "未知商家"
        by_provider[provider] = by_provider.get(provider, 0) + 1

    event_counts = {"new": 0, "restock": 0, "price_drop": 0}
    for counts in by_source.values():
        for key in event_counts:
            event_counts[key] += counts[key]

    headline_parts = [
        f"新 {event_counts['new']}" if event_counts["new"] else "",
        f"补货 {event_counts['restock']}" if event_counts["restock"] else "",
        f"降价 {event_counts['price_drop']}" if event_counts["price_drop"] else "",
    ]
    lines = [
        f"📊 VPS Monitor v4 事件摘要 · 共 {len(events)} 个",
        " / ".join(part for part in headline_parts if part),
        "",
        "按来源:",
    ]
    for source, counts in by_source.items():
        parts = [
            f"新 {counts['new']}" if counts["new"] else "",
            f"补货 {counts['restock']}" if counts["restock"] else "",
            f"降价 {counts['price_drop']}" if counts["price_drop"] else "",
        ]
        lines.append(f"  • {_source_label(source)}: " + " / ".join(part for part in parts if part))

    lines.extend(["", "Top 商家/母鸡:"])
    for provider, count in sorted(by_provider.items(), key=lambda item: item[1], reverse=True)[:12]:
        lines.append(f"  • {provider}: {count}")
    return split_blocks("", ["\n".join(lines)], max_chars=4000)


def send_telegram_messages(messages: list[str], telegram_config: dict) -> int:
    token = telegram_config.get("bot_token") or os.environ.get(telegram_config.get("bot_token_env", ""), "")
    chat_ids_raw = telegram_config.get("chat_ids") or os.environ.get(telegram_config.get("chat_ids_env", ""), "")
    chat_ids = [part.strip() for part in str(chat_ids_raw).replace(";", ",").split(",") if part.strip()]
    if not token or not chat_ids:
        raise RuntimeError("telegram token/chat ids missing")

    sent = 0
    for message in messages:
        for chat_id in chat_ids:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"telegram push failed chat_id={chat_id}: {data}")
            sent += 1
    return sent


def split_blocks(header: str, blocks: list[str], max_chars: int = 4000) -> list[str]:
    if not blocks:
        return []
    chunks: list[str] = []
    current = header
    separator = "\n\n" if header else ""
    for block in blocks:
        candidate = current + separator + block
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current != header:
            chunks.append(current)
            current = header
        if len(header) + 2 + len(block) <= max_chars:
            current = header + "\n\n" + block
        else:
            text = header + "\n\n" + block
            for i in range(0, len(text), max_chars):
                chunks.append(text[i:i + max_chars])
            current = header
    if current != header:
        chunks.append(current)
    return _add_page_suffix(chunks)


def _add_page_suffix(chunks: list[str]) -> list[str]:
    if len(chunks) <= 1:
        return chunks
    total = len(chunks)
    out = []
    for idx, chunk in enumerate(chunks, 1):
        first_line, _, rest = chunk.partition("\n")
        out.append(f"{first_line} ({idx}/{total})\n{rest}" if rest else f"{first_line} ({idx}/{total})")
    return out
