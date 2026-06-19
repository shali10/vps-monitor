# Site D: HTML 解析模式

**代表商家**:dedirock.com(Promo 页)  
**鉴权**:无(公开 HTML)  
**数据**:HTML 内嵌 JSON 或正则提取

## 适用场景

- 商家没有公开 API,只有 Promo 页 / 商品列表页
- 页面用 JavaScript 渲染但 Server-side 有隐藏 JSON(`__NEXT_DATA__` / `window.__INITIAL_STATE__`)
- 或纯 HTML,价格 / 库存用 class / data-attr 标记

## fetch 函数要点(以 dedirock 为例)

```python
import re
import requests
import json

def fetch_site_d():
    if not SITE_D_URL:
        log.info("site_d disabled")
        return [], 0
    r = requests.get(SITE_D_URL, timeout=15, headers={
        "User-Agent": "Mozilla/5.0 ..."
    })
    r.raise_for_status()
    html = r.text
    # 方案 1: 提取页面内嵌 JSON
    m = re.search(r"window.__INITIAL_STATE__\s*=\s*({.*?});", html, re.DOTALL)
    if m:
        data = json.loads(m.group(1))
        products = data.get("products", [])
        return products, len(products)
    # 方案 2: 正则提取(回退)
    products = re.findall(r"data-product-id=.(\d+).*?\$(\d+\.\d+)", html)
    return [{"id": pid, "price": float(price)} for pid, price in products], len(products)
```

要点:
- **User-Agent**:避免被反爬(部分站屏蔽 requests 默认 UA)
- **超时短**:HTML 站可能慢,15s 避免阻塞
- **优先 JSON 提取**(藏在 HTML 里的 `__NEXT_DATA__` / `__INITIAL_STATE__`),回退正则
- **BeautifulSoup 也行**:`from bs4 import BeautifulSoup; soup = BeautifulSoup(html, 'html.parser')`

## CF 反爬注意

如果商家用 Cloudflare Turnstile / JS challenge:
- `requests` 直接拉 → 403 / 200 HTML 壳
- 解法 1:`curl_cffi`(伪装 TLS 指纹)
- 解法 2:Playwright / headless Chrome
- 解法 3:商家如有公开 API,直接用 API 不用 HTML 解析

dedirock 当前没 CF,`requests` 可直拉。

## compare 函数要点

HTML 站的字段名因站而异,dedirock 用 `status` + `campaign` + `price`:

```python
def compare_site_d(state, items):
    restock, soldout, campaign_change = [], [], []
    old_products = state.get("products", {})
    new_products = {}
    for p in items:
        pid = str(p["id"])
        new_products[pid] = {"status": p.get("status"),
                             "campaign": p.get("campaign"),
                             "price": p.get("price")}
        old = old_products.get(pid, {})
        # 补货:有 → 无 → 有
        if old.get("status") == "soldout" and p.get("status") == "available":
            restock.append(p)
        # 售罄:有 → 无
        elif old.get("status") == "available" and p.get("status") == "soldout":
            soldout.append(p)
        # Campaign 变化:BlackFriday → None
        elif old.get("campaign") != p.get("campaign"):
            campaign_change.append(p)
    return restock, soldout, campaign_change, new_products
```

3 种事件:**补货 + 售罄 + Campaign 变化**(比 JSON 站更丰富)。

## 验证

```bash
# 看 HTML 真实内容
curl -s https://dedirock.com/promo | head -c 2000

# 看内嵌 JSON
curl -s https://dedirock.com/promo | grep -o "window.__INITIAL_STATE__.*" | head -c 500
```

## 加新站(HTML 解析)

1. `curl` 拉一次,看 HTML 结构
2. 找价格 / 库存 / 状态字段的 class / data-attr / JSON 嵌入
3. 写 `fetch_site_Y` 用正则或 BeautifulSoup 提取
4. 写 `compare_site_Y` 根据状态字段定义事件(补货 / 售罄 / Campaign)
5. **CF 商家先确认能否绕过**,不能就考虑用商家公开 API(如果有)或换站
