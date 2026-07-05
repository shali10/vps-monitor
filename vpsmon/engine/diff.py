from __future__ import annotations

from vpsmon.models import Event, EventType, VpsOffer
from vpsmon.storage.sqlite import StateStore


def diff_offers(
    store: StateStore,
    offers: list[VpsOffer],
    first_run_silent: bool = True,
    commit: bool = True,
) -> list[Event]:
    events: list[Event] = []
    source_counts: dict[str, int] = {}
    for offer in offers:
        source_counts[offer.source] = source_counts.get(offer.source, 0) + 1

    silent_sources = {source for source in source_counts if first_run_silent and store.count_source(source) == 0}

    for offer in offers:
        old = store.get(offer.source, offer.offer_id)
        if old is None:
            if offer.available and offer.source not in silent_sources:
                events.append(Event(EventType.NEW, offer))
            continue

        old_available = bool(old["available"])
        if not old_available and offer.available:
            events.append(Event(EventType.RESTOCK, offer))

        old_price = old["usd_year"]
        new_price = offer.price.usd_year if offer.price else None
        if old_price and new_price and new_price < float(old_price) * 0.99:
            events.append(
                Event(
                    EventType.PRICE_DROP,
                    offer,
                    old_price_raw=old["price_raw"],
                    new_price_raw=offer.price.raw if offer.price else None,
                )
            )

    if commit:
        store.upsert_many(offers)
    return events
