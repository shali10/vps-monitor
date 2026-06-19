# Site B: 公开 WHMCS API 模式

**代表商家**:多数 WHMCS 标准商家  
**鉴权**:无(公开 API)  
**数据**:JSON 分页 + 标准 WHMCS 字段(`name` / `price` / `stock` / `status`)

## 与 Site A 的区别

| 维度 | Site A (Bearer) | Site B (Public) |
|---|---|---|
| 鉴权 | `Authorization: Bearer *** | 无 |
| 字段 | `sold_out` / `remaining` / `price_monthly` | `stock` / `price` / `status` |
| 分页 | `?limit=200&page=N` | `?per_page=50&page=N`(WHMCS 标准) |
| 触发 | `sold_out` true→false | `stock` 0→N |

## fetch 函数要点

```python
def fetch_site_b():
    if not SITE_B_API_URL:
        log.info("site_b disabled")
        return [], 0
    items, page = [], 1
    while True:
        r = requests.get(
            SITE_B_API_URL,
            params={"per_page": 50, "page": page},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        # WHMCS 标准: list 直接在根
        batch = data if isinstance(data, list) else data.get("data", [])
        items.extend(batch)
        # 无 total 字段 → 用 has_next 判断
        if len(batch) < 50:
            break
        page += 1
    return items, len(items)
```

要点:
- **公开 API 无鉴权 header**(直接 GET)
- **WHMCS 分页**:`per_page=50`(WHMCS 默认)+ `page=N`(从 1 起)
- **无 total 字段** → 用 `len(batch) < per_page` 判断终止
- **超时短**:15s

## compare 函数要点

```python
def compare_site_b(state, items):
    new_arrivals, restocked = [], []
    old_plans = state.get("plans", {})
    new_plans = {}
    for p in items:
        pid = str(p["id"])
        # ⚠️ Site B 字段: stock 而非 remaining, price 而非 price_monthly
        new_plans[pid] = {
            "stock": p.get("stock", 0),
            "price": p.get("price", 0),
            "status": p.get("status", "active"),
        }
        if pid not in old_plans:
            new_arrivals.append(p)
        elif old_plans[pid].get("stock", 0) == 0 and p.get("stock", 0) > 0:
            restocked.append(p)  # stock 0→N = 补货
    return new_arrivals, restocked, new_plans
```

要点:
- **触发条件**:`stock` 0→N(不是 `status` 翻转,跟 Site A 不同)
- **新到货**:plan id 第一次出现
- **公开 API 字段一致性高**:标准 WHMCS 商家字段基本一致

## 业务规则三重过滤

```python
def _site_b_match_rules(plan):
    # 1. 价格过滤
    if not (0 < plan.get("price", 0) <= 0.4):
        return False
    # 2. 关键词过滤(优化 / CN2 / GIA 等)
    name = plan.get("name", "") + plan.get("description", "")
    keywords = ["优化", "CN2", "GIA", "CMI", "9929", "精品", "三网", "BGP"]
    if not any(k in name for k in keywords):
        return False
    # 3. 库存 > 0
    if plan.get("stock", 0) <= 0:
        return False
    return True
```

## 调试

```bash
# 单独跑 Site B
cd /opt/vps-monitor
sudo systemctl stop vps-monitor
python3 monitor.py --once --site b
```

## 加新站(公开 WHMCS)

如果新站也是公开 WHMCS API:
1. 改 `.env`:`SITE_X_API_URL`(不用 TOKEN)
2. 复制 `fetch_site_b` / `compare_site_b` / `notify_site_b_restocked` / `monitor_site_b` 改名为 `*_site_x`
3. 字段名一般不变(`id` / `name` / `price` / `stock` 都标准)
4. 加 state key + main loop 调度 + `--once --site x`
5. restart + 验证

如果新站不是标准 WHMCS(树形 / 自定义字段),参考 `site-d-html-scrape.md` 重新设计。
