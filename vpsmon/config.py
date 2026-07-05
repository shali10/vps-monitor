from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConfigError(RuntimeError):
    pass


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"config not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ConfigError("config root must be object")
    data.setdefault("state_db", "./state/vpsmon.sqlite3")
    data.setdefault("sources", {})
    data.setdefault("rules", {})
    data.setdefault("telegram", {"enabled": False})
    return data
