from vpsmon.cli import run_once
from vpsmon.models import Event, EventType
from vpsmon.notifiers import telegram
from vpsmon.notifiers.telegram import format_offer, render_events, render_summary, send_telegram_messages, split_blocks
from vpsmon.rules.filtering import offer_allowed
from vpsmon.rules.parsing import parse_cpu_cores, parse_ram_gb, parse_usd_year
from vpsmon.sources.czl import normalize as normalize_czl
from vpsmon.sources.dujiaojing import normalize as normalize_dujiaojing


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
