from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typing import Any

import requests

from vpsmon.config import load_config
from vpsmon.notifiers.telegram import send_telegram_messages, split_blocks

WATCH_FIELDS = ("domain", "siteName", "merchantName", "minPackage", "tags")


def _load_items(url: str) -> list[dict[str, Any]]:
    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    data = resp.json()
    return [x for x in data if isinstance(x, dict) and x.get("key") and x.get("key") != "global"]


def _snapshot(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        out[str(item["key"])] = {field: item.get(field) for field in WATCH_FIELDS}
    return out


def _fmt_item(key: str, item: dict[str, Any]) -> str:
    tags = item.get("tags") or []
    tag_text = " / ".join(str(x) for x in tags) if isinstance(tags, list) else str(tags or "")
    lines = [
        f"📦 <b>{item.get('merchantName') or item.get('siteName') or key}</b>",
        f"   🌐 {item.get('domain') or '-'}",
        f"   💰 {item.get('minPackage') or '-'}",
    ]
    if tag_text:
        lines.append(f"   🏷️ {tag_text}")
    return "\n".join(lines)


def _render_changes(old: dict[str, dict[str, Any]], new: dict[str, dict[str, Any]]) -> list[str]:
    blocks: list[str] = []
    old_keys = set(old)
    new_keys = set(new)

    for key in sorted(new_keys - old_keys):
        blocks.append("🆕 新增商家\n" + _fmt_item(key, new[key]))

    for key in sorted(old_keys - new_keys):
        blocks.append("🗑️ 移除商家\n" + _fmt_item(key, old[key]))

    for key in sorted(old_keys & new_keys):
        changes = []
        for field in WATCH_FIELDS:
            if old[key].get(field) != new[key].get(field):
                changes.append((field, old[key].get(field), new[key].get(field)))
        if not changes:
            continue
        head = f"✏️ <b>{new[key].get('merchantName') or new[key].get('siteName') or key}</b> 信息变化"
        lines = [head]
        for field, before, after in changes:
            if isinstance(before, list):
                before = " / ".join(map(str, before))
            if isinstance(after, list):
                after = " / ".join(map(str, after))
            lines.append(f"   • {field}: {before or '-'} → {after or '-'}")
        if new[key].get("domain"):
            lines.append(f"   🌐 {new[key]['domain']}")
        blocks.append("\n".join(lines))

    if not blocks:
        return []
    header = f"📣 PoorVPS 导航变更 · {len(blocks)} 项"
    return split_blocks(header, blocks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/opt/vps-monitor/config.json")
    parser.add_argument("--url", default="https://poorvps.com/nav-config.json")
    parser.add_argument("--state", default="/opt/vps-monitor/state/poorvps_nav.json")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--notify-first-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    state_path = Path(args.state)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    items = _load_items(args.url)
    snap = _snapshot(items)

    if state_path.exists():
        old = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        old = {}

    messages = _render_changes(old, snap) if old or args.notify_first_run else []
    state_path.write_text(json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"poorvps items={len(snap)} changes={len(messages)}")
    if args.send:
        sent = send_telegram_messages(messages, cfg.get("telegram", {})) if messages else 0
        print(f"telegram_sent={sent} messages={len(messages)}")
    else:
        for i, msg in enumerate(messages, 1):
            print(f"\n--- message {i}/{len(messages)} chars={len(msg)} ---")
            print(msg[:4000])


if __name__ == "__main__":
    main()
