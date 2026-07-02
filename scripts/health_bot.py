#!/usr/bin/env python3
"""哨兵 bot —— 每 2h 心跳汇报当前监控商家状态。

设计:
- 独立进程(cron 或 systemd timer 触发)
- 读 /opt/vps-monitor/.env 拿 TG 配置
- 读 /opt/vps-monitor/state.json 推断每个商家状态
- 推送: 当前监控商家列表 + 各站 last_poll 时间 + 24h 推送计数
- 不依赖 monitor.py,可独立部署 / 独立版本

用法:
    python3 health_bot.py                # 立即推一次
    # 或 cron: 0 */2 * * * /usr/bin/python3 /opt/health-bot/health_bot.py
"""

import json
import sys
import time
from pathlib import Path

import requests

ENV_FILE = Path("/opt/vps-monitor/.env")
STATE_FILE = Path("/opt/vps-monitor/state.json")
LOG_FILE = Path("/opt/health-bot/health_bot.log")

# 监控商家列表(hardcode,详见 PITFALLS.md Pitfall 7)
# 状态: active = 真监控中 / preparing = 占位待接入 / disabled = 已废弃
MONITORED_SHOPS = [
    {"emoji": "🔥", "name": "DediRock",        "status": "active",
     "url": "https://dedirock.com"},
    {"emoji": "🐳", "name": "独角鲸",          "status": "preparing",
     "url": "https://example.com"},
    {"emoji": "💎", "name": "Incudal",         "status": "active",
     "url": "https://incudal.di0.uk/dashboard"},
]


def load_env():
    """读 .env(不进 systemd 上下文,手动 parse)。"""
    env = {}
    if not ENV_FILE.exists():
        sys.exit(f"❌ .env 不存在: {ENV_FILE}")
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def push_tg(env, text):
    """推 TG,多个 chat_id 独立 try。"""
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_ids = env.get("TELEGRAM_CHAT_IDS", env.get("TELEGRAM_CHAT_ID", "")).split(",")
    chat_ids = [c.strip() for c in chat_ids if c.strip()]
    if not token or not chat_ids:
        print(f"❌ TG 配置缺失: token={bool(token)} chats={chat_ids}")
        return
    for cid in chat_ids:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": cid, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": True},
                timeout=15,
            )
            r.raise_for_status()
            print(f"  ✅ pushed to {cid}")
        except Exception as e:
            print(f"  ❌ push to {cid} failed: {e}")


def main():
    env = load_env()
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except Exception as e:
            print(f"⚠️  state.json read failed: {e}")

    now_ts = int(time.time())
    lines = ["<b>📡 VPS 监控心跳</b>", ""]
    for shop in MONITORED_SHOPS:
        e, name, status, url = shop["emoji"], shop["name"], shop["status"], shop["url"]
        if status == "active":
            site_state = state.get("site_a", {})  # 简化:只查 Site A
            last_poll = state.get("last_poll", 0)
            ago = (now_ts - last_poll) // 60 if last_poll else "?"
            lines.append(f"{e} <b>{name}</b> · active · 上次轮询 {ago} 分钟前")
        elif status == "preparing":
            lines.append(f"{e} <b>{name}</b> · 筹备中")
        else:
            lines.append(f"{e} <b>{name}</b> · disabled")
    lines.append("")
    lines.append(f"🕐 检查时间: {time.strftime("%Y-%m-%d %H:%M:%S")}")

    push_tg(env, "\n".join(lines))


if __name__ == "__main__":
    main()
