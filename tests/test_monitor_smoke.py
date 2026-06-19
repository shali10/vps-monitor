#!/usr/bin/env python3
"""Smoke tests for monitor.py — syntax + import + basic structure."""

import ast
import sys
import subprocess
from pathlib import Path

MONITOR_PY = Path(__file__).parent.parent / "monitor.py"


def test_syntax_ok():
    """monitor.py 必须语法 OK。"""
    src = MONITOR_PY.read_text(encoding="utf-8")
    try:
        ast.parse(src, filename=str(MONITOR_PY))
    except SyntaxError as e:
        pytest.fail(f"monitor.py syntax error: {e}")


def test_py_compile():
    """python3 -m py_compile 必须通过(系统级检查)。"""
    r = subprocess.run(
        ["python3", "-m", "py_compile", str(MONITOR_PY)],
        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"py_compile failed: {r.stderr}"


def test_required_functions_exist():
    """关键函数必须存在(per-site adapter 模式铁律)。"""
    src = MONITOR_PY.read_text(encoding="utf-8")
    # 至少要有 Site A 的 4 个函数
    for fn in ["fetch_site_a", "compare_site_a",
               "notify_site_a_restocked", "monitor_site_a"]:
        assert f"def {fn}" in src, f"missing function: {fn}"


def test_required_constants_exist():
    """关键常量必须存在(系统级配置)。"""
    src = MONITOR_PY.read_text(encoding="utf-8")
    for const in ['SITE_A_API_URL', 'TELEGRAM_BOT_TOKEN', 'POLL_INTERVAL']:
        assert const in src, f"missing constant: {const}"


def test_no_secrets_in_source():
    """源码不应包含真实 token / chat_id(仅占位符 OK)。"""
    src = MONITOR_PY.read_text(encoding="utf-8")
    # 占位符 OK,但真实 JWT (eyJ 开头 + 长度 > 100) 不应在源码
    import re
    real_jwts = re.findall(r"eyJ[A-Za-z0-9_-]{50,}", src)
    assert len(real_jwts) == 0, f"疑似真实 JWT 泄露: {real_jwts[:1]}"


def test_main_loop_has_per_site_try():
    """主循环必须有 per-site try/except(防 Pitfall 17 阻塞)。"""
    src = MONITOR_PY.read_text(encoding="utf-8")
    # 检查 try/except 在 main 循环里出现多次(每个 site 一次)
    try_count = src.count("    try:") + src.count("\ttry:")
    assert try_count >= 2, f"per-site try 太少: {try_count},可能回退到共享 try"


# pytest 不一定有,这里 inline 跑
import traceback

def _run():
    tests = [test_syntax_ok, test_py_compile, test_required_functions_exist,
             test_required_constants_exist, test_no_secrets_in_source,
             test_main_loop_has_per_site_try]
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
    else:
        print(f"\n{len(tests)}/{len(tests)} PASSED")


if __name__ == "__main__":
    _run()
