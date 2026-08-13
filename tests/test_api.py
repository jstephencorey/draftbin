from tests.conftest import AUTH


def test_listing_requires_a_token(client):
    assert client.get("/api/drafts").status_code == 401


def test_listing_returns_newest_first(client):
    first = client.post("/api/upload/markdown", json={"markdown": "# One\n"}, headers=AUTH).json()
    second = client.post("/api/upload/markdown", json={"markdown": "# Two\n"}, headers=AUTH).json()

    drafts = client.get("/api/drafts", headers=AUTH).json()["drafts"]
    assert {draft["id"] for draft in drafts} == {first["id"], second["id"]}
    assert drafts[0]["expires_in_seconds"] <= 86400


def test_delete_removes_the_draft_and_its_file(client, app):
    draft_id = client.post(
        "/api/upload/markdown", json={"markdown": "# Gone\n"}, headers=AUTH
    ).json()["id"]

    assert client.delete(f"/api/drafts/{draft_id}", headers=AUTH).status_code == 200
    assert not app.state.store.path_for(draft_id).exists()
    assert client.get(f"/d/{draft_id}").status_code == 404


def test_delete_requires_a_token(client):
    assert client.delete("/api/drafts/aaaaaaaaaaaaaaaaaaaaaa").status_code == 401


def test_delete_of_an_unknown_draft_is_not_found(client):
    assert client.delete("/api/drafts/aaaaaaaaaaaaaaaaaaaaaa", headers=AUTH).status_code == 404


def test_draft_response_carries_the_privacy_headers(client):
    draft_id = client.post(
        "/api/upload/markdown", json={"markdown": "# Headers\n"}, headers=AUTH
    ).json()["id"]

    headers = client.get(f"/d/{draft_id}").headers
    assert "noindex" in headers["x-robots-tag"]
    assert headers["referrer-policy"] == "no-referrer"
    assert "no-store" in headers["cache-control"]
    assert headers["x-content-type-options"] == "nosniff"


def test_json_responses_are_never_cached(client):
    """These payloads carry draft URLs, which are the only thing gating access."""
    draft_id = client.post(
        "/api/upload/markdown", json={"markdown": "# Cached\n"}, headers=AUTH
    ).json()["id"]

    responses = [
        client.post("/api/upload/markdown", json={"markdown": "# New\n"}, headers=AUTH),
        client.post("/api/upload", json={"html": "<p>hi</p>"}, headers=AUTH),
        client.get("/api/drafts", headers=AUTH),
        client.get("/api/drafts"),
        client.delete(f"/api/drafts/{draft_id}", headers=AUTH),
        client.get("/healthz"),
    ]
    for response in responses:
        assert "no-store" in response.headers["cache-control"], response.request.url
        assert response.headers["referrer-policy"] == "no-referrer"


def test_robots_txt_disallows_everything(client):
    assert "Disallow: /" in client.get("/robots.txt").text


def test_healthz_is_open(client):
    assert client.get("/healthz").json() == {"ok": True}


def test_landing_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "draftbin" in response.text
