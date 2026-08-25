from draftbin.fonts import FONT_FILES
from tests.conftest import AUTH


def test_every_declared_font_is_actually_served(client):
    for filename in FONT_FILES:
        response = client.get(f"/static/fonts/{filename}")
        assert response.status_code == 200, filename
        assert response.headers["content-type"] == "font/woff2"
        assert response.content[:4] == b"wOF2"


def test_head_works_on_a_font_too(client):
    assert client.head("/static/fonts/merriweather-latin.woff2").status_code == 200


def test_fonts_are_cached_even_though_drafts_are_not(client):
    """The one immutable thing here; re-fetching it per draft view would be silly."""
    headers = client.get("/static/fonts/merriweather-latin.woff2").headers
    assert "immutable" in headers["cache-control"]
    assert "no-store" not in headers["cache-control"]


def test_only_the_declared_names_resolve(client):
    """The allowlist is what keeps a crafted filename from reaching out of the folder."""
    assert client.get("/static/fonts/OFL.txt").status_code == 404
    assert client.get("/static/fonts/..%2f..%2fconfig.py").status_code == 404


def test_drafts_are_allowed_to_load_the_font(client):
    """`default-src 'none'` blocks fonts too, so font-src has to name this origin."""
    draft_id = client.post(
        "/api/upload/markdown", json={"markdown": "# Typeset\n"}, headers=AUTH
    ).json()["id"]

    response = client.get(f"/d/{draft_id}")
    assert "font-src 'self' https://drafts.example.com" in response.headers[
        "content-security-policy"
    ]
    assert "/static/fonts/merriweather-latin.woff2" in response.text
    assert "font-family: Merriweather" in response.text


def test_the_face_falls_back_to_something_every_device_has(client):
    """A saved-to-disk copy loads no font at all, so the stack after it has to be real."""
    draft_id = client.post(
        "/api/upload/markdown", json={"markdown": "# Typeset\n"}, headers=AUTH
    ).json()["id"]

    assert "Merriweather, Georgia" in client.get(f"/d/{draft_id}").text
