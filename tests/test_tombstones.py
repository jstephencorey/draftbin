import time

from tests.conftest import AUTH


def publish(client, ttl_seconds=60):
    return client.post(
        "/api/upload/markdown", json={"markdown": "# Ephemeral\n", "ttl_seconds": ttl_seconds},
        headers=AUTH,
    ).json()["id"]


def advance(monkeypatch, seconds):
    later = time.time() + seconds
    monkeypatch.setattr(time, "time", lambda: later)


def test_an_expired_link_says_it_expired(client, monkeypatch):
    """A stale link in a note should read as expired, not as a typo."""
    draft_id = publish(client)
    advance(monkeypatch, 61)

    response = client.get(f"/d/{draft_id}")
    assert response.status_code == 404
    assert "no longer available" in response.text
    assert "removed on" in response.text


def test_it_still_says_so_after_the_sweeper_has_run(client, app, monkeypatch):
    draft_id = publish(client)
    advance(monkeypatch, 61)
    assert app.state.sweep_expired() == 1

    assert "no longer available" in client.get(f"/d/{draft_id}").text


def test_a_manually_deleted_draft_says_it_was_removed(client):
    draft_id = publish(client, ttl_seconds=3600)
    client.delete(f"/api/drafts/{draft_id}", headers=AUTH)

    assert "no longer available" in client.get(f"/d/{draft_id}").text


def test_an_id_that_never_existed_is_just_not_found(client):
    response = client.get("/d/aaaaaaaaaaaaaaaaaaaaaa")
    assert response.status_code == 404
    assert "does not exist" in response.text
    assert "no longer available" not in response.text


def test_tombstones_hold_no_content(client, app, monkeypatch):
    draft_id = publish(client)
    advance(monkeypatch, 61)
    app.state.sweep_expired()

    with app.state.database.connect() as connection:
        row = connection.execute("SELECT * FROM tombstones WHERE id = ?", (draft_id,)).fetchone()
    assert set(row.keys()) == {"id", "removed_at"}


def test_tombstones_are_purged_once_they_are_old_enough(client, app, monkeypatch):
    draft_id = publish(client)
    advance(monkeypatch, 61)
    app.state.sweep_expired()
    assert "no longer available" in client.get(f"/d/{draft_id}").text

    advance(monkeypatch, app.state.config.tombstone_retention_seconds + 120)
    app.state.sweep_expired()

    assert "does not exist" in client.get(f"/d/{draft_id}").text


def test_the_expired_page_honours_the_theme_query(client, monkeypatch):
    draft_id = publish(client)
    advance(monkeypatch, 61)

    assert "prefers-color-scheme" not in client.get(f"/d/{draft_id}?theme=dark").text
