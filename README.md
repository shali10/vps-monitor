# vps-monitor

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Telegram](https://img.shields.io/badge/Telegram-26A5E4?logo=telegram&logoColor=white)](https://telegram.org/)

> VPS 商品库存 / 补货 / 降价 监控 → Telegram 推送
>
> 多站点 adapter 架构 · 事件驱动 diff · systemd 守护 · 0 第三方重依赖

---

## 为什么做这个

WHMCS 商家经常在深夜悄悄补货,刷一次 API 几十秒,人肉盯不现实。  
市面上的"监控脚本"要么只支持一个站,要么每个站写一套,改起来崩溃。  
**vps-monitor** 用统一的 `fetch → compare → notify` adapter 模式,
4 行配置 + 1 个新函数就能加新站。事件驱动,**只推变化**,不刷屏。

---

## ✨ 特点

- **多站点独立轮询** — 每个站独立的 URL / 鉴权 / 间隔,共用 1 个 Telegram bot
- **事件驱动 diff** — 只推"新到货"和"刚补货",老库存永不打扰
- **systemd 守护** — 自动重启 + journalctl 集中日志
- **三重过滤业务规则** — 关键词(优化/CN2/GIA...) + 价格区间(0-0.4 USD/月) + 库存 > 0
- **vpsmonctl 控制器** — 10+ 命令封装 `backup` / `restart` / `set-config` / `manual-push`
- **health-bot 哨兵** — 独立进程每 2h 心跳汇报当前监控状态
- **生产可观测性** — `FlushFileHandler` 解决 Python `logging.FileHandler` buffer 丢日志
- **故障隔离** — per-site try/except,一个站抛异常不阻塞其他站

---

## 🏗️ 架构

```
                ┌──────────────────────────────────────┐
                │           systemd                    │
                │    vps-monitor.service               │
                │   (Restart=always / EnvFile=.env)    │
                └─────────────────┬────────────────────┘
                                  │
                                  ▼
        ┌─────────────────────────────────────────────┐
        │           monitor.py (主循环)                │
        │   ┌─────────┐ ┌─────────┐ ┌─────────┐       │
        │   │ Site A  │ │ Site B  │ │ Site C  │ ...   │
        │   │ Bearer  │ │ Public  │ │ Resource│       │
        │   │ JSON    │ │ JSON    │ │ Template│       │
        │   └────┬────┘ └────┬────┘ └────┬────┘       │
        │        │           │           │             │
        │   ┌────▼───────────▼───────────▼────┐        │
        │   │   per-site try/except 隔离     │        │
        │   └────────────┬───────────────────┘        │
        └────────────────┼──────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │     state.json      │  ← baseline 对比
              └──────────┬──────────┘
                         │ diff
                         ▼
              ┌──────────────────────┐
              │  Telegram Bot API    │  ← 仅在有变化时推
              └──────────────────────┘
```

每个 Site 由 4 个函数组成:

| 函数 | 职责 |
|---|---|
| `fetch_site_X()` | HTTP 拉数据 → list of items |
| `compare_site_X(state, items)` | 与 baseline 对比 → (new, restocked, new_state) |
| `notify_site_X_restocked(items)` | 格式化 TG 消息 HTML |
| `monitor_site_X(state)` | 串联上面 3 个 + 写回 state + 触发推送 |

---

## 🚀 快速开始

### 1. 申请 Telegram Bot

1. 找 [@BotFather](https://t.me/BotFather) → `/newbot` → 拿 **bot token**
2. 给 bot 发任意消息,浏览器访问 `https://api.telegram.org/bot<TOKEN>/getUpdates` 拿 **chat_id**
3. 多接收人:在 `.env` 用英文逗号分隔多个 chat_id(单点失败不影响其他)

### 2. 准备 Bearer Token(如需鉴权)

WHMCS / 自建 API 通常用 `Authorization: Bearer *** 拿法:

1. 浏览器登录商家站
2. `F12` → `Network` → 点商品/列表
3. 找 XHR/fetch 请求 → `Request Headers` → `Authorization:`
4. 复制冒号后那串(通常是 `eyJ...` JWT,带不带 `Bearer ` 前缀都行)

### 3. 一键装机

```bash
git clone https://github.com/<your-user>/vps-monitor.git
cd vps-monitor
sudo bash scripts/install.sh
```

### 4. 手动安装

```bash
sudo mkdir -p /opt/vps-monitor
sudo cp -r ./* /opt/vps-monitor/
cd /opt/vps-monitor
pip3 install -r requirements.txt
sudo cp .env.example .env
sudo chmod 600 .env
sudo $EDITOR .env       # 填 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID / SITE_X_TOKEN

sudo cp vps-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vps-monitor

# 验证
sudo systemctl status vps-monitor
tail -f /opt/vps-monitor/monitor.log
```

---

## 📦 监控的 4 种 Source 模式

| 模式 | 代表商家 | 鉴权 | 解析 | 适配难度 |
|---|---|---|---|---|
| **WHMCS Bearer** | fuckip.me (dartnode) | `Authorization: Bearer *** | JSON 分页 + Bearer | ⭐ 直接用 Site A |
| **公开 WHMCS** | 多数 WHMCS 商家 | 无 | JSON 分页 | ⭐ 直接用 Site B |
| **资源模板** | incudal.di0.uk | `Authorization: Bearer *** | package 自身当 1 个伪 plan | ⭐⭐ 参考 Site C |
| **HTML 解析** | dedirock.com | 无 | `requests + 正则` | ⭐⭐⭐ 参考 Site D |

详见 [`docs/sites/`](docs/sites/)。

---

## ➕ 加新站点(5 步 recipe)

例如想加 Site E(假设是新的 WHMCS Bearer 站):

1. **顶部加常量**(复用 Site A 模板):
   ```python
   SITE_E_API_URL = "https://newsite.com/api/v1/plans"
   SITE_E_TOKEN = _env_str("SITE_E_TOKEN", "")
   SITE_E_POLL_INTERVAL = 60
   SITE_E_DEPLOY_URL = "https://newsite.com/deploy?plan_id={plan_id}"
   ```

2. **复制 Site A 改 4 个函数**:`fetch_site_e` / `compare_site_e` / `notify_site_e_restocked` / `monitor_site_e`

3. **`load_state()` 加 key**:
   ```python
   return {
       "site_a": {...}, "site_b": {...}, "site_c": {...}, "site_d": {...},
       "site_e": {"plans": {}, "first_run": True},   # ← 加这行
       "last_poll": 0,
   }
   ```

4. **`main()` 加轮询**:
   ```python
   last_e = 0
   if now - last_e >= SITE_E_POLL_INTERVAL:
       last_e = now
       monitor_site_e(state["site_e"])
   ```

5. **`--once` 也加**:
   ```python
   if args.site in ("e", "all"):
       n_new, n_restock = monitor_site_e(state["site_e"])
       print(f"site-e: {n_new} new, {n_restock} restocked")
   ```

完成。详见 [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)。

---

## 🛠️ vpsmonctl 控制器

| 你想... | 命令 |
|---|---|
| 看监控状态 | `vpsmonctl status` |
| 看最近 100 行日志 | `vpsmonctl logs 100` |
| 重启监控 | `vpsmonctl restart` |
| 加 TG 接收人 | `vpsmonctl add-chat 123456789` |
| 改随便机价格阈值 | `vpsmonctl set-cheap-max 0.2` |
| 改优化机价格阈值 | `vpsmonctl set-optimized-max 0.5` |
| 改轮询间隔 | `vpsmonctl set-interval 30` |
| 手动推一次当前库存 | `vpsmonctl manual-push` |
| 查当前命中数量 | `vpsmonctl check` |
| 只推变化(防刷屏) | `vpsmonctl only-changes on` |

完整命令 + 用法见 `vpsmonctl --help`。

---

## 🔍 调试 / 重置

### 跑一次(不启动 service)

```bash
cd /opt/vps-monitor
sudo systemctl stop vps-monitor    # 先停,避免双跑
python3 monitor.py --once          # 跑全部
python3 monitor.py --once --site a # 只跑 Site A
```

首次跑(`first_run=true`)会**只记录 baseline 不推送**,数字全是 0,这是预期。删 `state.json` 就能重置。

### 看日志

```bash
tail -f /opt/vps-monitor/monitor.log
journalctl -u vps-monitor -f
grep -E '\[ERROR\]|\[WARNING\]' /opt/vps-monitor/monitor.log | tail -20
```

### 重置

```bash
sudo systemctl stop vps-monitor
sudo rm /opt/vps-monitor/state.json   # ← 删了会重新 baseline,首次跑不推
sudo systemctl start vps-monitor
```

---

## ⚠️ 已知 Pitfalls(必读)

写了 26 个实战 pitfall,从 systemd EnvironmentFile 空值行到 Token 失效排查,都是 0.5-2 小时踩出来的坑。  
[**→ 完整 PITFALLS.md**](docs/PITFALLS.md)

---

## 📁 目录结构

```
vps-monitor/
├── monitor.py              # 主 daemon (~50KB / 1233 行)
├── vpsmonctl               # 控制器 (10+ 命令)
├── vps-monitor.service     # systemd unit
├── requirements.txt        # requests (唯一第三方依赖)
├── .env.example            # 环境变量模板(脱敏)
├── .gitignore              # .env / state.json / *.bak 永不进 git
├── LICENSE                 # MIT
├── CHANGELOG.md
├── README.md
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── INSTALL.md
│   ├── PITFALLS.md
│   ├── CONTRIBUTING.md
│   └── sites/
│       ├── site-a-whmcs.md
│       ├── site-b-public.md
│       ├── site-c-resource-template.md
│       └── site-d-html-scrape.md
│
├── scripts/
│   ├── install.sh
│   ├── inventory_snapshot.py
│   └── health_bot.py
│
├── tests/
│   ├── test_monitor_smoke.py
│   └── test_state_diff.py
│
└── examples/
    └── state.example.json
```

---

## 🤝 Contributing

欢迎 PR!详见 [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)。

---

## 📄 License

MIT — 见 [`LICENSE`](LICENSE)。

---

## 🙏 致谢

- Telegram Bot API 简单稳定
- 所有用 systemd + Python 标准库 + requests 的开源项目
- 凌晨 3 点还在补货的商家们(我们都在盯着你呢 👀)
