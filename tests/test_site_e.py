#!/usr/bin/env python3
"""Tests for site-e pool rules + price parsing + USD numeric compare.

site-e 是 czl.net 公开 API 适配器 (commit 35ffe16), 核心逻辑:
- _parse_ram_gb_e:     解析 RAM 字符串到 GB (float)
- _parse_usd_year_e:   解析价格字符串到 USD/年 (含币种换算 + 周期换算)
- _site_e_pool_match:  池规则匹配 (池1 / 池2 / None)
- _site_e_is_vps:      排除 DEDI / 独立服务器
- compare_site_e 内:   USD 数字价格比较 + 1% 容忍 (避免币种换算/格式化噪音)

跑测试: python3 tests/test_site_e.py
"""

import importlib.util
import sys
from pathlib import Path

# Load monitor.py as module (避免污染 sys.path / 副作用)
MONITOR_PATH = Path(__file__).parent.parent / "monitor.py"
spec = importlib.util.spec_from_file_location("monitor", MONITOR_PATH)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


# ============================================================
# _parse_ram_gb_e
# ============================================================

def test_parse_ram_gb_e_basic():
    """基本 RAM 解析 (GB / MB / 空格 / 大小写)"""
    assert monitor._parse_ram_gb_e("1GB") == 1.0
    assert monitor._parse_ram_gb_e("2 GB") == 2.0
    assert monitor._parse_ram_gb_e("1024MB") == 1.0
    assert monitor._parse_ram_gb_e("2048 MB") == 2.0
    assert monitor._parse_ram_gb_e("512M") == 0.5
    assert monitor._parse_ram_gb_e("1.5 GB") == 1.5
    assert monitor._parse_ram_gb_e("8 gb") == 8.0


def test_parse_ram_gb_e_edge():
    """边界 + 异常 (空 / None / 非法字符串)"""
    assert monitor._parse_ram_gb_e("") == 0
    assert monitor._parse_ram_gb_e(None) == 0
    assert monitor._parse_ram_gb_e("invalid") == 0
    assert monitor._parse_ram_gb_e("VPS") == 0


# ============================================================
# _parse_usd_year_e
# ============================================================

def test_parse_usd_year_usd():
    """USD 价格解析"""
    assert abs(monitor._parse_usd_year_e("$10/年") - 10.0) < 0.01
    assert abs(monitor._parse_usd_year_e("$5.99/年") - 5.99) < 0.01
    assert abs(monitor._parse_usd_year_e("$25 /年") - 25.0) < 0.01  # 空格容忍


def test_parse_usd_year_cny():
    """人民币换算 (1 CNY = 0.139 USD)"""
    # ¥38/年 ≈ 38 * 0.139 = 5.282
    assert abs(monitor._parse_usd_year_e("¥38/年") - 5.282) < 0.01
    # ￥7/月 → 7 * 0.139 * 12 = 11.676
    assert abs(monitor._parse_usd_year_e("￥7/月") - 11.676) < 0.01
    # 38元/年 (无 ¥ 符号, 用"元"匹配)
    assert abs(monitor._parse_usd_year_e("38元/年") - 5.282) < 0.01


def test_parse_usd_year_eur():
    """欧元换算 + 月→年 周期"""
    # €4.10/月 × 12 × 1.08 = 53.136
    assert abs(monitor._parse_usd_year_e("€4.10/月") - 53.136) < 0.5


def test_parse_usd_year_edge():
    """边界 + 异常 (空 / 非法 / 无周期)"""
    assert monitor._parse_usd_year_e("") == 9999
    assert monitor._parse_usd_year_e("invalid") == 9999
    assert monitor._parse_usd_year_e("$10") == 10.0  # 无周期默认按 USD 不变


# ============================================================
# _site_e_pool_match
# ============================================================

def test_pool_match_pool1():
    """池 1: 廉价低规格 (RAM 0.4-1.1GB + ≤$9/年)"""
    assert monitor._site_e_pool_match(0.5, 5.0) == "池1(廉价)"
    assert monitor._site_e_pool_match(1.0, 9.0) == "池1(廉价)"
    assert monitor._site_e_pool_match(0.8, 7.5) == "池1(廉价)"
    assert monitor._site_e_pool_match(0.4, 0.01) == "池1(廉价)"  # 边界


