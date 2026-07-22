import json
from pathlib import Path

from vpsmon.cli import run_once
from vpsmon.engine.diff import diff_offers
from vpsmon.models import Event, EventType, Money, VpsOffer
from vpsmon.notifiers import telegram
from vpsmon.notifiers.telegram import format_offer, render_events, render_summary, send_telegram_messages, split_blocks
from vpsmon.rules.filtering import offer_allowed
from vpsmon.rules.parsing import parse_cpu_cores, parse_ram_gb, parse_usd_year
from vpsmon.sources import czl, dujiaojing
from vpsmon.sources.czl import CzlSource, normalize as normalize_czl
from vpsmon.sources.dujiaojing import DujiaojingSource, normalize as normalize_dujiaojing
from vpsmon.storage.sqlite import StateStore

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text())


def test_parse_ram_units():
    assert parse_ram_gb("2GB RAM") == 2
    assert parse_ram_gb("2048MB RAM") == 2
    assert parse_ram_gb("512MB") == 0.5


def test_parse_price_periods():
    assert parse_usd_year("$10/年") == 10
    assert parse_usd_year("$2/月") == 24
    cny_year = parse_usd_year("38元/年")
    assert cny_year is not None
    assert round(cny_year, 3) == 5.282


def test_parse_cpu_units():
    assert parse_cpu_cores("1 Core") == 1
    assert parse_cpu_cores("2vCore") == 2


def test_split_blocks_under_limit():
    blocks = ["x" * 1000 for _ in range(10)]
    chunks = split_blocks("header", blocks, max_chars=2500)
    assert len(chunks) > 1
    assert all(len(chunk) <= 2500 + 16 for chunk in chunks)


def test_split_blocks_empty_header_has_no_leading_blank():
    assert split_blocks("", ["hello"], max_chars=100) == ["hello"]


def test_dujiaojing_normalize_and_filter():
    offer = normalize_dujiaojing(
        {
            "id": 123,
            "name": "特惠套餐",
            "machine_name": "HK CN2-GIA Node",
            "machine_region": "HK",
            "machine_region_id": "hk",
            "machine_id": "m1",
            "machine_description": "三网 CN2 GIA",
            "machine_vm_type": "KVM",
            "cpu": 2,
            "ram_mb": 2048,
            "disk_gb": 20,
            "bandwidth_mbps": 1000,
            "monthly_traffic_gb": 1024,
            "price_monthly": 0.2,
            "remaining": 3,
        },
        "https://example.test/deploy?plan_id={plan_id}&machine_id={machine_id}&region={region}",
    )
    assert offer.source == "dujiaojing"
    assert offer.price is not None
    assert round(offer.price.usd_year, 3) == 2.4
    assert offer.available is True
    assert offer.stock == 3
    assert "CN2" in offer.route
    assert offer_allowed(offer, {"price_max_usd_month": 0.3})


def test_format_offer_uses_text_link():
    offer = normalize_dujiaojing(
        {
            "id": 2,
            "name": "特惠",
            "machine_name": "HK Node",
            "machine_region": "HK",
            "machine_id": "m2",
            "cpu": 1,
            "ram_mb": 1024,
            "disk_gb": 10,
            "bandwidth_mbps": 100,
            "price_monthly": 0.1,
            "remaining": 1,
        },
        "https://example.test/deploy?plan_id={plan_id}&machine_id={machine_id}&region={region}",
    )
    text = format_offer(offer, {})
    assert '<a href="https://example.test/deploy?plan_id=2&amp;machine_id=m2&amp;region=HK">直达购买</a>' in text
    assert "🛍️ https://" not in text
    assert "📦 <b>特惠 · HK</b>" in text
    assert "🏷️ HK Node" in text
    assert "🟢 有货 ×1" in text
    assert text.index("💰") < text.index("🛍️") < text.index("🌐")


def test_format_offer_applies_same_template_to_czl():
    offer = normalize_czl(
        {
            "id": "czl-1",
            "title": "LET 1GB KVM VPS with a very very long title that should be compacted on mobile",
            "provider": "GreenCloud",
            "location": "Türkiye - Bursa Bulgaria - Sofia United States - Los Angeles",
            "cpu": "1 Core",
            "ram": "2GB RAM",
            "disk": "20GB SSD",
            "bandwidth": "400GB",
            "remark": "更新时间 , 2026-01-14T05:27:53.000+00:00 / 4837 / 去程软银",
            "price": "$39.99/年",
            "isAvailable": True,
        },
        "https://vps-monitor.czl.net/product/{item_id}",
    )
    text = format_offer(offer, {})
    assert "<b>LET 1GB KVM VPS" in text
    assert "with a very very long title that should be compacted" not in text
    assert "💻 1vCore / 2GB / 20GB SSD / 400GB" in text
    assert "💰 $39.99/年 · 🟢 有货" in text
    assert '<a href="https://vps-monitor.czl.net/product/czl-1">直达购买</a>' in text
    assert "更新时间" not in text
    assert " / / " not in text
    assert "#greencloud" in text


