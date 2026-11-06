import pytest
from inventory_monitor.redact import redact

@pytest.mark.parametrize("text", ["00000", "watch-a at 00000", "failure: https://example.invalid/?zip=00000&x=1", "Vehicle Registration ZIP: 00000", "https://example.invalid/?ZIP%3D99999", "https://example.invalid/?zip%253D99999"])
def test_secrets(text):
    output = redact(text, ("00000", "99999", "watch-a"))
    assert all(secret not in output for secret in ("00000", "99999", "watch-a"))

def test_unknown_zip_query():
    assert redact("https://example.invalid/?zip=fictional&x=1") == "https://example.invalid/?x=1"

def test_registration_value_without_config():
    assert redact("Vehicle Registration ZIP: 99999") == "Vehicle Registration ZIP: [REDACTED]"
