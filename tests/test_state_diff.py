#!/usr/bin/env python3
"""Tests for state.json diff logic.

state.json 是 baseline 对比层,核心测试场景:
- 新套餐 id 出现 → new_arrival
- soldOut 翻转 true→false → restocked
- 字段纯变化(remaining 5→10) → 不触发
- 空 old / 空 new → baseline(first_run)
"""

import sys


# Inline 简化版 compare_site_a 的核心逻辑(便于单元测)
def compare_site_a_simple(state, items):
    """简化版 Site A compare,独立可测。"""
    new_arrivals, restocked = [], []
    old_plans = state.get("plans", {})
    new_plans = {}
    for p in items:
        pid = str(p["id"])
        new_plans[pid] = {
            "remaining": p.get("remaining", 0),
            "sold_out": p.get("sold_out", False),
        }
        if pid not in old_plans:
            new_arrivals.append(p)
        elif old_plans[pid].get("sold_out") and not p.get("sold_out"):
            restocked.append(p)
    return new_arrivals, restocked, new_plans


def test_empty_state_first_run():
    """空 state 应该是 first_run,不推任何事件。"""
    state = {"plans": {}, "first_run": True}
    items = [{"id": "1", "sold_out": False, "remaining": 5}]
    new, restocked, new_state = compare_site_a_simple(state, items)
    # caller 负责检查 first_run 跳过
    assert new == items, "新套餐应识别"
    # 但实际不推(Pitfall: first_run 只记 baseline)


def test_new_arrival():
    """新套餐 id 第一次出现 = new_arrival。"""
    state = {"plans": {"1": {"sold_out": False, "remaining": 5}}}
    items = [
        {"id": "1", "sold_out": False, "remaining": 5},
        {"id": "2", "sold_out": False, "remaining": 3},  # ← 新的
    ]
    new, restocked, new_state = compare_site_a_simple(state, items)
    assert len(new) == 1 and new[0]["id"] == "2"
    assert restocked == []


def test_restocked():
    """sold_out true → false = 补货。"""
    state = {"plans": {"1": {"sold_out": True, "remaining": 0}}}
    items = [{"id": "1", "sold_out": False, "remaining": 5}]
    new, restocked, new_state = compare_site_a_simple(state, items)
    assert new == []  # 不是新套餐
    assert len(restocked) == 1
    assert restocked[0]["id"] == "1"


def test_no_change():
    """字段没变化 → 不推。"""
    state = {"plans": {"1": {"sold_out": False, "remaining": 5}}}
    items = [{"id": "1", "sold_out": False, "remaining": 5}]
    new, restocked, new_state = compare_site_a_simple(state, items)
    assert new == []
    assert restocked == []


def test_remaining_change_no_event():
    """remaining 5→10 不是事件(只关心 sold_out 翻转)。"""
    state = {"plans": {"1": {"sold_out": False, "remaining": 5}}}
    items = [{"id": "1", "sold_out": False, "remaining": 10}]
    new, restocked, new_state = compare_site_a_simple(state, items)
    assert new == []
    assert restocked == []


def test_sold_out_no_event():
    """sold_out false → true(售罄)不是 restock 事件(我们不推售罄)。"""
    state = {"plans": {"1": {"sold_out": False, "remaining": 5}}}
    items = [{"id": "1", "sold_out": True, "remaining": 0}]
    new, restocked, new_state = compare_site_a_simple(state, items)
    assert new == []
    assert restocked == []


def test_mixed_scenario():
    """混合:新 + 补货 + 售罄 + 无变化,只推新+补货。"""
    state = {
        "plans": {
            "1": {"sold_out": True, "remaining": 0},   # → restock
            "2": {"sold_out": False, "remaining": 5},  # → sold out(不推)
            "3": {"sold_out": False, "remaining": 5},  # 无变化
        }
    }
    items = [
        {"id": "1", "sold_out": False, "remaining": 5},
        {"id": "2", "sold_out": True, "remaining": 0},
        {"id": "3", "sold_out": False, "remaining": 5},
        {"id": "4", "sold_out": False, "remaining": 3},  # 新
    ]
    new, restocked, new_state = compare_site_a_simple(state, items)
    assert {p["id"] for p in new} == {"4"}
    assert {p["id"] for p in restocked} == {"1"}


import traceback


def _run():
    tests = [
        test_empty_state_first_run,
        test_new_arrival,
        test_restocked,
        test_no_change,
        test_remaining_change_no_event,
        test_sold_out_no_event,
        test_mixed_scenario,
    ]
    failed = []
    for t in tests:
        name = t.__name__
        try:
            t()
            print(f"  ✅ {name}")
        except Exception as e:
            failed.append((name, e))
            print(f"  ❌ {name}: {e}")
            traceback.print_exc()
    if failed:
        sys.exit(1)
    else:
        print(f"\n{len(tests)}/{len(tests)} PASSED")


if __name__ == "__main__":
    _run()
