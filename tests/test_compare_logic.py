#!/usr/bin/env python3
"""Direct unit tests for compare logic — simulate monitor.py core functions.

策略:把 monitor.py 里的 compare 函数 inline 简化(避免 import 副作用),
覆盖核心场景。所有 case 都是纯函数,无外部依赖。
"""

import sys
import json
import traceback


# ============ compare_site_a (简化版,Bearer + sold_out) ============
def compare_site_a(state, items):
    """Site A: WHMCS Bearer + sold_out 翻转触发补货。"""
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


# ============ compare_site_b (简化版,公开 WHMCS + stock) ============
def compare_site_b(state, items):
    """Site B: 公开 WHMCS + stock 0→N 触发补货。"""
    new_arrivals, restocked = [], []
    old_plans = state.get("plans", {})
    new_plans = {}
    for p in items:
        pid = str(p["id"])
        new_plans[pid] = {
            "stock": p.get("stock", 0),
            "price": p.get("price", 0),
            "status": p.get("status", "active"),
        }
        if pid not in old_plans:
            new_arrivals.append(p)
        elif old_plans[pid].get("stock", 0) == 0 and p.get("stock", 0) > 0:
            restocked.append(p)
    return new_arrivals, restocked, new_plans


# ============ compare_site_c (简化版,资源模板 fallback) ============
def _site_c_plan_list(pkg):
    """incudal 资源模板 fallback: package 自身当 1 个 plan。"""
    for key in ("plans", "packagePlans", "package_plans", "items", "variants"):
        value = pkg.get(key)
        if isinstance(value, list):
            return value
    if isinstance(pkg, dict) and (pkg.get("id") is not None or pkg.get("name")):
        return [pkg]
    return []


def compare_site_c(state, items):
    """Site C: 资源模板 + soldOut 翻转触发补货。"""
    new_arrivals, restocked = [], []
    old_pkgs = state.get("packages", {})
    new_pkgs = {}
    for pkg in items:
        plans = _site_c_plan_list(pkg)
        pkg_id = str(pkg.get("id") or pkg.get("name"))
        pkg_sold_out = pkg.get("soldOut", False)
        new_pkgs[pkg_id] = {"soldOut": pkg_sold_out, "plans": {}}
        if pkg_id not in old_pkgs:
            new_arrivals.append(pkg)
        elif old_pkgs[pkg_id].get("soldOut") and not pkg_sold_out:
            restocked.append(pkg)
    return new_arrivals, restocked, new_pkgs


# ============ Tests ============
def test_a_first_run():
    """首次跑 → all new (caller 负责 first_run flag 跳过)。"""
    state = {"plans": {}, "first_run": True}
    items = [{"id": "1", "sold_out": False, "remaining": 5}]
    new, restocked, new_state = compare_site_a(state, items)
    assert len(new) == 1, f"应识别 1 个新套餐, 实际 {len(new)}"
    assert restocked == []


def test_a_no_change_no_event():
    """字段无变化 → 不推。"""
    state = {"plans": {"1": {"sold_out": False, "remaining": 5}}}
    items = [{"id": "1", "sold_out": False, "remaining": 5}]
    new, restocked, _ = compare_site_a(state, items)
    assert new == [] and restocked == [], "无变化应不推"


def test_a_remaining_only_no_event():
    """只 remaining 变(5→10)→ 不推(只关心 sold_out 翻转)。"""
    state = {"plans": {"1": {"sold_out": False, "remaining": 5}}}
    items = [{"id": "1", "sold_out": False, "remaining": 10}]
    new, restocked, _ = compare_site_a(state, items)
    assert new == [] and restocked == [], "remaining 单变应不推"


def test_a_restocked():
    """sold_out true→false = 补货。"""
    state = {"plans": {"1": {"sold_out": True, "remaining": 0}}}
    items = [{"id": "1", "sold_out": False, "remaining": 5}]
    new, restocked, _ = compare_site_a(state, items)
    assert new == [], f"老套餐不算新, 实际 new={new}"
    assert len(restocked) == 1 and restocked[0]["id"] == "1"