def test_format_offer_cleans_route_and_useless_tag():
    offer = normalize_dujiaojing(
        {
            "id": 3,
            "name": "短标签",
            "machine_name": "香港",
            "machine_region": "HK",
            "machine_description": "NQ: https://nodequality.example/r/abc 测试ip：1.1.1.1 移动快乐",
            "cpu": 1,
            "ram_mb": 1024,
            "disk_gb": 10,
            "bandwidth_mbps": 100,
            "price_monthly": 0.1,
            "remaining": 1,
        },
        "https://example.test/{plan_id}",
    )
    text = format_offer(offer, {})
    assert "https://nodequality" not in text
    assert "NQ:" not in text
    assert "测试ip：" not in text
    assert "#hk" not in text


def test_render_events_can_skip_unavailable_before_call():
    available = normalize_dujiaojing(
        {"id": 1, "name": "有货", "cpu": 1, "ram_mb": 1024, "disk_gb": 10, "price_monthly": 0.1, "remaining": 1},
        "https://example.test/{plan_id}",
    )
    soldout = normalize_dujiaojing(
        {"id": 2, "name": "无货", "cpu": 1, "ram_mb": 1024, "disk_gb": 10, "price_monthly": 0.1, "remaining": 0},
        "https://example.test/{plan_id}",
    )
    events = [Event(EventType.NEW, available), Event(EventType.NEW, soldout)]
    messages = render_events([event for event in events if event.offer.available], {})
    joined = "\n".join(messages)
    assert "有货" in joined
    assert "无货" not in joined


def test_render_summary():
    offer = normalize_dujiaojing(
        {
            "id": 1,
            "name": "特惠",
            "machine_name": "HK Node",
            "machine_region": "HK",
            "cpu": 1,
            "ram_mb": 1024,
            "disk_gb": 10,
            "bandwidth_mbps": 100,
            "price_monthly": 0.1,
            "remaining": 1,
        },
        "https://example.test/{plan_id}",
    )
    messages = render_summary([Event(EventType.NEW, offer)])
    assert len(messages) == 1
    assert "独角鲸云" in messages[0]
    assert "HK Node" in messages[0]



def _offer(
    offer_id="plan-1",
    *,
    source="czl",
    available=True,
    price_raw="$12/年",
    usd_year=12.0,
    stock=1,
):
    return VpsOffer(
        source=source,
        offer_id=offer_id,
        title="LowEnd KVM",
        provider="ExampleHost",
        location="Los Angeles",
        cpu_cores=1,
        ram_gb=1,
        disk="20GB SSD",
        bandwidth="1TB",
        route="4837 / CMI",
        price=Money(raw=price_raw, usd_year=usd_year),
        available=available,
        stock=stock,
        url=f"https://example.test/{offer_id}",
        raw={"id": offer_id},
    )


