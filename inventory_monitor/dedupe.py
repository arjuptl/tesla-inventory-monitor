"""Optional private dedupe. Never commit generated data."""
import hashlib
import json
from pathlib import Path

class Dedupe:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.seen = set(json.loads(path.read_text())) if path and path.exists() else set()

    def event(self, card):
        identity = card.vin or card.href
        if not identity:
            return None  # No stable identity: do not invent one from price/title.
        key = hashlib.sha256(identity.encode()).hexdigest()
        if key in self.seen:
            return None
        self.seen.add(key)
        return "existing_match"

    def save(self):
        if self.path:
            private_write(self.path, sorted(self.seen))
        # TODO: Durable cross-run scheduled-run state is outside this public package.

def private_write(path, value):
    import os
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w") as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(value, handle)
