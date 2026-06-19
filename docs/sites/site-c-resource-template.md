# Site C: 资源模板 API 模式

**代表商家**:incudal.di0.uk  
**鉴权**:`Authorization: Bearer ***  
**数据**:顶层 `packages` 数组,每个 package **无 plans 子数组**(资源模板)

## 特殊性

incudal 类商家的 API 返回结构:
```json
{
  "packages": [
    {
      "id": 1,
      "name": "探針機",
      "soldOut": true,
      "cpu_max": 10000,
      "memory_max": 809600,
      "disk_max": 102400,
      "sourceType": "official",
      "network_mode": "ipv6_only",
      "instance_type": "container"
    }
  ],
  "total": 3
}
```

**没有 `plans` 字段**,没有 `price` 字段(只有资源规格)。

## fetch 函数要点

```python
def fetch_site_c():
    if not SITE_C_API_URL:
        log.info("site_c disabled")
        return [], 0
    r = requests.get(
        SITE_C_API_URL,
        headers={"Authorization": f"Bearer {SITE_C_TOKEN}"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    pkgs = data.get("packages", [])
    return pkgs, len(pkgs)
```

要点:
- **顶层 packages**:不是 `data["packages"]` 嵌套
- **无分页**:incudal API 一次返回全部 3 个

## compare 函数要点(关键:fallback 把 package 当 1 个伪 plan)

```python
def _site_c_plan_list(pkg):
    # incudal package 自身就是 1 个资源模板(无 plans 子数组)
    for key in ("plans", "packagePlans", "package_plans", "items", "variants"):
        value = pkg.get(key)
        if isinstance(value, list):
            return value
    # fallback: package 自身当 1 个 plan
    if isinstance(pkg, dict) and (pkg.get("id") is not None or pkg.get("name")):
        return [pkg]
    return []
```

如果不加这个 fallback,incudal 会"polled 0 packages"(找不到 plans → signature 空)。

## ⚠️ `?source=` 参数陷阱

| `?source=` | packages | 备注 |
|---|---|---|
| (none) | 3 | 默认全 3 个 |
| `official` | 1 | 只有探針機 |
| `community` | 3 | 探針機 + 洛杉矶小鸡鸡 + 还有4天 |
| `shared` | 3 | 同 community |
| `all` | 3 | 同 community |

**`?source=official` 只返回 1 个,漏 2 个真商品!**  
推荐:`SITE_C_API_URL=https://incudal.di0.uk/api/packages`(无 source)或 `?source=community`。

## 价格字段缺失

incudal 公开 API **没有 price 字段**。推送显示"价格 0.00 USD"但**不假** —— API 真没返回。

如果业务规则需要价格过滤,在 `_site_c_match_rules` 里:
```python
def _site_c_match_rules(pkg):
    # 因为没 price,只能用关键词 + 资源规格
    if pkg.get("cpu_max", 0) < 100:
        return False
    return True
```

## 调试

```bash
# 看 incudal 全貌
python3 -c "
import requests
headers = {\"Authorization\": \"Bearer YOUR_TOKEN\"}
for src in ['', 'official', 'community', 'shared', 'all']:
    url = f'https://incudal.di0.uk/api/packages' + (f'?source={src}' if src else '')
    r = requests.get(url, headers=headers)
    d = r.json()
    print(f'[source={src or chr(34)+\"NONE\"+chr(34)}] packages=' + str(len(d.get('packages', []))))
"
# 输出: source=NONE packages=3, source=official packages=1, ...
```