def test_diff_first_run_silent_seeds_state(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    try:
        events = diff_offers(store, [_offer()], first_run_silent=True)
        assert events == []
        assert store.count_source("czl") == 1
        saved = store.get("czl", "plan-1")
        assert saved is not None
        assert saved["available"] == 1
        assert saved["price_raw"] == "$12/年"
    finally:
        store.close()


def test_diff_first_run_can_emit_new_without_commit(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    try:
        events = diff_offers(store, [_offer()], first_run_silent=False, commit=False)
        assert [event.event_type for event in events] == [EventType.NEW]
        assert store.count_source("czl") == 0
    finally:
        store.close()


def test_diff_detects_restock_and_price_drop(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    try:
        store.upsert_many([_offer(available=False, price_raw="$20/年", usd_year=20.0, stock=0)])
        events = diff_offers(store, [_offer(available=True, price_raw="$10/年", usd_year=10.0, stock=2)])
        assert [event.event_type for event in events] == [EventType.RESTOCK, EventType.PRICE_DROP]
        assert events[1].old_price_raw == "$20/年"
        assert events[1].new_price_raw == "$10/年"
        saved = store.get("czl", "plan-1")
        assert saved["available"] == 1
        assert saved["stock"] == 2
        assert saved["usd_year"] == 10.0
    finally:
        store.close()


def test_state_store_records_events_with_payload(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    try:
        offer_id = "plan-2"
        events = [Event(EventType.NEW, _offer(offer_id))]
        store.record_events(events)
        row = store.conn.execute("SELECT * FROM events WHERE source=? AND offer_id=?", ("czl", offer_id)).fetchone()
        assert row is not None
        assert row["event_type"] == "new"
        assert row["title"] == "LowEnd KVM"
        assert row["url"] == "https://example.test/plan-2"
        assert '"id": "plan-2"' in row["payload_json"]
    finally:
        store.close()


def test_filter_pools_match_low_price_and_reject_missing_specs():
    rules = {
        "pools": [
            {"name": "tiny", "ram_min_gb": 0.5, "ram_max_gb": 1.0, "cpu_min_cores": 1, "usd_year_max": 10},
        ]
    }
    assert offer_allowed(_offer(usd_year=9.0, price_raw="$9/年"), rules)
    assert not offer_allowed(_offer(usd_year=12.0, price_raw="$12/年"), rules)
    no_cpu = _offer()
    no_cpu = VpsOffer(**{**no_cpu.__dict__, "cpu_cores": None})
    assert not offer_allowed(no_cpu, rules)


def test_czl_source_fetches_paginated_fixture(monkeypatch):
    calls = []

    class FakeResp:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout, headers=None):
        calls.append((url, params, timeout, headers))
        page = params["page"]
        if page == 1:
            return FakeResp(load_fixture("czl_page_1.json"))
        if page == 2:
            return FakeResp(load_fixture("czl_page_2.json"))
        return FakeResp({"data": {"items": []}})

    monkeypatch.setattr(czl.requests, "get", fake_get)
    source = CzlSource(
        {
            "api_url": "https://example.test/czl",
            "page_size": 2,
            "max_pages": 2,
            "max_workers": 1,
            "deploy_url": "https://example.test/buy/{item_id}",
        }
    )
    offers = source.fetch()

    assert [offer.offer_id for offer in offers] == [
        "44b274448870488e",
        "4c76534073bef9c5",
        "ec47efd414b6db99",
    ]
    assert calls == [
        (
            "https://example.test/czl",
            {"page": 1, "pageSize": 2},
            15,
            czl.DEFAULT_HEADERS,
        ),
        (
            "https://example.test/czl",
            {"page": 2, "pageSize": 2},
            15,
            czl.DEFAULT_HEADERS,
        ),
    ]
    assert offers[0].url == "https://example.test/buy/czl-fixture-1"
    assert offers[0].stock == 3
    assert offers[0].available is True
    assert offers[1].available is False
    assert offers[2].ram_gb == 2
    assert "CMI" in offers[2].route


def test_dujiaojing_source_fetches_fixture_until_total(monkeypatch):
    calls = []

    class FakeResp:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, headers, timeout):
        calls.append((url, params, headers, timeout))
        if params["page"] == 1:
            return FakeResp(load_fixture("dujiaojing_page_1.json"))
        if params["page"] == 2:
            return FakeResp(load_fixture("dujiaojing_page_2.json"))
        return FakeResp({"code": 0, "data": {"total": 3, "plans": []}})

    monkeypatch.setattr(dujiaojing.requests, "get", fake_get)
    source = DujiaojingSource(
        {
            "api_url": "https://example.test/plans",
            "token": "fixture-token",
            "deploy_url": "https://example.test/deploy?plan_id={plan_id}&machine_id={machine_id}&region={region}",
            "page_size": 2,
            "max_pages": 5,
        }
    )
    offers = source.fetch()

    assert [offer.offer_id for offer in offers] == ["101", "102", "103"]
    assert [call[1]["page"] for call in calls] == [1, 2]
    assert all(call[2] == {"Authorization": "Bearer fixture-token"} for call in calls)
    assert offers[0].price is not None
    assert round(offers[0].price.usd_year, 3) == 0.96
    assert offers[0].traffic == "500GB BW"
    assert offers[1].available is False
    assert offers[1].traffic == "不限流量"
    assert offers[2].cpu_cores == 2
    assert offers[2].ram_gb == 2
    assert offers[2].url == "https://example.test/deploy?plan_id=103&machine_id=us-1&region=us"


def test_dujiaojing_source_requires_token(monkeypatch):
    monkeypatch.delenv("MISSING_TOKEN", raising=False)
    source = DujiaojingSource({"api_url": "https://example.test/plans", "token_env": "MISSING_TOKEN"})
    try:
        source.fetch()
    except RuntimeError as exc:
        assert "token missing" in str(exc)
    else:
        raise AssertionError("expected missing token error")


def test_send_telegram_messages_uses_env(monkeypatch):
    calls = []

    class FakeResp:
        def json(self):
            return {"ok": True}

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        return FakeResp()

    monkeypatch.setenv("TG_TOKEN", "token")
    monkeypatch.setenv("TG_CHATS", "1,2")
    monkeypatch.setattr(telegram.requests, "post", fake_post)
    sent = send_telegram_messages(["hello"], {"bot_token_env": "TG_TOKEN", "chat_ids_env": "TG_CHATS"})
    assert sent == 2
    assert calls[0][1]["parse_mode"] == "HTML"
