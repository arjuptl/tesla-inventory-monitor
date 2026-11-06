"""Scan distributable source files for prohibited personal identifiers."""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIR_NAMES = {".venv", ".git", ".pytest_cache", "__pycache__", ".tmp", "node_modules"}
# Encoded so the markers themselves are less likely to appear as plain text in reviews.
MARKERS = [
    base64.b64decode(item).lower()
    for item in [
        "NzUwMDI=",  # personal zip A
        "NjA2NjE=",  # personal zip B
        "cHJhdGlr",
        "bmlsYXk=",
        "cHJhdGlrMTIxNg==",
        "bmx5cGF0ZWw=",
    ]
]
# Full personal mailbox local-parts only (not every @gmail.com in the universe).
EMAIL_MARKERS = [
    base64.b64decode(item).lower()
    for item in [
        "cHJhdGlrMTIxNkBnbWFpbC5jb20=",
        "bmx5cGF0ZWxAeWFob28uY29t",
    ]
]
ALLOWED_ZIPS = {b"00000", b"99999"}


def _should_skip(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def scan(root: Path) -> list[str]:
    failures: list[str] = []
    for path in root.rglob("*"):
        if _should_skip(path.relative_to(root)):
            continue
        if path.is_symlink():
            failures.append("symlink")
            continue
        if not path.is_file():
            continue
        data = path.read_bytes().lower()
        rel = path.relative_to(root).as_posix().lower().encode()
        if any(m in data or m in rel for m in MARKERS):
            failures.append("prohibited_identifier")
        if any(m in data for m in EMAIL_MARKERS):
            failures.append("prohibited_email")
        if re.search(rb"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", data):
            # Allow no email addresses at all in the public tree.
            failures.append("contact_address")
        for match in re.finditer(rb"(?:zip[\"'\s:=]+)([0-9]{5})(?![0-9])", data):
            if match.group(1) not in ALLOWED_ZIPS:
                failures.append("non_placeholder_zip")
        if re.search(rb"zip=(?!00000|99999)[0-9]{5}", data):
            failures.append("zip_query_param")
    return failures


if __name__ == "__main__":
    errors = scan(ROOT)
    print("Sanitization FAIL" if errors else "Sanitization PASS")
    # Do not print offending paths/content (may be sensitive).
    sys.exit(1 if errors else 0)
