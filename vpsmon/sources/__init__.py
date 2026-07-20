from __future__ import annotations

from typing import Any

_registry: dict[str, type] = {}


def register(name: str, cls: type) -> None:
    """Register a source adapter class under a short name.

    The class must implement ``__init__(self, config: dict)`` and
    ``fetch(self) -> list[VpsOffer]``.
    """
    _registry[name] = cls


def get_source(name: str, config: dict) -> Any:
    """Build a source instance by name, or raise KeyError."""
    cls = _registry.get(name)
    if cls is None:
        raise KeyError(f"unknown source: {name!r}; available: {list(_registry)}")
    return cls(config)


def list_sources() -> list[str]:
    """Return all registered source names in insertion order."""
    return list(_registry)
