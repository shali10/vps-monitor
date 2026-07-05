# vps-monitor v4

Typed VPS stock/restock monitor for two production sources: 独角鲸云 and czl.net. v4 uses source adapters, normalized offer models, rule filtering, SQLite state, and a shared Telegram formatter.

## Production Layout

| Item | Value |
|---|---|
| Runtime host | LXC |
| Runtime path | `/opt/vps-monitor` |
| Config | `/opt/vps-monitor/config.json` |
| State | `/opt/vps-monitor/state/vpsmon.sqlite3` |
| Notification | Telegram HTML messages |
| Health bot | `/opt/health-bot/health_bot.py` |

## Timers

| Source | Timer | Interval | Command |
|---|---:|---:|---|
| 独角鲸云 | `vps-monitor-v4-dujiaojing.timer` | 3min | `python3 -m vpsmon.cli --config /opt/vps-monitor/config.json --source dujiaojing --send` |
| czl.net | `vps-monitor-v4-czl.timer` | 2h | `python3 -m vpsmon.cli --config /opt/vps-monitor/config.json --source czl --send` |

The services are oneshot jobs. A successful run ends as `inactive (dead)`, which is expected. Check `Result=success` and `ExecMainStatus=0` instead of expecting a long-running process.

## Local Development

```bash
python3 -m py_compile $(find vpsmon tests -name '*.py' | sort)
python3 -m pytest -q
python3 -m vpsmon.cli --config config.example.json --source dujiaojing --notify-first-run --dry-run
python3 -m vpsmon.cli --config config.example.json --source czl --notify-first-run --dry-run
```

## Deploy Notes

Do not ship `.env`, SQLite state, logs, caches, or legacy observer units. Production credentials stay in the LXC `/opt/vps-monitor/.env` and are injected by systemd `EnvironmentFile=`.

Before replacing LXC code, keep one rollback tarball:

```bash
tar czf /opt/vps-monitor-legacy-$(date +%Y%m%d%H%M%S).tar.gz -C /opt vps-monitor
```

## Message Format

All sources render through `vpsmon.notifiers.telegram.format_offer()`. Source-specific cleanup belongs in `vpsmon/sources/<source>.py`; shared truncation, stock labels, text links, route cleanup, and hashtags belong in the Telegram formatter.
