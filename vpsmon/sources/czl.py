from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import re

import requests

from vpsmon.models import Money, VpsOffer
from vpsmon.rules.parsing import parse_cpu_cores, parse_ram_gb, parse_usd_year

CN_ROUTE_KEYWORDS = ["优化", "CN2", "GIA", "CMI", "9929", "4837", "精品", "三网", "BGP", "回国", "直连", "低延迟", "软银", "AS9929"]

# czl.net sometimes marks provider offers available even when the final WHMCS cart is out of stock.
# ColoCrossing is a confirmed false-positive source (2026-07-07). Keep rows for history, but do not render as available.
UNRELIABLE_STOCK_PROVIDERS = {"colocrossing"}


def _stable_offer_id(item: dict) -> str:
    """Generate a stable unique key based on offer attributes, not the volatile API id.
    
    czl.net assigns a new sequential id every time a plan is re-listed, so using
    id as the key causes every fetch to create duplicate "new" events.
    Instead, hash the stable attributes: provider + title + location + cpu + ram + disk + bandwidth + price.
    """
    parts = [
        str(item.get("provider") or ""),
        str(item.get("title") or item.get("name") or ""),
        str(item.get("location") or ""),
        str(item.get("cpu") or ""),
        str(item.get("ram") or item.get("memory") or ""),
        str(item.get("disk") or ""),
        str(item.get("bandwidth") or item.get("bw") or ""),
        str(item.get("price") or ""),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _available(item: dict) -> bool:
    if item.get("isAvailable") is not None:
        return bool(item.get("isAvailable"))
    if item.get("soldOut") is not None:
        return not bool(item.get("soldOut"))
    stock = item.get("stock", item.get("available", item.get("remaining")))
    if stock is None:
        return True
    try:
        return int(stock) > 0
    except (TypeError, ValueError):
        return True


def _stock(item: dict) -> int | None:
    stock = item.get("stock", item.get("remaining"))
    if stock is None:
        return None
    try:
        return int(stock)
    except (TypeError, ValueError):
        return None


def _route(item: dict) -> str:
    text = " ".join(str(item.get(k, "")) for k in ("title", "location", "remark"))
    hits = [kw for kw in CN_ROUTE_KEYWORDS if kw.lower() in text.lower() or kw in text]
    remark = str(item.get("remark") or "").strip()
    if remark:
        cleaned_remark = re.sub(r"更新时间\s*,?\s*\d{4}-\d{2}-\d{2}T\S+", "", remark)
        remark_parts = [part.strip(" ，,;；:/") for part in cleaned_remark.split("/") if part.strip(" ，,;；:/")]
        for part in remark_parts:
            if part not in hits:
                hits.append(part)
    return " / ".join(hits) if hits else "未标注"


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(x).strip() for x in value if str(x).strip())
    return str(value).strip()


def normalize(item: dict, deploy_url: str) -> VpsOffer:
    raw_price = str(item.get("price") or "")
    usd_year = parse_usd_year(raw_price)
    stable_id = _stable_offer_id(item)
    raw_id = str(item.get("id") or item.get("item_id") or "")
    # Use raw_id in URL if available, otherwise use stable_id
    url_id = raw_id if raw_id else stable_id
    url = deploy_url.format(item_id=url_id)
    return VpsOffer(
        source="czl",
        offer_id=stable_id,
        title=_clean_text(item.get("title") or item.get("name") or "未知套餐"),
        provider=_clean_text(item.get("provider")),
        location=_clean_text(item.get("location")),
        cpu_cores=parse_cpu_cores(item.get("cpu")),
        ram_gb=parse_ram_gb(item.get("ram") or item.get("memory")),
        disk=_clean_text(item.get("disk")),
        bandwidth=_clean_text(item.get("bandwidth") or item.get("bw")),
        route=_route(item),
        price=Money(raw=raw_price, usd_year=usd_year) if usd_year is not None else None,
        available=_available(item) and _clean_text(item.get("provider")).lower() not in UNRELIABLE_STOCK_PROVIDERS,
        stock=_stock(item),
        url=url,
        raw=item,
    )


class CzlSource:
    SOURCE_NAME = "czl"
    def __init__(self, config: dict):
        self.api_url = config["api_url"]
        self.page_size = int(config.get("page_size", 12))
        self.max_pages = int(config.get("max_pages", 100))
        self.max_workers = int(config.get("max_workers", 8))
        self.deploy_url = config.get("deploy_url", "https://vps-monitor.czl.net/buy/{item_id}")

    def _fetch_page(self, page: int) -> tuple[int, dict | list | None]:
        try:
            resp = requests.get(
                self.api_url,
                params={"page": page, "pageSize": self.page_size},
                timeout=15,
            )
            resp.raise_for_status()
            return page, resp.json()
        except Exception:
            return page, None

    def fetch(self) -> list[VpsOffer]:
        pages = list(range(1, self.max_pages + 1))
        results: dict[int, dict | list] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._fetch_page, page): page for page in pages}
            for future in as_completed(futures):
                page, data = future.result()
                if data is not None:
                    results[page] = data

        raw_items: list[dict] = []
        for page in sorted(results):
            body = results[page]
            rows = body.get("data", body) if isinstance(body, dict) else body
            if isinstance(rows, dict):
                rows = rows.get("items", rows.get("rows", []))
            if isinstance(rows, list):
                raw_items.extend([row for row in rows if isinstance(row, dict)])

        return [normalize(item, self.deploy_url) for item in raw_items]


register("czl", CzlSource)
