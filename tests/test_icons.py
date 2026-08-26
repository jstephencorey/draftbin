from draftbin.icons import ICO_ICON_URL, SVG_ICON_URL
from tests.conftest import AUTH


def test_the_root_probe_gets_a_real_ico(client):
    """Browsers ask for this one without being told to, and they want ICO bytes."""
    response = client.get(ICO_ICON_URL)
    assert response.status_code == 200
    assert response.content[:4] == b"\x00\x00\x01\x00"


def test_the_svg_is_served_as_an_image(client):
    response = client.get(SVG_ICON_URL)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert response.text.startswith("<svg")


def test_head_works_on_both(client):
    assert client.head(ICO_ICON_URL).status_code == 200
    assert client.head(SVG_ICON_URL).status_code == 200


def test_the_icon_is_cached_even_though_drafts_are_not(client):
    for url in (ICO_ICON_URL, SVG_ICON_URL):
        headers = client.get(url).headers
        assert "max-age" in headers["cache-control"], url
        assert "no-store" not in headers["cache-control"], url


def test_a_rendered_draft_names_the_icon(client):
    draft_id = client.post(
        "/api/upload/markdown", json={"markdown": "# Titled\n"}, headers=AUTH
    ).json()["id"]

    body = client.get(f"/d/{draft_id}").text
    assert f'href="{SVG_ICON_URL}"' in body
    assert f'href="{ICO_ICON_URL}"' in body


def test_the_landing_page_names_the_icon(client):
    assert f'href="{SVG_ICON_URL}"' in client.get("/").text


def test_drafts_are_allowed_to_load_the_icon(client):
    """`default-src 'none'` blocks the icon too; favicons are fetched under img-src."""
    draft_id = client.post(
        "/api/upload/markdown", json={"markdown": "# Titled\n"}, headers=AUTH
    ).json()["id"]

    csp = client.get(f"/d/{draft_id}").headers["content-security-policy"]
    assert "img-src 'self' https://drafts.example.com" in csp


def test_an_html_draft_still_has_an_icon_to_fall_back_on(client):
    """Uploaded HTML is served verbatim, so /favicon.ico is the only icon it can get."""
    draft_id = client.post(
        "/api/upload", json={"html": "<html><head></head><body>Hi</body></html>"},
        headers=AUTH,
    ).json()["id"]

    assert "<link rel=\"icon\"" not in client.get(f"/d/{draft_id}").text
    assert client.get(ICO_ICON_URL).status_code == 200
