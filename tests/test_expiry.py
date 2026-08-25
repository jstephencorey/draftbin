import time

from fastapi.testclient import TestClient

from draftbin.app import create_app
from tests.conftest import AUTH


def upload(client, ttl_seconds=None):
    body = {"markdown": "# Draft\n"}
    if ttl_seconds:
        body["ttl_seconds"] = ttl_seconds
    return client.post("/api/upload/markdown", json=body, headers=AUTH).json()["id"]


def advance(monkeypatch, seconds):
    later = time.time() + seconds
    monkeypatch.setattr(time, "time", lambda: later)


def test_expired_draft_is_not_served_before_any_sweep(client, monkeypatch):
    draft_id = upload(client, ttl_seconds=60)
    advance(monkeypatch, 61)
    assert client.get(f"/d/{draft_id}").status_code == 404


def test_expired_draft_is_hidden_from_the_listing(client, monkeypatch):
    upload(client, ttl_seconds=60)
    advance(monkeypatch, 61)
    assert client.get("/api/drafts", headers=AUTH).json()["drafts"] == []


def test_live_draft_survives_the_sweeper(client, app):
    draft_id = upload(client, ttl_seconds=3600)
    assert app.state.sweep_expired() == 0
    assert client.get(f"/d/{draft_id}").status_code == 200


def test_sweeper_deletes_the_stored_file(client, app, monkeypatch):
    draft_id = upload(client, ttl_seconds=60)
    stored = app.state.store.path_for(draft_id)
    assert stored.is_file()

    advance(monkeypatch, 61)
    assert app.state.sweep_expired() == 1
    assert not stored.is_file()


def test_sweeping_twice_is_harmless(client, app, monkeypatch):
    upload(client, ttl_seconds=60)
    advance(monkeypatch, 61)
    assert app.state.sweep_expired() == 1
    assert app.state.sweep_expired() == 0


def test_startup_deletes_a_file_whose_row_is_gone(client, app, config):
    """A crash between the row delete and the file delete would otherwise strand it forever."""
    stranded = app.state.store.path_for("aaaaaaaaaaaaaaaaaaaaaa")
    stranded.write_text("<p>no row points at me</p>", encoding="utf-8")

    with TestClient(create_app(config)):
        pass

    assert not stranded.is_file()


def test_startup_keeps_files_that_still_have_a_row(client, app, config):
    draft_id = upload(client, ttl_seconds=3600)

    with TestClient(create_app(config)) as restarted:
        assert restarted.get(f"/d/{draft_id}").status_code == 200
