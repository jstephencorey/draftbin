from draftbin.config import DEFAULT_TTL_SECONDS
from tests.conftest import AUTH

HTML_DOC = "<!doctype html><html><head><title>Plan</title></head><body><h1>Plan</h1></body></html>"


def test_upload_requires_a_token(client):
    response = client.post("/api/upload", json={"html": HTML_DOC})
    assert response.status_code == 401


def test_upload_rejects_a_wrong_token(client):
    response = client.post(
        "/api/upload", json={"html": HTML_DOC}, headers={"Authorization": "Bearer nope"}
    )
    assert response.status_code == 401


def test_html_upload_returns_a_viewable_url(client):
    response = client.post(
        "/api/upload", json={"html": HTML_DOC, "filename": "plan.html"}, headers=AUTH
    )
    assert response.status_code == 201
    body = response.json()
    assert body["url"] == f"https://drafts.example.com/d/{body['id']}"
    assert body["title"] == "Plan"
    assert body["expires_in_seconds"] == DEFAULT_TTL_SECONDS

    view = client.get(f"/d/{body['id']}")
    assert view.status_code == 200
    assert view.text == HTML_DOC


def test_html_upload_is_served_byte_for_byte(client):
    response = client.post("/api/upload", json={"html": HTML_DOC}, headers=AUTH)
    view = client.get(f"/d/{response.json()['id']}")
    assert view.text == HTML_DOC


def test_html_title_falls_back_to_the_filename(client):
    response = client.post(
        "/api/upload", json={"html": "<p>no head at all</p>", "filename": "plan.html"}, headers=AUTH
    )
    assert response.json()["title"] == "plan"


def test_untitled_html_gets_a_generic_title(client):
    response = client.post("/api/upload", json={"html": "<p>hi</p>"}, headers=AUTH)
    assert response.json()["title"] == "Untitled draft"


def test_upload_strips_directories_from_the_filename(client):
    response = client.post(
        "/api/upload",
        json={"html": HTML_DOC, "filename": "../../etc/passwd.html"},
        headers=AUTH,
    )
    assert response.json()["filename"] == "passwd.html"


def test_upload_rejects_a_ttl_over_the_maximum(client):
    response = client.post(
        "/api/upload", json={"html": HTML_DOC, "ttl_seconds": 604801}, headers=AUTH
    )
    assert response.status_code == 422
    assert "604800" in response.json()["detail"]


def test_upload_rejects_an_oversized_document(client, config):
    oversized = "<p>" + "x" * config.max_upload_bytes + "</p>"
    response = client.post("/api/upload", json={"html": oversized}, headers=AUTH)
    assert response.status_code == 413


def test_oversized_body_is_rejected_without_a_token(client, config):
    """The size guard has to sit ahead of the route: the body is read before auth runs."""
    oversized = "x" * (config.max_upload_bytes + 1)
    response = client.post("/api/upload", json={"html": oversized})
    assert response.status_code == 413
    assert "no-store" in response.headers["cache-control"]


def test_unknown_draft_id_renders_the_not_found_page(client):
    response = client.get("/d/aaaaaaaaaaaaaaaaaaaaaa")
    assert response.status_code == 404
    assert "expired" in response.text


def test_malformed_draft_id_is_not_found(client):
    assert client.get("/d/short").status_code == 404
