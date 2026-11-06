"""Synthetic DOM stubs and mocks only; no live inventory DOM was available."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from inventory_monitor import browser_ui as ui


def _page_with_body_text(text: str, *, visible_iframe: bool = False):
    """Stub page: body.inner_text returns only the provided visible text."""
    page = Mock()
    page.locator.side_effect = lambda sel, **kwargs: _locator(sel, text, visible_iframe)


def _locator(sel, text, visible_iframe):
    loc = Mock()
    if sel == "body":
        loc.inner_text.return_value = text
        return loc
    if "iframe" in sel:
        loc.count.return_value = 1 if visible_iframe else 0
        return loc
    loc.count.return_value = 0
    loc.inner_text.return_value = ""
    return loc


def test_hidden_challenge_content():
    # Playwright-visible text would exclude template/script/hidden nodes.
    # Visible body copy has no challenge words.
    page = Mock()
    page.locator.side_effect = lambda sel, **kw: _locator(sel, "New Inventory\nNo vehicles available", False)
    ui.check_block(page)  # must not raise


def test_hidden_fixture_documents_non_visible_strings():
    html = Path("tests/fixtures/hidden_captcha.html").read_text()
    assert "captcha" in html.lower()
    assert "<template>" in html
    assert 'hidden' in html or "display:none" in html


def test_visible_challenge_text():
    page = Mock()
    page.locator.side_effect = lambda sel, **kw: _locator(sel, "Please verify that you are human", False)
    with pytest.raises(ui.Blocked) as caught:
        ui.check_block(page)
    assert caught.value.reason == "BODY_TEXT_SIGNAL"


def test_visible_challenge_iframe():
    page = Mock()
    page.locator.side_effect = lambda sel, **kw: _locator(sel, "Inventory", True)
    with pytest.raises(ui.Blocked) as caught:
        ui.check_block(page)
    assert caught.value.reason == "CHALLENGE_IFRAME"


@pytest.mark.parametrize("status,reason", [(403, "HTTP_403"), (429, "HTTP_429")])
def test_navigation_status(status, reason):
    page = SimpleNamespace(goto=Mock(return_value=SimpleNamespace(status=status)))
    with pytest.raises(ui.Blocked) as caught:
        ui.navigate(page, "https://example.invalid/")
    assert caught.value.reason == reason
    assert caught.value.http_status == status


def harness(monkeypatch):
    page = Mock()
    context = Mock()
    context.new_page.return_value = page
    playwright = Mock()
    playwright.chromium.launch_persistent_context.return_value = context
    monkeypatch.setattr(ui, "check_block", Mock())
    monkeypatch.setattr(ui, "navigate", Mock(return_value=200))
    return playwright, context, page


def test_success_stages(monkeypatch):
    playwright, context, page = harness(monkeypatch)
    stages = []

    def configure(page, watch, record_stage):
        def record(stage):
            stages.append(stage)
            record_stage(stage)
        original_configure(page, watch, record)

    original_configure = ui.configure
    monkeypatch.setattr(ui, "configure", configure)
    monkeypatch.setattr(ui, "choose", Mock())
    monkeypatch.setattr(ui, "selected", lambda page, name: name != "Premium All-Wheel Drive")
    control = page.get_by_role.return_value
    control.count.return_value = 1
    control.is_visible.return_value = True
    control.is_checked.return_value = False
    control.nth.return_value.is_visible.return_value = True
    dialog = control.filter.return_value
    dialog.get_by_label.return_value.input_value.return_value = "00000"
    dialog.get_by_label.return_value.count.return_value = 0
    dialog.get_by_role.return_value.count.return_value = 1
    monkeypatch.setattr(ui, "readiness", lambda page: "LOADED_EMPTY")
    watch = SimpleNamespace(zip="00000", trim="Premium Rear-Wheel Drive",
                            prefer_drivetrain="RWD", search_within="All Deliverable")
    result = ui.run_watch(playwright, watch)
    assert stages == ["configure_location", "configure_filters"]
    assert result.status == "LOADED_EMPTY"
    assert result.stage == "readiness"
    assert result.http_status == 200
    assert result.elapsed_ms >= 0
    assert playwright.chromium.launch_persistent_context.call_args.kwargs["headless"] is True
    context.close.assert_called_once()


@pytest.mark.parametrize("stage", ["navigate", "check_block_after_nav", "configure_location",
                                  "configure_filters", "readiness", "parse_cards", "detail_eligibility"])
def test_block_stage_and_stop(monkeypatch, stage):
    playwright, context, page = harness(monkeypatch)
    block = ui.Blocked(ui.BlockReason.HTTP_429, 429)
    def configure(page, watch, record):
        record("configure_location")
        if stage == "configure_location":
            raise block
        record("configure_filters")
        if stage == "configure_filters":
            raise block
    monkeypatch.setattr(ui, "configure", configure)
    monkeypatch.setattr(ui, "readiness", Mock(return_value="LOADED_WITH_CARDS"))
    monkeypatch.setattr(ui, "selected", lambda *_: True)
    if stage == "navigate":
        ui.navigate.side_effect = block
    elif stage == "check_block_after_nav":
        ui.check_block.side_effect = block
    elif stage == "readiness":
        ui.readiness.side_effect = block
    elif stage == "parse_cards":
        page.locator.side_effect = block
    elif stage == "detail_eligibility":
        nodes = page.locator.return_value.filter.return_value
        nodes.count.return_value = 1
        nodes.nth.return_value.locator.return_value.count.return_value = 0
        monkeypatch.setattr(ui, "parse_card", lambda *_: SimpleNamespace(trim="trim", href="https://example.invalid/"))
        ui.navigate.side_effect = [200, block]
    result = ui.run_watch(playwright, SimpleNamespace(trim="trim"))
    assert (result.status, result.stage, result.reason, result.http_status) == ("BLOCKED", stage, "HTTP_429", 429)
    assert result.card_count == 0 and result.matches == []
    assert result.elapsed_ms >= 0
    context.close.assert_called_once()


def test_unverified_stage(monkeypatch):
    playwright, _, _ = harness(monkeypatch)
    def configure(page, watch, record):
        record("configure_location")
        raise ui.Unverified
    monkeypatch.setattr(ui, "configure", configure)
    result = ui.run_watch(playwright, None)
    assert (result.status, result.stage) == ("UI_UNVERIFIED", "configure_location")


def test_launch_failure(monkeypatch):
    playwright, _, _ = harness(monkeypatch)
    playwright.chromium.launch_persistent_context.side_effect = RuntimeError("private")
    result = ui.run_watch(playwright, None)
    assert (result.status, result.stage) == ("ERROR", "launch")
