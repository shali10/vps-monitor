# Site E: czl.net 公开 API 模式 (1C2G 池监控)

**代表数据源**: [vps-monitor.czl.net](https://vps-monitor.czl.net) (Next.js + `/api/public/filter`)
**鉴权**: 无 (公开 API)
**数据**: JSON 分页列表, **12/page 强制** (忽略 pageSize 参数)
**部署**: LXC `204.152.198.206:53635`, commit `35ffe16`

## 适用场景

- 聚合站(如 czl.net / lowendstock 等)有公开 filter API
- 想监控某个聚合站里的"特定配置 + 价格"池
- 不直接对接商家,而是抓聚合站"已整理"的数据
- 避免为每个商家写 HTML / WHMCS 适配器

## fetch 函数要点 (site-e 实现)

```python
def fetch_site_e():
    # 1. 并发拉 100 页 (API 强制 12/page, 1054 条全量 ~88 页)
    # 2. 8 worker + ThreadPoolExecutor + as_completed
    # 3. 失败页 Round 2 retry (sleep 1s 错峰)
    # 4. 去重 (id 字段)
    # 5. 池规则过滤 (RAM + USD/年)
```

要点:
- **强制 12/page**: API 忽略 `pageSize` 参数, 全量需 88 页
- **并发限速敏感**: czl.net 限速敏感, 10 worker 触发 `Connection reset by peer`, 8 worker 稳
- **retry 兜底**: 单页失败不阻塞, Round 2 sleep 1s 错峰重试
- **id 去重**: 并发本身不重复, 但加保险(防止 API 返回重复)

## compare 函数要点

```python
def compare_site_e(state, items):
    # 三类事件:
    #   1. new_arrival: 新 id 出现
    #   2. restocked:   isAvailable false → true
    #   3. price_drop:  USD 数字真降 ≥1% (避免币种换算/格式化噪音)
```

要点:
- **价格比较用 USD 数字**: 不用字符串 `!=`, 避免 czl.net 改价格格式时误报降价
- **1% 容忍**: 容忍币种换算/舍入抖动(实际汇率波动 < 1%)
- **`_parse_usd_year_e()`** 统一币种(¥/￥/€/$)和周期(月/季/年)→ USD/年

## 池规则硬编码 (per user 2026-06-20)

```python
def _site_e_pool_match(ram_gb, usd_year):
    if 0.4 <= ram_gb <= 1.1 and 0 < usd_year <= 9:
        return "池1(廉价)"   # 1GB 玩具机, ≤$9/年
    if 2.0 <= ram_gb <= 16 and 10 <= usd_year <= 20:
        return "池2(主力)"   # 2-16GB 主力机, $10-20/年
    return None
```

要改池规则需改代码(env var 化是未来优化项)。
RAM 边界值 1.0GB 会被算成"池 1"(跟 1.1GB 一样符合"低规格"语义)。

## 排除规则

```python
def _site_e_is_vps(item):
    text = (item.get("title", "") + " " + item.get("disk", "")).lower()
    return not any(b in text for b in ["dedicated", "dedi", "独立服", "独立服务器"])
```

排除 RackNerd DEDI / Spartan DEDI / Netcup RS 等独立服务器(只监控 VPS/KVM)。

## 实际效果 (2026-06-20)

| 指标 | 值 |
|------|---|
| 全量抓取 | 1054 条 (88 页 × 12 条) |
| 池匹配 | **58 条** (池1: 2 + 池2: 56) |
| 当前有货 | 7 条 (首次跑 0 推送避免刷屏) |
| 抓取耗时 | **14s** (并发 vs 串行 26s 提速 46%) |
| 推送事件 | 🆕 新套餐 / 🔔 补货 / 💰 降价 |
| 部署 | LXC `/opt/vps-monitor/monitor.py`, systemd `vps-monitor.service` |

## 部署

LXC `204.152.198.206:53635`, PID 23284, systemd:
- `EnvironmentFile=/opt/vps-monitor/.env`
- 2 小时轮询 (`SITE_E_POLL_INTERVAL=7200`)
- `NOTIFY_ONLY_CHANGES=true` (避免重启刷屏)
- TG 推送: 2 个 chat_id (用户 TG + QQ bot 转发)

## 已知限制

- 池规则硬编码 → 改需改代码 (env var 化是 v3.3.0 优化项)
- 价格 USD 换算汇率硬编码 (1 USD = 0.139 CNY = 1.08 EUR)
- 依赖 czl.net 公开 API 持续可用 (down 则 site-e 静默, 不影响其他 site)
- LXC 488MB RAM 下 8 worker 完全够 (内存压力 < 10MB)

## 单测

`tests/test_site_e.py` 覆盖:
- `_parse_ram_gb_e`: 11 个测试 (基本/边界/异常)
- `_parse_usd_year_e`: 4 个测试 (USD/CNY/EUR/边界)
- `_site_e_pool_match`: 8 个测试 (池1/池2/不在池)
- USD 数字比较: 3 个测试 (真降/未变/抖动)
- `_site_e_is_vps`: 5 个测试 (普通 VPS/排除 DEDI)

跑测试: `python3 tests/test_site_e.py`

## 相关

- Commit: `35ffe16 feat(site-e): add czl.net public API adapter (1C2G pool rules)`
- Issue: 无
- PR: 无
