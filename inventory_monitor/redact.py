"""Defense in depth; public summaries use a fixed allowlist instead of raw errors."""
import re
from urllib.parse import unquote, urlsplit, urlunsplit, parse_qsl, urlencode

def redact(value, secrets=()):
    text = str(value)
    # Decode repeated percent encoding before removing URL query values.
    for _ in range(3):
        decoded = unquote(text)
        if decoded == text:
            break
        text = decoded
    def clean_url(match):
        try:
            url = urlsplit(match.group())
            query = urlencode([(k, v) for k, v in parse_qsl(url.query) if k.lower() != "zip"])
            return urlunsplit((url.scheme, url.netloc, url.path, query, url.fragment))
        except ValueError:
            return "[REDACTED URL]"
    text = re.sub(r"https?://[^\s\"'<>]+", clean_url, text, flags=re.I)
    # Also handle query fragments in exception messages without a complete URL.
    text = re.sub(r"(?i)([?&]|&amp;)zip=[^&#\s\"'<>]*", "", text)
    text = re.sub(r"(?i)(vehicle registration zip[\s:='\"<>-]*)([0-9]+)", r"\1[REDACTED]", text)
    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text
