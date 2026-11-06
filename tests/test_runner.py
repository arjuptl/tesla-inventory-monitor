import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from inventory_monitor.browser_ui import Result
from inventory_monitor.cards import parse_card
from inventory_monitor.config import load_config
from inventory_monitor.dedupe import Dedupe
from inventory_monitor.runner import execute, main, private_directory

@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv("WATCH_CONFIG_JSON", Path("config.example.json").read_text())
    return load_config()

def test_block_latches_and_stops(config, tmp_path):
    calls = []
    def run(_, watch):
        calls.append(watch)
        return Result("BLOCKED")
    first = execute(config, tmp_path, run, None)
    assert len(calls) == 1
    assert [row["status"] for row in first["watches"]] == ["BLOCKED", "BLOCKED_LATCHED"]
    assert not first["ok"]
    execute(config, tmp_path, run, None)
    assert len(calls) == 1

def test_public_summary_has_no_details(config, tmp_path):
    card = parse_card("Model Y Premium Rear-Wheel Drive $12,345 VIN TESTFAKE123456789", "/my/order/fictional")
    result = execute(config, tmp_path, lambda *_: Result("LOADED_WITH_CARDS", 2, [card]), None)
    encoded = json.dumps(result)
    for secret in (*config.secrets, card.vin, card.price, card.href):
        assert secret not in encoded
    assert result["ok"]
    assert "existing_match" in (tmp_path / "results.json").read_text()
    assert (tmp_path / "results.json").stat().st_mode & 0o777 == 0o600

def test_raw_exception_not_emitted(config, tmp_path):
    def run(*_):
        raise RuntimeError("secret 00000 watch-a")
    result = execute(config, tmp_path, run, None)
    assert "00000" not in json.dumps(result)
    assert all(row["status"] == "ERROR" for row in result["watches"])

def test_invalid_config_stdout_only(monkeypatch, capsys):
    monkeypatch.setenv("WATCH_CONFIG_JSON", "secret 00000")
    assert main([]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)["note"] == "invalid_configuration"
    assert captured.err == ""

def test_private_path_rejects_repo(monkeypatch):
    monkeypatch.setenv("RUN_PRIVATE_DIR", str(Path.cwd() / "private-test"))
    with pytest.raises(ValueError):
        private_directory()

def test_private_path_rejects_symlink(monkeypatch, tmp_path):
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    monkeypatch.setenv("RUN_PRIVATE_DIR", str(link))
    with pytest.raises(ValueError):
        private_directory()

def test_dedupe_persists(tmp_path):
    card = parse_card("Model Y", "/my/order/fictional")
    path = tmp_path / "dedupe.json"
    dedupe = Dedupe(path)
    assert dedupe.event(card) == "existing_match"
    assert dedupe.event(card) is None
    dedupe.save()
    assert Dedupe(path).event(card) is None
    assert dedupe.event(parse_card("Model Y")) is None

class FakeLocator:
    def __init__(self, text="", count=0, texts=()):
        self.text, self.total, self.texts = text, count, texts

    def inner_text(self, **kwargs):
        return self.text

    def count(self):
        return self.total

    def filter(self, **kwargs):
        return self

    def all_inner_texts(self):
        return self.texts

class FakePage:
    def __init__(self, text, cards=(), busy=False):
        self.text, self.cards, self.busy = text, cards, busy
        self.clock = 0

    def locator(self, selector):
        from inventory_monitor.browser_ui import CARDS
        if selector == "body":
            return FakeLocator(text=self.text)
        if selector == CARDS:
            return FakeLocator(count=len(self.cards), texts=self.cards)
        if "aria-busy" in selector:
            return FakeLocator(count=int(self.busy))
        return FakeLocator()

    def wait_for_timeout(self, milliseconds):
        self.clock += milliseconds / 1000

@pytest.mark.parametrize("text,cards,busy,expected", [
    ("No vehicles available", (), False, "LOADED_EMPTY"),
    ("10 vehicles", (), False, "TIMEOUT"),
    ("Loading", (), False, "TIMEOUT"),
    ("No vehicles available", (), True, "TIMEOUT"),
    ("Model Y", ("Model Y Premium Rear-Wheel Drive",), False, "LOADED_WITH_CARDS"),
])
def test_readiness_states(monkeypatch, text, cards, busy, expected):
    from inventory_monitor import browser_ui
    page = FakePage(text, cards, busy)
    monkeypatch.setattr(browser_ui.time, "monotonic", lambda: page.clock)
    assert browser_ui.readiness(page, seconds=3) == expected

@pytest.mark.parametrize("text", ["Access denied. No vehicles available", "Verify you are human", "403 Forbidden"])
def test_block_never_empty(text):
    from inventory_monitor.browser_ui import Blocked, readiness
    with pytest.raises(Blocked):
        readiness(FakePage(text), seconds=1)

def test_navigation_403_latches():
    from inventory_monitor.browser_ui import Blocked, navigate
    page = SimpleNamespace(goto=lambda *args, **kwargs: SimpleNamespace(status=403))
    with pytest.raises(Blocked):
        navigate(page, "https://example.invalid/")


def test_private_diagnostics_and_coarse_fields(config, tmp_path):
    from datetime import datetime
    result = Result("BLOCKED", stage="navigate", reason="HTTP_403",
                    http_status=403, elapsed_ms=42)
    public = execute(config, tmp_path, lambda *_: result, None)
    path = tmp_path / "diagnostics.json"
    rows = json.loads(path.read_text())
    assert path.stat().st_mode & 0o777 == 0o600
    assert len(rows) == len(config.watches)
    for row, summary in zip(rows, public["watches"]):
        assert datetime.fromisoformat(row.pop("timestamp")).tzinfo is not None
        assert row == summary
    assert rows[0]["stage"] == "navigate"
    assert rows[0]["reason"] == "HTTP_403"
    assert rows[0]["http_status"] == 403
    assert rows[0]["elapsed_ms"] == 42
    assert rows[1]["status"] == "BLOCKED_LATCHED"
    assert rows[1]["stage"] is None
    assert all(secret not in path.read_text() for secret in config.secrets)


def test_main_final_json_after_browser_noise(config, tmp_path, monkeypatch, capfd):
    import os
    from unittest.mock import MagicMock
    from inventory_monitor import browser_ui
    monkeypatch.setattr("inventory_monitor.runner.private_directory", lambda: tmp_path)
    monkeypatch.setattr("playwright.sync_api.sync_playwright", MagicMock())
    def run(*_):
        os.write(1, b"private browser output\n")
        os.write(2, b"private browser error\n")
        return Result("BLOCKED", stage="readiness", reason="BODY_TEXT_SIGNAL",
                      http_status=200, elapsed_ms=9)
    monkeypatch.setattr(browser_ui, "run_watch", run)
    assert main([]) == 1
    captured = capfd.readouterr()
    summary = json.loads(captured.out)
    assert captured.err == ""
    assert "private browser" not in captured.out
    assert summary["watches"][0]["reason"] == "BODY_TEXT_SIGNAL"
    assert summary["watches"][0]["stage"] == "readiness"
    assert summary["watches"][0]["http_status"] == 200
    assert (tmp_path / "blocked.json").exists()
    assert main([]) == 1
    assert json.loads(capfd.readouterr().out)["watches"][0]["status"] == "BLOCKED_LATCHED"
    assert main(["--resume-blocked"]) == 1
    assert json.loads(capfd.readouterr().out)["watches"][0]["status"] == "BLOCKED"
