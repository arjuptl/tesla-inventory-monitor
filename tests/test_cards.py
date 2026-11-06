from pathlib import Path
import pytest
from inventory_monitor.cards import parse_card, parse_fixture, detail_url
from inventory_monitor.browser_ui import eligibility

def test_synthetic_html():
    cards = parse_fixture(Path("tests/fixtures/cards.html").read_text())
    assert len(cards) == 2
    assert cards[0].price == "$12,345"
    assert cards[0].odometer == "10 miles"
    assert cards[0].vin == "TESTFAKE123456789"  # Deliberately fictional.
    assert cards[1].trim == "Premium All-Wheel Drive"

def test_full_visible_fake_vin():
    assert parse_card("Model Y VIN: TESTFAKE123456789").vin == "TESTFAKE123456789"

def test_never_infer_vin_from_link():
    assert parse_card("Model Y", "/my/order/TESTFAKE123456789").vin is None

@pytest.mark.parametrize("text", ["Model Y demo", "Model Y INVENTORY DEMO", "Model 3"])
def test_excluded(text):
    assert parse_card(text) is None

@pytest.mark.parametrize("href", ["https://example.invalid/my/order/fake", "javascript:void(0)", "//example.invalid/my/order/fake", "/unsupported", "https://www.tesla.com:443/my/order/fake"])
def test_unsafe_detail(href):
    assert detail_url(href) is None

def test_detail_strips_zip():
    assert detail_url("/my/order/fake?zip=00000&color=test") == "https://www.tesla.com/my/order/fake?color=test"

@pytest.mark.parametrize("text,expected", [("Available for registration in ZIP 00000", True), ("Eligible for registration ZIP: 00000", True), ("Not available for registration ZIP 00000", False), ("Available for registration ZIP 99999", False), ("Available now", False), ("Available for registration ZIP 00000 but cannot deliver", False)])
def test_eligibility(text, expected):
    assert eligibility(text, "00000") is expected
