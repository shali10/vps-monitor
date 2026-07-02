"""State persistence — load/save state.json with atomic write."""
import json

from config import STATE_FILE


def load_state():
    """Load state from disk, return default if missing."""
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "site_a": {"plans": {}, "first_run": True},
        "site_e": {"items": {}, "first_run": True},
        "last_poll": 0,
    }


def save_state(state):
    """Atomic write via tmp + rename."""
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.replace(STATE_FILE)
