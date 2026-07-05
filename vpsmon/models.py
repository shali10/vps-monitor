from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    NEW = "new"
    RESTOCK = "restock"
    PRICE_DROP = "price_drop"


@dataclass(frozen=True)
class Money:
    raw: str
    usd_year: float


@dataclass(frozen=True)
class VpsOffer:
    source: str
    offer_id: str
    title: str
    provider: str = ""
    location: str = ""
    cpu_cores: float | None = None
    ram_gb: float | None = None
    disk: str = ""
    bandwidth: str = ""
    traffic: str = ""
    route: str = ""
    price: Money | None = None
    available: bool = True
    stock: int | None = None
    url: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Event:
    event_type: EventType
    offer: VpsOffer
    old_price_raw: str | None = None
    new_price_raw: str | None = None
