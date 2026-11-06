"""Environment-only configuration. Errors deliberately omit supplied values."""
import json
import os
import re
from dataclasses import dataclass

TRIMS = {"MY_PR_RWD": "Premium Rear-Wheel Drive", "MY_PR_AWD": "Premium All-Wheel Drive"}
FIELDS = {"id", "zip", "trim_code", "prefer_drivetrain", "payment", "condition", "search_within"}

class ConfigError(ValueError):
    pass

@dataclass(frozen=True)
class Watch:
    id: str
    zip: str
    trim_code: str
    prefer_drivetrain: str
    payment: str
    condition: str
    search_within: str

    @property
    def trim(self):
        return TRIMS[self.trim_code]

@dataclass(frozen=True)
class Config:
    watches: tuple[Watch, ...]

    @property
    def secrets(self):
        return tuple(value for w in self.watches for value in (w.zip, w.id))

def load_config():
    try:
        data = json.loads(os.environ["WATCH_CONFIG_JSON"])
        if not isinstance(data, dict) or set(data) != {"watches", "email"}:
            raise ValueError
        if data["email"] != {"enabled": False} or data["email"]["enabled"] is not False:
            raise ValueError
        rows = data["watches"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
            raise ValueError
        watches = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != FIELDS:
                raise ValueError
            if not all(isinstance(v, str) and v for v in row.values()):
                raise ValueError
            if not re.fullmatch(r"[0-9]{5}", row["zip"]):
                raise ValueError
            if row["trim_code"] not in TRIMS:
                raise ValueError
            expected = "RWD" if row["trim_code"] == "MY_PR_RWD" else "AWD"
            if (row["prefer_drivetrain"], row["payment"], row["condition"], row["search_within"]) != (expected, "Cash", "new", "All Deliverable"):
                raise ValueError
            if len(row["id"]) > 128 or row["id"] in {w.id for w in watches}:
                raise ValueError
            watches.append(Watch(**row))
        return Config(tuple(watches))
    except (KeyError, ValueError, TypeError):
        raise ConfigError("Invalid or missing WATCH_CONFIG_JSON") from None
