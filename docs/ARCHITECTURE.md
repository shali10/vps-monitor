# 架构详解

## 进程模型

```
systemd (PID 1)
└── vps-monitor.service
    └── python3 /opt/vps-monitor/monitor.py  (主 daemon, single process)
```

主 daemon 是个 `while True` 主循环,每 `MAIN_LOOP_INTERVAL` 秒醒一次,检查每个站是否到了轮询时间,到了就调对应的 `monitor_site_X(state)`。

不是多进程 / 多线程 — Python `requests` 同步调用,简单可控。

## 主循环伪代码

```python
while running:
    now = int(time.time())
    if now - last_a >= SITE_A_POLL_INTERVAL:
        last_a = now
        try:
            monitor_site_a(state["site_a"])
        except Exception as e:
            log.exception("site-a poll failed: %s", e)  # 不阻塞 site_b/c/d

    if now - last_b >= SITE_B_POLL_INTERVAL:
        # ...
    # ...
    for _ in range(MAIN_LOOP_INTERVAL):
        time.sleep(1)
```

**关键设计**:每个 site 独立 try/except(Pitfall 17 教训)。一个站 401/timeout/JSON 解析错,**不影响其他站继续轮询**。

## Adapter 4 函数职责

| 函数 | 输入 | 输出 | 职责 |
|---|---|---|---|
| `fetch_site_X()` | 无 | `(items, total)` | HTTP 拉 + 分页 + 鉴权 + 错误处理 |
| `compare_site_X(state, items)` | (state, items) | `(new, restocked, new_state)` | 与 baseline 对比,识别事件 |
| `notify_site_X_restocked(items)` | items | HTML str | 格式化 TG 消息(emoji + 链接 + 规格) |
| `monitor_site_X(state)` | state | `(n_new, n_restock)` | 串联: fetch → compare → 写 state → 推 TG |

`state.json` 是 baseline + first_run flag 的持久化层。每次 monitor_site_X 跑完会**原子写回**(写 tmp + rename)。

## 事件触发逻辑

| 状态变化 | 触发事件 |
|---|---|
| 套餐 id 第一次出现 | 🆕 新到货(`new_arrival`) |
| `soldOut` 从 `true` → `false` | 🔔 补货(`restocked`) |
| `remaining` 从 0 → N | 🔔 补货 |
| 价格下降 | 💰 降价(可选,Site C 有) |
| 其他字段变化 | ❌ 不推 |

**不推**老库存(避免刷屏)、**不推**售罄(只推"刚补货")、**不推**纯字段变化(只在状态翻转时推)。

## 日志架构

`monitor.py` 用自定义 `FlushFileHandler`(Pitfall 13 教训):

```python
class _FlushFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()  # ← 每条 log 立即 flush,不 buffer
```

效果:monitor.log mtime 秒级更新,而不是 systemd 重启才 flush。

双路输出:
- `monitor.log`(本地文件,可 tail)
- `journalctl -u vps-monitor`(systemd journal,远程看)

## systemd 集成

```ini
[Service]
Type=simple
WorkingDirectory=/opt/vps-monitor
ExecStart=/usr/bin/python3 /opt/vps-monitor/monitor.py
Restart=always
RestartSec=10
EnvironmentFile=/opt/vps-monitor/.env
```

关键点:
- `Type=simple` + 进程常驻(不是 oneshot)
- `Restart=always` + `RestartSec=10`(崩了 10s 后自动重启)
- `EnvironmentFile=` 注入 `.env` 到 `os.environ`(monitor.py 用 `os.environ.get(...)` 读)
- **`EnvironmentFile=` 空值行会注入空字符串**!(Pitfall 1 教训)→ `.env` 里不用的 KEY **删整行**,不要留 `KEY=`

## vpsmonctl 设计

封装 10+ 高频操作,避免直接 `vim monitor.py` / `systemctl restart`:

| 类别 | 命令示例 |
|---|---|
| 状态 | `status` / `logs N` / `check` |
| 生命周期 | `restart` / `backup` / `restore` |
| 配置热改 | `set-cheap-max` / `set-optimized-max` / `set-interval` / `set-keywords` |
| 推送 | `add-chat` / `list-chats` / `manual-push` / `test-push` / `only-changes on/off` |

每个 setter 命令会自动:`备份 .env → 改 KEY → restart service → 验证 active + 无 error`。