def test_pool_match_pool2():
    """池 2: 主力推荐 (RAM 2-16GB + $10-20/年)"""
    assert monitor._site_e_pool_match(2.0, 10.0) == "池2(主力)"
    assert monitor._site_e_pool_match(4.0, 17.0) == "池2(主力)"
    assert monitor._site_e_pool_match(16.0, 20.0) == "池2(主力)"
    assert monitor._site_e_pool_match(8.0, 15.0) == "池2(主力)"


def test_pool_match_none():
    """不在池内 (RAM 不匹配 / 价格超界 / 太小太大)"""
    assert monitor._site_e_pool_match(1.5, 9.0) is None  # RAM 1.5 不在池 1 也不在池 2
    assert monitor._site_e_pool_match(2.0, 25.0) is None  # 超价
    assert monitor._site_e_pool_match(32.0, 15.0) is None  # RAM > 16
    assert monitor._site_e_pool_match(0.3, 5.0) is None  # RAM < 0.4
    assert monitor._site_e_pool_match(2.0, 5.0) is None  # RAM 2 但价 < $10


# ============================================================
# USD 数字比较 (compare_site_e 内的逻辑)
# ============================================================

def test_compare_price_drop_real():
    """真降价 ≥1% 触发"""
    prev_yu = monitor._parse_usd_year_e("$14.99/年")
    cur_yu = monitor._parse_usd_year_e("$13.99/年")
    # 6.6% 下降 → 触发
    assert cur_yu < prev_yu * 0.99


def test_compare_price_no_change():
    """币种不同但 USD 等价 → 不触发 (避免币种换算噪音)"""
    # $10/年 vs ¥72/年 (≈ $10, 因为 1 CNY = 0.139 USD → 72 * 0.139 ≈ 10.0)
    prev_yu = monitor._parse_usd_year_e("$10/年")
    cur_yu = monitor._parse_usd_year_e("¥72/年")
    assert abs(prev_yu - cur_yu) < 0.5  # 接近 (汇率换算后近似)
    # 不应该触发降价 (cur_yu ≈ prev_yu, cur_yu > prev_yu * 0.99)
    assert not (cur_yu < prev_yu * 0.99)


def test_compare_price_jitter_tolerated():
    """<1% 抖动不触发 (容忍汇率/舍入)"""
    # $10 → $9.95 = 0.5% 下降 (在 1% 容忍内)
    prev_yu = monitor._parse_usd_year_e("$10/年")
    cur_yu = monitor._parse_usd_year_e("$9.95/年")
    assert not (cur_yu < prev_yu * 0.99)


# ============================================================
# _site_e_is_vps (排除 DEDI)
# ============================================================

def test_is_vps_normal():
    """普通 VPS (KVM / SSD / RAM 标识都不触发)"""
    assert monitor._site_e_is_vps({"title": "1GB KVM VPS", "disk": "20GB SSD"})
    assert monitor._site_e_is_vps({"title": "Hashtag-26-SSD-VPS", "disk": "20GB"})
    assert monitor._site_e_is_vps({"title": "2GB Black Friday", "disk": "25GB"})


def test_is_vps_excludes_dedi():
    """排除独立服务器 (英文/拼音/中文)"""
    assert not monitor._site_e_is_vps({"title": "DUAL Intel Xeon Dedicated", "disk": "1TB"})
    assert not monitor._site_e_is_vps({"title": "DEDI - AMD EPYC", "disk": ""})
    assert not monitor._site_e_is_vps({"title": "独立服务器 - 32GB", "disk": "1TB"})
    assert not monitor._site_e_is_vps({"title": "独立服", "disk": ""})


# ============================================================
# Main
# ============================================================

def _run_all():
    """跑所有 test_* 函数, 打印结果"""
    test_funcs = [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = failed = 0
    failures = []
    for name, fn in test_funcs:
        try:
            fn()
            passed += 1
            print(f"✅ {name}")
        except AssertionError as e:
            failed += 1
            failures.append((name, f"AssertionError: {e}"))
            print(f"❌ {name}: {e}")
        except Exception as e:
            failed += 1
            failures.append((name, f"{type(e).__name__}: {e}"))
            print(f"⚠️ {name}: {type(e).__name__}: {e}")
    print(f"\n{'='*50}")
    print(f"📊 {passed} passed, {failed} failed (total {len(test_funcs)})")
    if failures:
        print("\n❌ Failures:")
        for name, err in failures:
            print(f"  - {name}: {err}")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
