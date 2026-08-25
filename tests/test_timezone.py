import dataclasses
import time

import pytest
from fastapi.testclient import TestClient

from draftbin.app import create_app
from draftbin.config import ConfigError, load_config
from tests.conftest import AUTH


@pytest.fixture
def denver_client(config):
    with TestClient(create_app(dataclasses.replace(config, timezone="America/Denver"))) as client:
        yield client


def test_expiry_is_shown_in_the_configured_zone(denver_client):
    draft = denver_client.post(
        "/api/upload/markdown", json={"markdown": "# Local\n"}, headers=AUTH
    ).json()

    view = denver_client.get(f"/d/{draft['id']}").text
    assert "UTC" not in view
    assert " MDT" in view or " MST" in view


def test_the_expired_page_uses_the_configured_zone(denver_client, monkeypatch):
    draft = denver_client.post(
        "/api/upload/markdown", json={"markdown": "# Local\n", "ttl_seconds": 60}, headers=AUTH
    ).json()

    later = time.time() + 61
    monkeypatch.setattr(time, "time", lambda: later)

    page = denver_client.get(f"/d/{draft['id']}").text
    assert " MDT" in page or " MST" in page


def test_the_api_keeps_reporting_utc(denver_client):
    """Machines want an unambiguous instant; publish.py converts for display itself."""
    draft = denver_client.post(
        "/api/upload/markdown", json={"markdown": "# Local\n"}, headers=AUTH
    ).json()

    assert draft["expires_at"].endswith("+00:00")


def test_the_default_zone_is_utc(client):
    draft = client.post("/api/upload/markdown", json={"markdown": "# Plain\n"}, headers=AUTH).json()
    assert "UTC" in client.get(f"/d/{draft['id']}").text


def test_an_unknown_zone_is_rejected_at_startup(monkeypatch):
    monkeypatch.setenv("DRAFTBIN_TOKEN", "a-token-long-enough-to-pass")
    monkeypatch.setenv("DRAFTBIN_TIMEZONE", "Middle/Earth")

    with pytest.raises(ConfigError, match="DRAFTBIN_TIMEZONE"):
        load_config()