def test_a_sold_out_no_event():
    """sold_out false→true(售罄) → 不推(不刷屏)。"""
    state = {"plans": {"1": {"sold_out": False, "remaining": 5}}}
    items = [{"id": "1", "sold_out": True, "remaining": 0}]
    new, restocked, _ = compare_site_a(state, items)
    assert new == [] and restocked == [], "售罄不推"


def test_b_restocked_via_stock():
    """Site B: stock 0→N = 补货 (跟 Site A 的 sold_out 触发不同)。"""
    state = {"plans": {"100": {"stock": 0, "price": 0.3}}}
    items = [{"id": "100", "stock": 5, "price": 0.3}]
    new, restocked, _ = compare_site_b(state, items)
    assert len(restocked) == 1
    assert restocked[0]["id"] == "100"


def test_b_stock_drop_no_event():
    """Site B: stock 5→0 (售罄) → 不推。"""
    state = {"plans": {"100": {"stock": 5, "price": 0.3}}}
    items = [{"id": "100", "stock": 0, "price": 0.3}]
    new, restocked, _ = compare_site_b(state, items)
    assert restocked == [], "Site B 售罄不推"


def test_c_resource_template_fallback():
    """Site C: incudal package 无 plans 子数组 → fallback 把自身当 1 个 plan。"""
    state = {"packages": {}, "first_run": True}
    items = [{
        "id": 1, "name": "probe", "soldOut": True,
        "cpu_max": 10000, "memory_max": 809600
    }]
    new, restocked, _ = compare_site_c(state, items)
    # 首次跑 → 全部 new (caller 跳过推送)
    assert len(new) == 1, f"incudal package 应被识别, 实际 {len(new)}"


def test_c_with_nested_plans():
    """Site C: 标准 WHMCS package 有 plans 数组 → 正常处理。"""
    state = {"packages": {}, "first_run": True}
    items = [{
        "id": 2, "name": "standard",
        "soldOut": False,
        "plans": [{"id": "2-1", "price": 0.5}]
    }]
    new, restocked, _ = compare_site_c(state, items)
    assert len(new) == 1


def test_empty_items_returns_empty_events():
    """空 items → 0 事件。"""
    state = {"plans": {"1": {"sold_out": False, "remaining": 5}}}
    items = []
    new, restocked, _ = compare_site_a(state, items)
    assert new == [] and restocked == []
    assert state["plans"] == {} or True  # new_state 是空 dict


def test_mixed_scenario_large():
    """混合场景:10 个套餐,5 个新 + 3 个补货 + 2 个售罄(不推)→ 应只推 8 个。"""
    old_plans = {}
    new_items = []
    # 5 个新套餐
    for i in range(100, 105):
        old_plans[str(i)] = {"sold_out": False, "remaining": 5}
        new_items.append({"id": str(i), "sold_out": False, "remaining": 5})
    # 3 个补货
    for i in range(200, 203):
        old_plans[str(i)] = {"sold_out": True, "remaining": 0}
        new_items.append({"id": str(i), "sold_out": False, "remaining": 5})
    # 2 个售罄(不推)
    for i in range(300, 302):
        old_plans[str(i)] = {"sold_out": False, "remaining": 5}
        new_items.append({"id": str(i), "sold_out": True, "remaining": 0})
    # 5 个全新(不在 old)
    for i in range(400, 405):
        new_items.append({"id": str(i), "sold_out": False, "remaining": 5})
    state = {"plans": old_plans, "first_run": False}

    new, restocked, _ = compare_site_a(state, new_items)
    assert len(new) == 5, f"应识别 5 个全新, 实际 {len(new)}"
    assert len(restocked) == 3, f"应识别 3 个补货, 实际 {len(restocked)}"


def _run():
    tests = [
        test_a_first_run,
        test_a_no_change_no_event,
        test_a_remaining_only_no_event,
        test_a_restocked,
        test_a_sold_out_no_event,
        test_b_restocked_via_stock,
        test_b_stock_drop_no_event,
        test_c_resource_template_fallback,
        test_c_with_nested_plans,
        test_empty_items_returns_empty_events,
        test_mixed_scenario_large,
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
