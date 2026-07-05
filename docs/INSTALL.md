# 安装部署

本文档给出从本地测试到 systemd 部署的完整流程。

## 环境要求

| 项 | 要求 |
|---|---|
| Python | 3.10+ |
| 系统 | Linux 推荐，macOS 可本地 dry-run |
| 依赖 | `requests` |
| 推送 | Telegram bot token 和 chat id |
| 持久化 | SQLite，本地文件即可 |

## 本地安装

```bash
git clone https://github.com/shali10/vps-monitor.git
cd vps-monitor
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
cp config.example.json config.local.json
```

编辑 `.env` 后加载环境变量：

```bash
set -a
. ./.env
set +a
```

## dry-run 验证

默认不发送 Telegram。建议先强制首轮输出，确认格式和筛选规则：

```bash
vpsmon-v4 --config config.local.json --source czl --notify-first-run --dry-run
vpsmon-v4 --config config.local.json --source dujiaojing --notify-first-run --dry-run
```

如果不想安装 console script，也可以直接跑模块：

```bash
python3 -m vpsmon.cli --config config.local.json --source czl --notify-first-run --dry-run
```

## 发送测试

```bash
vpsmon-v4 --config config.local.json --source czl --notify-first-run --summary --send
```

`--summary` 会发送摘要，适合第一次确认 Telegram 通道。

## 生产部署

推荐路径：`/opt/vps-monitor`。

```bash
sudo mkdir -p /opt/vps-monitor
sudo rsync -a --delete ./ /opt/vps-monitor/
cd /opt/vps-monitor
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
cp config.example.json config.json
```

编辑 `/opt/vps-monitor/.env` 和 `/opt/vps-monitor/config.json`。

安装 systemd unit：

```bash
sudo cp systemd/vps-monitor-v4-*.service systemd/vps-monitor-v4-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vps-monitor-v4-czl.timer vps-monitor-v4-dujiaojing.timer
```

查看状态：

```bash
systemctl list-timers 'vps-monitor-v4-*'
systemctl status vps-monitor-v4-czl.timer
systemctl show vps-monitor-v4-czl.service -p Result -p ExecMainStatus -p ActiveEnterTimestamp
```

## 升级

升级前保留一个回滚包：

```bash
sudo tar czf /opt/vps-monitor-backup-$(date +%Y%m%d%H%M%S).tar.gz -C /opt vps-monitor
```

更新代码：

```bash
cd /opt/vps-monitor
git pull --ff-only
. .venv/bin/activate
pip install -e .
python3 -m pytest -q
sudo systemctl daemon-reload
```

手动跑一轮：

```bash
set -a && . ./.env && set +a
vpsmon-v4 --config config.json --source czl --dry-run
```

## 卸载

```bash
sudo systemctl disable --now vps-monitor-v4-czl.timer vps-monitor-v4-dujiaojing.timer
sudo rm -f /etc/systemd/system/vps-monitor-v4-*.service /etc/systemd/system/vps-monitor-v4-*.timer
sudo systemctl daemon-reload
```

是否删除 `/opt/vps-monitor` 取决于你是否还要保留 SQLite 状态和配置。
