import copy
import json
from pathlib import Path
import pytest
from inventory_monitor.config import ConfigError, load_config

@pytest.fixture
def config_data():
    return json.loads(Path("config.example.json").read_text())

def test_valid(monkeypatch, config_data):
    monkeypatch.setenv("WATCH_CONFIG_JSON", json.dumps(config_data))
    config = load_config()
    assert len(config.watches) == 2
    assert config.watches[0].trim == "Premium Rear-Wheel Drive"
    assert "00000" in config.secrets

@pytest.mark.parametrize("field", ["id", "zip", "trim_code", "prefer_drivetrain", "payment", "condition", "search_within"])
def test_missing_field(monkeypatch, config_data, field):
    del config_data["watches"][0][field]
    monkeypatch.setenv("WATCH_CONFIG_JSON", json.dumps(config_data))
    with pytest.raises(ConfigError):
        load_config()

@pytest.mark.parametrize("field,value", [("zip", "abcde"), ("zip", "１２３４５"), ("zip", 0), ("zip", "0000"), ("trim_code", "unknown"), ("prefer_drivetrain", "AWD"), ("payment", "Lease"), ("condition", "used"), ("search_within", "Nearby"), ("id", "")])
def test_bad_values(monkeypatch, config_data, field, value):
    config_data["watches"][0][field] = value
    monkeypatch.setenv("WATCH_CONFIG_JSON", json.dumps(config_data))
    with pytest.raises(ConfigError) as caught:
        load_config()
    assert str(caught.value) == "Invalid or missing WATCH_CONFIG_JSON"

@pytest.mark.parametrize("raw", ["", "{", "[]", "null", '{}', '{"watches":[],"email":{"enabled":false}}'])
def test_bad_document(monkeypatch, raw):
    monkeypatch.setenv("WATCH_CONFIG_JSON", raw)
    with pytest.raises(ConfigError):
        load_config()

def test_missing_env(monkeypatch):
    monkeypatch.delenv("WATCH_CONFIG_JSON", raising=False)
    with pytest.raises(ConfigError):
        load_config()

@pytest.mark.parametrize("change", ["duplicate", "email", "extra"])
def test_strict_schema(monkeypatch, config_data, change):
    if change == "duplicate":
        config_data["watches"].append(copy.deepcopy(config_data["watches"][0]))
    elif change == "email":
        config_data["email"]["enabled"] = True
    else:
        config_data["extra"] = "untrusted"
    monkeypatch.setenv("WATCH_CONFIG_JSON", json.dumps(config_data))
    with pytest.raises(ConfigError):
        load_config()
