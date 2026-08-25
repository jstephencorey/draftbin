import time

from tests.conftest import AUTH


def publish_markdown(client, markdown="# First\n"):
    return client.post("/api/upload/markdown", json={"markdown": markdown}, headers=AUTH).json()


def test_replacing_keeps_the_id_and_the_url(client):
    """The whole point: the link recorded in a note survives a revision."""
    first = publish_markdown(client)

    second = client.put(
        f"/api/drafts/{first['id']}/markdown", json={"markdown": "# Second\n"}, headers=AUTH
    ).json()

    assert second["id"] == first["id"]
    assert second["url"] == first["url"]
    assert second["title"] == "Second"

    view = client.get(f"/d/{first['id']}").text
    assert "Second" in view
    assert "First" not in view


def test_replacing_keeps_the_original_publication_date(client):
    first = publish_markdown(client)
    second = client.put(
        f"/api/drafts/{first['id']}/markdown", json={"markdown": "# Second\n"}, headers=AUTH
    ).json()

    assert second["created_at"] == first["created_at"]


def test_replacing_resets_the_expiry(client):
    first = publish_markdown(client)
    first_expiry = client.put(
        f"/api/drafts/{first['id']}/markdown",
        json={"markdown": "# Short\n", "ttl_seconds": 3600},
        headers=AUTH,
    ).json()
    assert first_expiry["expires_in_seconds"] <= 3600

    refreshed = client.put(
        f"/api/drafts/{first['id']}/markdown", json={"markdown": "# Back to default\n"},
        headers=AUTH,
    ).json()
    assert refreshed["expires_in_seconds"] > 3600


def test_replacing_updates_the_stored_size_and_hash(client):
    first = publish_markdown(client)
    second = client.put(
        f"/api/drafts/{first['id']}/markdown",
        json={"markdown": "# Second\n\nWith a good deal more text in it than before.\n"},
        headers=AUTH,
    ).json()

    assert second["content_hash"] != first["content_hash"]
    assert second["size_bytes"] > first["size_bytes"]


def test_a_draft_can_change_format_when_replaced(client):
    first = publish_markdown(client)
    second = client.put(
        f"/api/drafts/{first['id']}/html",
        json={"html": "<html><head><title>Now HTML</title></head><body>hi</body></html>"},
        headers=AUTH,
    ).json()

    assert second["source_format"] == "html"
    assert second["themeable"] is False
    assert second["title"] == "Now HTML"


def test_replacing_requires_a_token(client):
    first = publish_markdown(client)
    response = client.put(f"/api/drafts/{first['id']}/markdown", json={"markdown": "# No\n"})
    assert response.status_code == 401


def test_replacing_an_unknown_draft_is_not_found(client):
    response = client.put(
        "/api/drafts/aaaaaaaaaaaaaaaaaaaaaa/markdown", json={"markdown": "# No\n"}, headers=AUTH
    )
    assert response.status_code == 404


def test_an_expired_draft_cannot_be_revived(client, monkeypatch):
    """Reviving one would bring a link that already leaked back to life."""
    first = client.post(
        "/api/upload/markdown", json={"markdown": "# Gone\n", "ttl_seconds": 60}, headers=AUTH
    ).json()

    later = time.time() + 61
    monkeypatch.setattr(time, "time", lambda: later)

    response = client.put(
        f"/api/drafts/{first['id']}/markdown", json={"markdown": "# Back?\n"}, headers=AUTH
    )
    assert response.status_code == 404


def test_replacing_rejects_an_oversized_document(client, config):
    first = publish_markdown(client)
    oversized = "<p>" + "x" * config.max_upload_bytes + "</p>"

    response = client.put(f"/api/drafts/{first['id']}/html", json={"html": oversized}, headers=AUTH)
    assert response.status_code == 413


def test_a_rejected_replacement_leaves_the_draft_intact(client, config):
    first = publish_markdown(client, "# Keep me\n")
    oversized = "<p>" + "x" * config.max_upload_bytes + "</p>"

    client.put(f"/api/drafts/{first['id']}/html", json={"html": oversized}, headers=AUTH)

    assert "Keep me" in client.get(f"/d/{first['id']}").text
    assert client.get("/api/drafts", headers=AUTH).json()["drafts"][0]["title"] == "Keep me"


def test_replacing_can_change_the_pinned_theme(client):
    first = publish_markdown(client)
    second = client.put(
        f"/api/drafts/{first['id']}/markdown",
        json={"markdown": "# Dark now\n", "theme": "dark"},
        headers=AUTH,
    ).json()

    assert second["theme"] == "dark"
    assert "prefers-color-scheme" not in client.get(f"/d/{first['id']}").text


def test_replacing_rejects_an_unknown_theme(client):
    first = publish_markdown(client)
    response = client.put(
        f"/api/drafts/{first['id']}/markdown",
        json={"markdown": "# Nope\n", "theme": "sepia"},
        headers=AUTH,
    )
    assert response.status_code == 422
