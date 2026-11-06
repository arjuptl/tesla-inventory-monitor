"""Tests must never open an Internet socket, including accidental site access."""
import socket
import pytest

@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Network is forbidden in offline tests")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
