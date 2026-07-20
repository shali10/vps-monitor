from __future__ import annotations

import os

import requests

from vpsmon.models import Money, VpsOffer

ROUTE_CHECKS = [
    ("三网", "三网"),
    ("cn2", "CN2"),
    ("gia", "GIA"),
    ("cmin2", "CMIN2"),
    ("cmi", "CMI"),
    ("9929", "9929"),
    ("4837", "4837"),
    ("bgp", "BGP"),
    ("移动直连", "移动直连"),
    ("联通可直连", "联通可直连"),
    ("直连", "直连"),
    ("低延迟", "低延迟"),
    ("原生", "原生IP"),
    ("家宽", "家宽"),
    ("大流量", "大流量"),
]


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _text_blob(plan: dict) -> str:
    fields = ["name", "machine_name", "machine_description", "machine_region", "machine_vm_type"]
    return " ".join(_clean(plan.get(k)) for k in fields).lower()


def _route(plan: dict) -> str:
    blob = _text_blob(plan)
    parts: list[str] = []
    for needle, label in ROUTE_CHECKS:
        if needle in blob and label not in parts:
            parts.append(label)
    for tag in plan.get("machine_tags") or []:
        tag_s = _clean(tag)
        if tag_s and tag_s not in parts:
            parts.append(tag_s)
    if parts:
        return " / ".join(parts[:6])
    desc = _clean(plan.get("machine_description")).replace("\n", " ")
    return desc[:80] + ("..." if len(desc) > 80 else "") if desc else "未标注"


def _price_monthly(plan: dict) -> float | None:
    if plan.get("price_monthly") is not None:
        try:
            return float(plan["price_monthly"])
        except (TypeError, ValueError):
            return None
    if plan.get("price_cents") is not None:
        try:
            return float(plan["price_cents"]) / 100
        except (TypeError, ValueError):
            return None
    return None


def _stock(plan: dict) -> int | None:
    remaining = plan.get("remaining")
    if remaining is None:
        return None
    try:
        return int(remaining)
    except (TypeError, ValueError):
        return None


def _available(plan: dict) -> bool:
    stock = _stock(plan)
    return True if stock is None else stock > 0


def _traffic(plan: dict) -> str:
    raw = plan.get("monthly_traffic_gb")
    try:
        gb = float(raw or 0)
    except (TypeError, ValueError):
        return ""
    if gb <= 0:
        return "不限流量"
    return f"{gb:g}GB BW"


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def normalize(plan: dict, deploy_url: str) -> VpsOffer:
    plan_id = _clean(plan.get("id"))
    price_month = _price_monthly(plan)
    price_raw = f"${price_month:g}/月" if price_month is not None else ""
    url = deploy_url.format(
        plan_id=plan_id,
        machine_id=_clean(plan.get("machine_id")),
        region=_clean(plan.get("machine_region_id") or plan.get("machine_region")),
    )
    disk = _clean(plan.get("disk_gb"))
    bandwidth = _clean(plan.get("bandwidth_mbps"))
    traffic = _traffic(plan)
    cpu = _float_or_none(plan.get("cpu"))
    ram_mb = _float_or_none(plan.get("ram_mb"))
    return VpsOffer(
        source="dujiaojing",
        offer_id=plan_id,
        title=_clean(plan.get("name")) or "未知套餐",
        provider=_clean(plan.get("machine_name")) or "独角鲸云",
        location=_clean(plan.get("machine_region")),
        cpu_cores=cpu,
        ram_gb=(ram_mb / 1024) if ram_mb is not None else None,
        disk=f"{disk}GB SSD" if disk else "",
        bandwidth=f"{bandwidth}Mbps" if bandwidth else "",
        traffic=traffic,
        route=_route(plan),
        price=Money(raw=price_raw, usd_year=price_month * 12) if price_month is not None else None,
        available=_available(plan),
        stock=_stock(plan),
        url=url,
        raw=plan,
    )


class DujiaojingSource:
    SOURCE_NAME = "dujiaojing"
    def __init__(self, config: dict):
        self.api_url = config["api_url"]
        self.token = config.get("token") or os.environ.get(config.get("token_env", ""), "")
        self.deploy_url = config.get("deploy_url", "https://dash.fuckip.me/deploy?plan_id={plan_id}")
        self.page_size = int(config.get("page_size", 200))
        self.max_pages = int(config.get("max_pages", 50))

    def fetch(self) -> list[VpsOffer]:
        if not self.token:
            raise RuntimeError("dujiaojing token missing")
        items: list[dict] = []
        total = 0
        for page in range(1, self.max_pages + 1):
            resp = requests.get(
                self.api_url,
                params={"limit": self.page_size, "page": page},
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"dujiaojing API error: {data}")
            body = data.get("data", {})
            page_items = body.get("plans", []) if isinstance(body, dict) else body
            total = body.get("total", 0) if isinstance(body, dict) else data.get("total", 0)
            if not isinstance(page_items, list) or not page_items:
                break
            items.extend([item for item in page_items if isinstance(item, dict)])
            if total and len(items) >= int(total):
                break
        return [normalize(item, self.deploy_url) for item in items]


register("dujiaojing", DujiaojingSource)
