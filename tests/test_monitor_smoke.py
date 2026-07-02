#!/usr/bin/env python3
"""Smoke tests for monitor.py — syntax + import + basic structure.

Refactored to use runtime introspection (import monitor → hasattr).
Previous version scanned source text, which broke when monitor.py became
a re-export shim over core/ + sites/.
"""
import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

MONITOR_PY = Path(__file__).parent.parent / "monitor.py"
MAIN_PY = Path(__file__).parent.parent / "main.py"

# Load monitor as module (triggers import chain)
# Load monitor as module (triggers import chain)
_spec = importlib.util.spec_from_file_location("monitor", MONITOR_PY)
assert _spec is not None, f"cannot load spec from {MONITOR_PY}"
monitor = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(monitor)


def test_syntax_ok():
    """monitor.py must parse."""
    src = MONITOR_PY.read_text(encoding="utf-8")
    ast.parse(src, filename=str(MONITOR_PY))


def test_py_compile():
    """py_compile must pass."""
    r = subprocess.run(
        [sys.executable, "-m", "py_compile", str(MONITOR_PY)],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, f"py_compile failed: {r.stderr}"


def test_required_functions_exist():
    """Key site-a adapter functions must be exposed by monitor module."""
    for fn in ["fetch_site_a", "compare_site_a",
               "notify_site_a_restocked", "monitor_site_a"]:
        assert hasattr(monitor, fn), f"missing function: {fn}"


def test_required_site_e_functions_exist():
    """Key site-e adapter functions must be exposed by monitor module."""
    for fn in ["fetch_site_e", "compare_site_e", "monitor_site_e",
               "_site_e_pool_match", "_parse_usd_year_e", "_parse_ram_gb_e",
               "_site_e_is_vps"]:
        assert hasattr(monitor, fn), f"missing function: {fn}"


def test_required_constants_exist():
    """Key constants must be exposed by monitor module."""
    for const in ["SITE_A_API_URL", "TELEGRAM_BOT_TOKEN", "POLL_INTERVAL",
                  "SITE_E_API_URL", "SITE_A_TOKEN"]:
        assert hasattr(monitor, const), f"missing constant: {const}"


def test_no_secrets_in_source():
    """Source must not contain real tokens."""
    import re
    src = MONITOR_PY.read_text(encoding="utf-8")
    real_jwts = re.findall(r"eyJ[A-Za-z0-9_-]{50,}", src)
    assert len(real_jwts) == 0, f"possible JWT leak: {real_jwts[:1]}"


def test_main_loop_has_per_site_try():
    """main.py main loop must have per-site try/exception isolation."""
    src = MAIN_PY.read_text(encoding="utf-8")
    try_count = src.count("    try:") + src.count("\ttry:")
    assert try_count >= 2, f"per-site try count too low: {try_count}"


if __name__ == "__main__":
    tests = [test_syntax_ok, test_py_compile, test_required_functions_exist,
             test_required_site_e_functions_exist, test_required_constants_exist,
             test_no_secrets_in_source, test_main_loop_has_per_site_try]
    failed = []
    for t in tests:
        name = t.__name__
        try:
            t()
            print(f"  ✅ {name}")
        except Exception as e:
            failed.append((name, e))
            print(f"  ❌ {name}: {e}")
    if failed:
        print(f"\n{len(failed)}/{len(tests)} FAILED")
        sys.exit(1)
    print(f"\nAll {len(tests)} smoke tests passed.")
