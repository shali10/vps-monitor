from __future__ import annotations

import argparse
from pathlib import Path

from vpsmon.config import load_config
from vpsmon.engine.diff import diff_offers
from vpsmon.notifiers.telegram import render_events, render_summary, send_telegram_messages
from vpsmon.rules.filtering import filter_offers, pool_name
from vpsmon.sources.czl import CzlSource
from vpsmon.sources.dujiaojing import DujiaojingSource
from vpsmon.storage.sqlite import StateStore


def _build_source(name: str, config: dict):
    if name == "czl":
        return CzlSource(config)
    if name == "dujiaojing":
        return DujiaojingSource(config)
    raise SystemExit(f"unknown source: {name}")


def run_once(
    config_path: str,
    source_name: str,
    dry_run: bool,
    first_run_silent: bool,
    send: bool = False,
    summary: bool = False,
    max_send_messages: int = 20,
    limit_events: int | None = None,
    sort_events: str = "source",
) -> int:
    config = load_config(config_path)
    source_cfg = config.get("sources", {}).get(source_name)
    if not source_cfg or not source_cfg.get("enabled", True):
        raise SystemExit(f"source disabled or missing: {source_name}")

    source = _build_source(source_name, source_cfg)
    policy = config.get("notify_policy", {}).get(source_name, config.get("notify_policy", {}).get("default", {}))
    if limit_events is None and policy.get("limit_events") is not None:
        limit_events = int(policy["limit_events"])
    if sort_events == "source" and policy.get("sort_events"):
        sort_events = str(policy["sort_events"])
    offers_raw = source.fetch()
    source_rules = config.get("rules", {}).get(source_name, {})
    global_rules = config.get("rules", {}).get("global", {})
    offers = filter_offers(offers_raw, source_rules, global_rules)

    state_path = Path(config_path).parent / config.get("state_db", "./state/vpsmon.sqlite3")
    store = StateStore(state_path)
    try:
        events = diff_offers(store, offers, first_run_silent=first_run_silent, commit=send)
        if send:
            store.record_events(events)
    finally:
        store.close()

    print(f"source={source_name} raw={len(offers_raw)} filtered={len(offers)} events={len(events)}")
    renderable_events = [event for event in events if event.offer.available]
    skipped_unavailable = len(events) - len(renderable_events)
    if skipped_unavailable:
        print(f"skipped_unavailable={skipped_unavailable}")
    if sort_events == "price":
        renderable_events.sort(key=lambda event: event.offer.price.usd_year if event.offer.price else 10**9)
    elif sort_events == "pool_price":
        renderable_events.sort(
            key=lambda event: (
                0 if pool_name(event.offer, source_rules.get("pools", [])) else 1,
                event.offer.price.usd_year if event.offer.price else 10**9,
            )
        )
    elif sort_events == "stock":
        renderable_events.sort(key=lambda event: event.offer.stock if event.offer.stock is not None else 10**9)
    if limit_events is not None:
        renderable_events = renderable_events[:limit_events]
        print(f"render_events={len(renderable_events)} limit={limit_events} sort={sort_events}")
    messages = render_summary(renderable_events) if summary else render_events(renderable_events, {source_name: source_rules})
    if send:
        if len(messages) > max_send_messages:
            raise SystemExit(
                f"refusing to send {len(messages)} messages; use --summary or raise --max-send-messages"
            )
        sent = send_telegram_messages(messages, config.get("telegram", {}))
        print(f"telegram_sent={sent} messages={len(messages)}")
    else:
        for i, message in enumerate(messages, 1):
            print(f"\n--- message {i}/{len(messages)} chars={len(message)} ---")
            print(message[:4000])
    return len(events)


def main() -> None:
    parser = argparse.ArgumentParser(prog="vpsmon-v4")
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument("--source", default="czl")
    parser.add_argument("--dry-run", action="store_true", help="kept for compatibility; default mode does not send")
    parser.add_argument("--send", action="store_true", help="send Telegram messages; default is dry-run preview")
    parser.add_argument("--summary", action="store_true", help="render a compact summary instead of full offer blocks")
    parser.add_argument("--limit-events", type=int, default=None, help="only render first N events after sorting")
    parser.add_argument("--sort-events", choices=["source", "price", "pool_price", "stock"], default="source")
    parser.add_argument("--max-send-messages", type=int, default=20, help="safety cap for --send")
    parser.add_argument("--notify-first-run", action="store_true", help="emit events even if source has no state yet")
    args = parser.parse_args()
    run_once(
        args.config,
        args.source,
        args.dry_run,
        first_run_silent=not args.notify_first_run,
        send=args.send,
        summary=args.summary,
        max_send_messages=args.max_send_messages,
        limit_events=args.limit_events,
        sort_events=args.sort_events,
    )


if __name__ == "__main__":
    main()
