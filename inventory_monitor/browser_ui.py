"""Visible UI only. Selectors are conservative and not live/cloud verified."""
import re
import time
from dataclasses import dataclass, field
from tempfile import TemporaryDirectory

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from .cards import BASE, parse_card

CARDS = "article.inventory-result, .inventory-results article, [data-testid='inventory-card'], .result.card"
BLOCK = re.compile(r"access denied|verify (?:that )?you are human|unusual traffic|captcha|security challenge|request blocked|403 forbidden", re.I)
EMPTY = re.compile(r"\bno (?:vehicles|results|inventory)(?: found| available| match)|\b0 vehicles\b", re.I)

class Blocked(Exception):
    pass

class Unverified(Exception):
    pass

@dataclass
class Result:
    status: str
    card_count: int = 0
    matches: list = field(default_factory=list)


def check_block(page):
    if BLOCK.search(page.locator("body").inner_text(timeout=2000)):
        raise Blocked
    if page.locator("iframe[title*='challenge' i]:visible, iframe[title*='captcha' i]:visible").count():
        raise Blocked


def navigate(page, url):
    response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
    # Only top-level navigation status; no network listeners or response-body access.
    if response and response.status in {403, 429}:
        raise Blocked
    check_block(page)


def choose(page, name):
    for role in ("checkbox", "radio"):
        control = page.get_by_role(role, name=name, exact=True)
        if control.count() == 1 and control.is_visible():
            control.check(timeout=5000)
            if not control.is_checked():
                raise Unverified
            return
    raise Unverified


def selected(page, name):
    for role in ("checkbox", "radio"):
        control = page.get_by_role(role, name=name, exact=True)
        if control.count() == 1 and control.is_visible() and control.is_checked():
            return True
    return False


def configure(page, watch):
    check_block(page)
    location = page.get_by_role("button", name=re.compile(r"location|delivery zip|registration zip", re.I))
    if location.count() != 1:
        raise Unverified
    location.click()
    dialog = page.get_by_role("dialog").filter(has=page.get_by_text(re.compile("Vehicle Registration ZIP", re.I)))
    dialog.wait_for(state="visible", timeout=5000)
    zip_input = dialog.get_by_label(re.compile("Vehicle Registration ZIP", re.I))
    zip_input.fill(watch.zip)
    within = dialog.get_by_label(re.compile("Search within", re.I))
    if within.count() == 1 and within.evaluate("el => el.tagName") == "SELECT":
        within.select_option(label=watch.search_within)
        if within.locator("option:checked").inner_text().strip() != watch.search_within:
            raise Unverified
    else:
        choose(dialog, watch.search_within)
    if zip_input.input_value() != watch.zip:
        raise Unverified
    apply = dialog.get_by_role("button", name=re.compile(r"^(apply|save|done|confirm)$", re.I))
    if apply.count() == 1:
        apply.click()
    else:
        zip_input.press("Enter")
    dialog.wait_for(state="hidden", timeout=5000)
    choose(page, "New")
    choose(page, "Cash")
    choose(page, watch.trim)
    # Ensure the mutually exclusive trim is not selected.
    other = "Premium All-Wheel Drive" if watch.prefer_drivetrain == "RWD" else "Premium Rear-Wheel Drive"
    checkbox = page.get_by_role("checkbox", name=other, exact=True)
    if checkbox.count() == 1 and checkbox.is_visible() and checkbox.is_checked():
        checkbox.uncheck()
    if selected(page, other) or not all(selected(page, name) for name in ("New", "Cash", watch.trim)):
        raise Unverified
    heading = page.get_by_role("heading", name=re.compile(r"Model Y|New Inventory", re.I))
    if not any(heading.nth(i).is_visible() for i in range(heading.count())):
        raise Unverified


def readiness(page, seconds=25):
    deadline = time.monotonic() + seconds
    previous = None
    stable_since = time.monotonic()
    while time.monotonic() < deadline:
        check_block(page)
        busy = page.locator("[aria-busy='true']:visible, [role='progressbar']:visible").count()
        cards = page.locator(CARDS).filter(visible=True)
        text = page.locator("body").inner_text(timeout=2000)
        candidate = None
        if not busy:
            if cards.count():
                candidate = ("LOADED_WITH_CARDS", tuple(cards.all_inner_texts()))
            elif EMPTY.search(text):
                candidate = ("LOADED_EMPTY", ())
        if candidate != previous:
            stable_since = time.monotonic()
            previous = candidate
        if candidate and time.monotonic() - stable_since >= 1.5:
            return candidate[0]
        page.wait_for_timeout(250)
    return "TIMEOUT"


def eligibility(text, zip_code):
    """Require explicit positive registration evidence for the configured ZIP."""
    if re.search(r"not available|unavailable|cannot be registered|not eligible|cannot deliver", text, re.I):
        return False
    positive = re.compile(r"(?:available|eligible) for (?:vehicle )?registration(?: in| at)?(?: zip)?\s*[:=-]?\s*" + re.escape(zip_code) + r"(?![0-9])", re.I)
    return bool(positive.search(text))


def run_watch(playwright, watch):
    # A fresh disposable profile per watch is stricter than per-run isolation.
    with TemporaryDirectory(prefix="inventory-monitor-profile-") as profile:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=profile, headless=True, accept_downloads=False,
        )
        context.set_default_timeout(5000)
        page = context.new_page()
        try:
            navigate(page, BASE)
            configure(page, watch)
            status = readiness(page)
            if status in {"LOADED_EMPTY", "LOADED_WITH_CARDS"}:
                if not all(selected(page, name) for name in ("New", "Cash", watch.trim)):
                    raise Unverified
            if status != "LOADED_WITH_CARDS":
                return Result(status)
            nodes = page.locator(CARDS).filter(visible=True)
            count = nodes.count()
            candidates = []
            for i in range(count):
                node = nodes.nth(i)
                links = node.locator("a[href]:visible")
                href = next((links.nth(j).get_attribute("href") for j in range(links.count())
                             if links.nth(j).get_attribute("href") and "/order/" in links.nth(j).get_attribute("href")), None)
                card = parse_card(node.inner_text(), href)
                if card and card.trim == watch.trim and card.href:
                    candidates.append(card)
            matches = []
            for card in candidates[:20]:
                navigate(page, card.href)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    check_block(page)
                    text = page.locator("body").inner_text()
                    if re.search(r"not available|unavailable|cannot be registered|not eligible|cannot deliver", text, re.I):
                        break
                    if re.search(r"\bdemo\b", text, re.I):
                        break
                    if eligibility(text, watch.zip):
                        matches.append(card)
                        break
                    page.wait_for_timeout(250)
            return Result("CANDIDATE_LIMIT" if len(candidates) > 20 else status, count, matches)
        except Blocked:
            return Result("BLOCKED")
        except Exception as error:
            try:
                check_block(page)
            except Blocked:
                return Result("BLOCKED")
            except Exception:
                pass
            if isinstance(error, PlaywrightTimeout):
                return Result("TIMEOUT")
            return Result("UI_UNVERIFIED" if isinstance(error, Unverified) else "ERROR")
        finally:
            context.close()
