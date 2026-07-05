from __future__ import annotations

from collections.abc import Iterable

from vpsmon.models import VpsOffer


def _pool_matches(offer: VpsOffer, pool: dict) -> bool:
    if offer.ram_gb is None:
        return False
    if offer.cpu_cores is None:
        return False
    if offer.ram_gb < float(pool.get("ram_min_gb", 0)):
        return False
    if offer.ram_gb > float(pool.get("ram_max_gb", 10**9)):
        return False
    if offer.cpu_cores < float(pool.get("cpu_min_cores", 0)):
        return False
    if offer.cpu_cores > float(pool.get("cpu_max_cores", 10**9)):
        return False
    if "usd_year_min" in pool or "usd_year_max" in pool:
        if offer.price is None:
            return False
        if offer.price.usd_year < float(pool.get("usd_year_min", 0)):
            return False
        if offer.price.usd_year > float(pool.get("usd_year_max", 10**9)):
            return False
    return True


def pool_name(offer: VpsOffer, pools: list[dict]) -> str | None:
    for pool in pools:
        if _pool_matches(offer, pool):
            return str(pool.get("name") or "pool")
    return None


def offer_allowed(offer: VpsOffer, source_rules: dict, global_rules: dict | None = None) -> bool:
    global_rules = global_rules or {}
    blob = " ".join([offer.title, offer.disk, offer.provider, offer.route]).lower()
    for keyword in global_rules.get("exclude_keywords", []):
        if str(keyword).lower() in blob:
            return False

    if offer.cpu_cores is None or offer.ram_gb is None:
        return False

    if offer.price is None:
        return False

    pools = source_rules.get("pools") or []
    if pools:
        return pool_name(offer, pools) is not None

    if "price_max_usd_month" in source_rules and offer.price.usd_year / 12 > float(source_rules["price_max_usd_month"]):
        return False
    if "price_min_usd_year" in source_rules and offer.price.usd_year < float(source_rules["price_min_usd_year"]):
        return False
    if "price_max_usd_year" in source_rules and offer.price.usd_year > float(source_rules["price_max_usd_year"]):
        monthly = offer.price.usd_year / 12
        max_monthly = float(source_rules.get("monthly_price_max_usd", 0))
        if max_monthly <= 0 or monthly > max_monthly:
            return False
    return True


def filter_offers(offers: Iterable[VpsOffer], source_rules: dict, global_rules: dict | None = None) -> list[VpsOffer]:
    return [offer for offer in offers if offer_allowed(offer, source_rules, global_rules)]
