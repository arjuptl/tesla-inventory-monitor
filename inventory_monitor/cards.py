"""Parse only text rendered by a visible card; never infer VINs from hrefs."""
import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

BASE = "https://www.tesla.com/inventory/new/my"
VIN = re.compile(r"(?<![A-Z0-9])[A-HJ-NPR-Z0-9]{17}(?![A-Z0-9])")

@dataclass(frozen=True)
class Card:
    title: str
    trim: str | None
    price: str | None
    odometer: str | None
    href: str | None
    vin: str | None

    def to_dict(self):
        return asdict(self)

def detail_url(href):
    if not href:
        return None
    url = urlsplit(urljoin(BASE, href))
    if url.scheme != "https" or url.netloc != "www.tesla.com" or not url.path.startswith(("/my/order/", "/inventory/new/my/")):
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(url.query) if k.lower() != "zip"])
    return urlunsplit((url.scheme, url.netloc, url.path, query, ""))

def parse_card(text, href=None):
    text = " ".join(text.split())
    if re.search(r"\bdemo\b", text, re.I) or not re.search(r"\bModel Y\b", text, re.I):
        return None
    trim = next((v for v in ("Premium Rear-Wheel Drive", "Premium All-Wheel Drive") if v.lower() in text.lower()), None)
    price = re.search(r"\$[0-9,]+(?:\.[0-9]{2})?", text)
    miles = re.search(r"[0-9,]+\s*(?:miles|mi)\b", text, re.I)
    vin = VIN.search(text)
    return Card("Model Y", trim, price.group() if price else None,
                miles.group() if miles else None, detail_url(href), vin.group() if vin else None)

class FixtureParser(HTMLParser):
    """Tiny synthetic fixture adapter; production uses Playwright visible inner_text."""
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.hidden = 0
        self.parts = []
        self.href = None
        self.cards = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hide = "hidden" in attrs or attrs.get("aria-hidden") == "true" or tag in {"script", "style"}
        self.stack.append((tag, hide))
        self.hidden += hide
        if tag == "article" and not self.depth and not self.hidden:
            self.depth = len(self.stack)
            self.parts, self.href = [], None
        if self.depth and not self.hidden and tag == "a":
            self.href = detail_url(attrs.get("href")) or self.href

    def handle_data(self, data):
        if self.depth and not self.hidden:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if not self.stack:
            return
        if len(self.stack) == self.depth and tag == "article":
            card = parse_card(" ".join(self.parts), self.href)
            if card:
                self.cards.append(card)
            self.depth = 0
        _, hide = self.stack.pop()
        self.hidden -= hide

def parse_fixture(html):
    parser = FixtureParser()
    parser.feed(html)
    return parser.cards
