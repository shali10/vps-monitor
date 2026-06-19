# Site A: WHMCS Bearer Token 模式

**代表商家**:fuckip.me (dartnode)  
**鉴权**:`Authorization: Bearer ***  
**数据**:JSON 分页 + `sold_out` / `remaining` / `price_monthly` 字段

## fetch 函数要点

```python
def fetch_site_a():
    if not SITE_A_API_URL:
        log.info("site_a disabled")
        return [], 0
    items, page = [], 1
    while True:
        r = requests.get(
            SITE_A_API_URL,
            params={"limit": 200, "page": page},
            headers={"Authorization": f"Bearer {SITE_A_TOKEN}"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        batch = data.get("plans", data.get("data", []))
        items.extend(batch)
        if len(batch) < 200 or len(items) >= data.get("total", len(items)):
            break
        page += 1
    return items, len(items)
```

要点:
- **分页循环**:`limit=200` + `page=N`,直到 `len(batch) < limit` 或 `>= total`
- **Bearer 鉴权**:`headers={"Authorization": f"Bearer {TOKEN}"}`
- **超时短**:15s(避免主循环阻塞,Pitfall 17 教训)
- **raise_for_status**:让 401/403/500 抛出去,主循环 try/except 捕获 + log

## compare 函数要点

```python
def compare_site_a(state, items):
    new_arrivals, restocked = [], []
    old_plans = state.get("plans", {})
    new_plans = {}
    for p in items:
        pid = str(p["id"])
        new_plans[pid] = {"remaining": p.get("remaining", 0),
                          "sold_out": p.get("sold_out", False),
                          "price_monthly": p.get("price_monthly", 0)}
        if pid not in old_plans:
            new_arrivals.append(p)
        elif old_plans[pid].get("sold_out") and not p.get("sold_out"):
            restocked.append(p)  # sold_out true→false = 补货
    return new_arrivals, restocked, new_plans
```

要点:
- **触发条件**:`sold_out` true→false(不是 `remaining 0→N`,因为字段名因站而异)
- **新到货**:plan id 第一次出现(不在 old_plans)
- **价格过滤**:在 `monitor_site_a` 里用 `_site_a_match_rules(plan)` 三重过滤(关键词 + 价格 + 库存)

## 字段差异注意

| 字段 | fuckip.me | 常见 WHMCS |
|---|---|---|
| 库存数 | `remaining`(int) | `available` / `stock` / `qty` |
| 售价 | `price_monthly` | `price` / `price_monthly` |
| 已售罄 | `sold_out`(bool) | `sold_out` / `out_of_stock` |

**不要照搬常见名**,**先看 fetch 的真实返回**,或 grep 商家 API 文档。

## 调试

```bash
# 单独跑 Site A
cd /opt/vps-monitor
sudo systemctl stop vps-monitor
python3 monitor.py --once --site a

# 看具体命中
vpsmonctl check   # 看 site-a 命中 N 条
```

## 加新站(Bearer 模式)

如果新站也是 WHMCS Bearer:
1. 改 `.env`:`SITE_F_API_URL` / `SITE_F_TOKEN`
2. 复制 `fetch_site_a` / `compare_site_a` / `notify_site_a_restocked` / `monitor_site_a` 改名为 `*_site_f`
3. 改字段映射(根据新站 API 实际返回)
4. 加 state key + main loop 调度 + `--once --site f`
5. restart + 验证
