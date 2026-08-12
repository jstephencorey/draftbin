import time

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
