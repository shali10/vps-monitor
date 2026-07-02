"""Main loop — polls each site independently with per-site exception isolation."""
import argparse
import os
import signal
import time

from config import SITE_A_TOKEN, SITE_E_API_URL
from core.logging import log
from core.state import load_state, save_state
from sites.site_a import monitor_site_a
from sites.site_e import monitor_site_e


def main():
    """Entry point: load state, register signal handlers, run poll loop."""
    log.info("vps-monitor starting (A+E only)")
    state = load_state()

    # NOTIFY_ONLY_CHANGES=true (default): first poll after restart is silent
    if os.environ.get("NOTIFY_ONLY_CHANGES", "true").lower() in ("true", "1", "yes"):
        state.setdefault("site_a", {}).setdefault("first_run", True)
        state.setdefault("site_e", {}).setdefault("first_run", True)

    running = True

    def stop(signum, frame):
        nonlocal running
        running = False
        log.info("received signal %d, shutting down...", signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    from config import SITE_A_POLL_INTERVAL, SITE_E_POLL_INTERVAL
    last_a = last_e = 0

    while running:
        now = int(time.time())

        # Site A: 独角鲸云
        try:
            if now - last_a >= SITE_A_POLL_INTERVAL:
                last_a = now
                if SITE_A_TOKEN:
                    n_new, n_restock = monitor_site_a(state.setdefault("site_a", {}))
                    if n_new or n_restock:
                        log.info("site-a: %d new, %d restocked", n_new, n_restock)
        except Exception as e:
            log.exception("site-a poll failed: %s", e)

        # Site E: czl.net
        try:
            if now - last_e >= SITE_E_POLL_INTERVAL:
                last_e = now
                if SITE_E_API_URL:
                    n_new, n_restock, n_drop = monitor_site_e(state.setdefault("site_e", {}))
                    if n_new or n_restock or n_drop:
                        log.info("site-e: %d new, %d restock, %d drop", n_new, n_restock, n_drop)
        except Exception as e:
            log.exception("site-e poll failed: %s", e)

        save_state(state)
        time.sleep(min(SITE_A_POLL_INTERVAL, SITE_E_POLL_INTERVAL, 10))

    save_state(state)
    log.info("vps-monitor stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="run one poll cycle then exit")
    parser.add_argument("--site", choices=["a", "e", "all"], default="all",
                        help="--once mode: which source to poll")
    args = parser.parse_args()

    if args.once:
        state = load_state()
        if args.site in ("a", "all") and SITE_A_TOKEN:
            n_new, n_restock = monitor_site_a(state.setdefault("site_a", {}))
            print(f"site-a: {n_new} new, {n_restock} restocked")
        if args.site in ("e", "all") and SITE_E_API_URL:
            n_new, n_restock, n_drop = monitor_site_e(state.setdefault("site_e", {}))
            print(f"site-e: {n_new} new, {n_restock} restock, {n_drop} drop")
        save_state(state)
    else:
        main()
