import time

from tests.conftest import AUTH


def publish(client, ttl_seconds=None):
    body = {"markdown": "# Still reading\n"}
    if ttl_seconds:
        body["ttl_seconds"] = ttl_seconds
    return client.post("/api/upload/markdown", json=body, headers=AUTH).json()


def test_extending_pushes_the_expiry_out(client):
    draft = publish(client, ttl_seconds=60)

    extended = client.patch(
        f"/api/drafts/{draft['id']}", json={"ttl_seconds": 7200}, headers=AUTH
    ).json()

    assert extended["id"] == draft["id"]
    assert extended["expires_in_seconds"] > 7000
    assert client.get(f"/d/{draft['id']}").status_code == 200


def test_extending_without_a_ttl_uses_the_server_default(client):
    draft = publish(client, ttl_seconds=60)

    extended = client.patch(f"/api/drafts/{draft['id']}", json={}, headers=AUTH).json()

    assert extended["expires_in_seconds"] > 86000


def test_the_new_expiry_shows_in_the_document(client):
    draft = publish(client, ttl_seconds=60)
    before = client.get(f"/d/{draft['id']}").text

    client.patch(f"/api/drafts/{draft['id']}", json={"ttl_seconds": 604800}, headers=AUTH)

    assert client.get(f"/d/{draft['id']}").text != before


def test_extending_cannot_exceed_the_server_maximum(client, config):
    draft = publish(client)

    response = client.patch(
        f"/api/drafts/{draft['id']}",
        json={"ttl_seconds": config.max_ttl_seconds + 1},
        headers=AUTH,
    )
    assert response.status_code == 422


def test_extending_requires_a_token(client):
    draft = publish(client)
    assert client.patch(f"/api/drafts/{draft['id']}", json={"ttl_seconds": 60}).status_code == 401


def test_extending_an_unknown_draft_is_not_found(client):
    response = client.patch(
        "/api/drafts/aaaaaaaaaaaaaaaaaaaaaa", json={"ttl_seconds": 60}, headers=AUTH
    )
    assert response.status_code == 404


def test_an_expired_draft_cannot_be_extended(client, monkeypatch):
    draft = publish(client, ttl_seconds=60)
    later = time.time() + 61
    monkeypatch.setattr(time, "time", lambda: later)

    response = client.patch(
        f"/api/drafts/{draft['id']}", json={"ttl_seconds": 3600}, headers=AUTH
    )
    assert response.status_code == 404
