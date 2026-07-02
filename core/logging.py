"""Logging setup — single _FlushFileHandler, single init at import time."""
import logging

from config import LOG_FILE


class _FlushFileHandler(logging.FileHandler):
    """FileHandler that flushes after every emit (fixes delayed log writes)."""

    def emit(self, record):
        super().emit(record)
        self.flush()


# Module-level setup: runs once on first import
_log_file = _FlushFileHandler(LOG_FILE, encoding="utf-8", delay=False)
_log_file.setLevel(logging.INFO)
_log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_log_file.setFormatter(_log_formatter)
log = logging.getLogger("vps-monitor")
log.setLevel(logging.INFO)
log.addHandler(_log_file)
log.addHandler(logging.StreamHandler())


def get_logger():
    """Return the configured 'vps-monitor' logger."""
    return log
