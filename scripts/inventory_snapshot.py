#!/usr/bin/env python3
"""inventory_snapshot.py - 3+ 家库存快照推送(测试用,临时脚本)

用法: /usr/bin/python3 /tmp/inventory_snapshot.py [--dry]

设计要点(2026-06-19 实战,2026-06-19 补 Pitfall 21 修正):
- 读 .env 拿配置(不是 os.environ, ad-hoc 不在 systemd 上下文)
- site_a URL 给显式默认值(env 里没设也能跑)
- incudal API 顶层 packages(不是 data.packages 嵌套)
- 单 chat_id 失败 continue,不阻塞其他
- --dry 模式只 print 不发
- 永远 atomic state / try/except 每个 site 单独隔离
- ⚠️ Pitfall 21: fuckip.me 用 "remaining" 字段(不是 available/stock)
- ⚠️ Pitfall 21: fuckip.me 用 "price_monthly" 字段(不是 price)
- ⚠️ Pitfall 21: incudal `?source=official` 只看 1 个 package, 要看全部用 no source 或 source=community

适用: 任何 vps-monitor 用户的"推一下当前 3 家库存"需求
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

# ============ 配置 ============
ENV_FILE = Path("/opt/vps-monitor/.env")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def load_env() -> dict:
    """手动读 .env(ad-hoc 脚本不在 systemd 上下文,os.environ 是空)"""
    env = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


# ============ 1) DediRock (HTML 解析) ============
DEDI_PRODUCTS = [
    {"code": "LA", "url": "https://billing.dedirock.com/index.php/store/promo-vps-los-angeles",
     "name": "Promo VPS Saver LA", "price": "9.88"},
    {"code": "NY", "url": "https://billing.dedirock.com/index.php/store/promo-vp",
     "name": "Promo VPS Saver NY", "price": "8.88"},
]


def fetch_dedi():
    out = []
    for p in DEDI_PRODUCTS:
        try:
            r = requests.get(p["url"], headers={"User-Agent": UA, "Accept": "text/html"}, timeout=15)
            if r.status_code != 200:
                out.append({**p, "in_stock": False, "campaign": f"http_{r.status_code}", "size": 0})
                continue
            html, size = r.text, len(r.content)
            in_stock = ("Promo VPS Saver" in html and f"{p['price']} USD" in html and "Order Now" in html)
            m = re.search(r'id="product\d+-name">([^<]+)', html)
            campaign = "no_product"
            if m:
                name = m.group(1)
                if "BF" in name: campaign = "BF"
                elif "LET" in name: campaign = "LET"
                else: campaign = "regular"
            out.append({**p, "in_stock": in_stock, "campaign": campaign, "size": size})
        except Exception as e:
            out.append({**p, "in_stock": False, "campaign": f"err:{type(e).__name__}", "size": 0})
    return out


# ============ 2) 独角鲸云 (WHMCS Bearer) ============
def fetch_site_a(env: dict):
    # ⚠️ Pitfall 19 坑 2: env.get() 没设时返回空, 给显式默认值
    url = env.get("SITE_A_API_URL") or "https://api.fuckip.me/api/v1/plans"
    token = env.get("SITE_A_TOKEN", "")
    if not token:
        return None
    headers = {"Authorization": f"Bearer {token}"}
    all_items = []
    page = 1
    while True:
        try:
            r = requests.get(url, params={"limit": 200, "page": page}, headers=headers, timeout=15)
            data = r.json()
        except Exception as e:
            return {"error": str(e), "items": all_items, "total": 0}
        if data.get("code") != 0:
            return {"error": f"api_err:{data.get('code')}", "items": all_items, "total": 0}
        body = data.get("data", {})
        items = body.get("plans", []) if isinstance(body, dict) else body
        all_items.extend(items)
        total = body.get("total", 0) if isinstance(body, dict) else data.get("total", 0)
        if len(all_items) >= total or not items:
            break
        page += 1
    # ⚠️ Pitfall 21: fuckip.me 库存字段是 "remaining"(per-plan 库存数), 不是 available/stock
    # 示例: plan["remaining"] = 9 = 还有 9 台, plan["sold_out"] = False
    # 多查几个兼容其他 WHMCS 商家
    def is_available(p):
        for k in ("remaining", "available", "stock", "qty", "quantity"):
            v = p.get(k, 0)
            if isinstance(v, (int, float)) and v > 0:
                return True
        return False
    available = [p for p in all_items if is_available(p)]
    return {"items": all_items, "total": total, "available": available}


# ============ 3) Incudal ============
def fetch_site_c(env: dict):
    url = env.get("SITE_C_API_URL", "")
    token = env.get("SITE_C_TOKEN", "")
    if not url:
        return None
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()
    except Exception as e:
        return {"error": str(e), "packages": []}
    # ⚠️ Pitfall 19 坑 3 + Pitfall 21: incudal 顶层 packages, 不是 data.packages
    # ⚠️ Pitfall 21: ?source=official 只看 1 个 package(探針機), 看全部要 no source 或 community
    if isinstance(data, dict):
        pkgs = data.get("packages", [])
    else:
        pkgs = []
    return {"packages": pkgs, "raw_keys": list(data.keys()) if isinstance(data, dict) else "not-dict"}


# ============ 推送 ============
def push_tg(env: dict, text: str) -> bool:
    chat_ids_str = env.get("TELEGRAM_CHAT_IDS", env.get("TELEGRAM_CHAT_ID", ""))
    chat_ids = [c.strip() for c in chat_ids_str.split(",") if c.strip()]
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    if not token or not chat_ids:
        print("[push] no token or chat_ids", flush=True)
        return False
    # ⚠️ Pitfall 19 坑 4: 单个 chat_id 失败 continue, 不 return
    any_ok = False
    for cid in chat_ids:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": cid, "parse_mode": "HTML", "text": text,
                      "disable_web_page_preview": True},
                timeout=10
            )
            j = r.json()
            ok = j.get("ok", False)
            if ok:
                print(f"[push] {cid} OK", flush=True)
                any_ok = True
            else:
                print(f"[push] {cid} FAIL: {j.get('description', '')[:80]}", flush=True)
        except Exception as e:
            print(f"[push] {cid} exception: {e}", flush=True)
    return any_ok


# ============ 主逻辑 ============
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="只 print 不发 TG")
    args = parser.parse_args()

    env = load_env()
    now = datetime.now().strftime("%H:%M:%S")
    print(f"=== inventory snapshot @ {now} ===", flush=True)

    # 1) DediRock
    dedi = fetch_dedi()
    for p in dedi:
        print(f"  [Dedi] {p['code']}: in_stock={p['in_stock']} campaign={p['campaign']}", flush=True)

    # 2) 独角鲸云
    site_a = fetch_site_a(env)
    if site_a and "items" in site_a:
        n_total = site_a.get("total", 0)
        n_avail = len(site_a.get("available", []))
        # ⚠️ Pitfall 21: fuckip.me 用 price_monthly 字段
        cheap = [p for p in site_a["items"] if 0 < p.get("price_monthly", 0) <= 0.4]
        super_cheap = [p for p in site_a["items"] if 0 < p.get("price_monthly", 0) <= 0.1]
        n_cheap = len(cheap)
        n_super_cheap = len(super_cheap)
        print(f"  [site_a] total={n_total} avail={n_avail} 0-0.4={n_cheap} 0-0.1={n_super_cheap}", flush=True)
    else:
        n_total = n_avail = n_cheap = n_super_cheap = 0
        err = site_a.get("error", "no data") if site_a else "no config"
        print(f"  [site_a] FAIL: {err}", flush=True)

    # 3) Incudal
    site_c = fetch_site_c(env)
    if site_c and "packages" in site_c:
        n_pkgs = len(site_c.get("packages", []))
        print(f"  [site_c] packages={n_pkgs} raw_keys={site_c.get('raw_keys')}", flush=True)
    else:
        n_pkgs = 0
        err = site_c.get("error", "no data") if site_c else "no config"
        print(f"  [site_c] FAIL: {err}", flush=True)

    # 4) 生成消息
    parts = [f"📊 <b>3 家库存快照</b> · {now}", "━━━━━━━━━━━━━━━━━━━━"]

    parts.append("\n🔥 <b>DediRock</b>")
    for p in dedi:
        if p["in_stock"]:
            parts.append(f"  • {p['code']}: in_stock / ${p['price']} / 活动 {p['campaign']}")
        else:
            parts.append(f"  • {p['code']}: out_of_stock ({p['campaign']})")

    if n_total > 0:
        parts.append("\n🐳 <b>独角鲸云</b>")
        parts.append(f"  • {n_total} plans 总 / {n_avail} available")
        parts.append(f"  • 价格分布: 0-0.4 优化 {n_cheap} / 0-0.1 随便 {n_super_cheap}")
    else:
        parts.append("\n🐳 <b>独角鲸云</b>: 抓取失败")

    if n_pkgs > 0:
        parts.append(f"\n💎 <b>Incudal</b>")
        parts.append(f"  • {n_pkgs} packages")
        for pkg in site_c.get("packages", [])[:5]:
            name = pkg.get("name") or pkg.get("title") or pkg.get("id", "?")
            # incudal 没 price 字段
            price = pkg.get("price") or pkg.get("price_monthly") or "?"
            sold = "售罄" if pkg.get("soldOut") else "在售"
            parts.append(f"  • {name} · {sold} · {pkg.get('cpu_max', '?')} CPU / {pkg.get('memory_max', '?')} MB")
    else:
        parts.append("\n💎 <b>Incudal</b>: 抓取失败")

    parts.append(f"\n⏰ {now} · 3 家库存快照")
    parts.append("━━━━━━━━━━━━━━━━━━━━")

    text = "\n".join(parts)
    print(f"\n=== 消息 ({len(text)} chars) ===", flush=True)
    print(text, flush=True)

    if args.dry:
        print("\n[dry] skip push", flush=True)
        return

    # 推送
    print(f"\n=== 推送 ===", flush=True)
    push_tg(env, text)


if __name__ == "__main__":
    main()
