import dataclasses

import pytest
from fastapi.testclient import TestClient

from draftbin.app import PASTE_COOKIE, create_app
from tests.conftest import TOKEN

PASTE = {"text": "# Pasted\n\nFrom a phone.", "token": TOKEN}


@pytest.fixture
def browser(app):
    """https, or the cookie jar drops the Secure cookie; redirects stay unfollowed
    because where the form sends you is half of what is under test."""
    with TestClient(app, base_url="https://testserver", follow_redirects=False) as client:
        yield client


def test_the_form_publishes_and_sends_you_to_the_draft(browser):
    response = browser.post("/paste", data=PASTE)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/d/")
    assert "Pasted" in browser.get(response.headers["location"]).text


def test_the_redirect_is_relative_so_the_hostname_survives(browser):
    """Reached over the tunnel or over the LAN, you stay on the host you arrived on."""
    location = browser.post("/paste", data=PASTE).headers["location"]
    assert not location.startswith("http")


def test_a_title_field_names_the_draft(browser):
    location = browser.post("/paste", data={**PASTE, "title": "Phone note"}).headers["location"]
    assert "<title>Phone note</title>" in browser.get(location).text


def test_the_token_field_disappears_once_the_cookie_is_set(browser):
    assert 'name="token"' in browser.get("/").text

    browser.post("/paste", data=PASTE)
    assert 'name="token"' not in browser.get("/").text


def test_the_cookie_alone_publishes_the_next_time(browser):
    browser.post("/paste", data=PASTE)

    response = browser.post("/paste", data={"text": "# Second"})
    assert response.status_code == 303


def test_the_cookie_cannot_be_read_by_script_or_sent_cross_site(browser):
    """SameSite=Strict is what stops a hostile page making the browser publish."""
    header = browser.post("/paste", data=PASTE).headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=strict" in header
    assert f"{PASTE_COOKIE}=" in header


def test_the_cookie_is_secure_only_over_https(config):
    plain = dataclasses.replace(config, public_base_url="http://localhost:8000")
    with TestClient(create_app(plain), follow_redirects=False) as client:
        assert "secure" not in client.post("/paste", data=PASTE).headers["set-cookie"].lower()

    with TestClient(create_app(config), follow_redirects=False) as client:
        assert "secure" in client.post("/paste", data=PASTE).headers["set-cookie"].lower()


def test_a_bad_token_re_renders_the_form_with_the_text_intact(browser):
    response = browser.post("/paste", data={"text": "# Kept\n", "token": "wrong-token-entirely"})

    assert response.status_code == 401
    assert "not accepted" in response.text
    assert "# Kept" in response.text
    assert "set-cookie" not in response.headers


def test_a_rotated_token_clears_the_stale_cookie_instead_of_looping(browser):
    browser.cookies.set(PASTE_COOKIE, "a-token-from-before-the-rotation")

    response = browser.post("/paste", data={"text": "# Note"})
    assert response.status_code == 401
    assert "rotated" in response.text
    assert 'name="token"' in response.text
    assert f'{PASTE_COOKIE}=""' in response.headers["set-cookie"]


def test_an_empty_paste_is_refused_rather_than_published(browser):
    response = browser.post("/paste", data={"text": "   \n", "token": TOKEN})

    assert response.status_code == 422
    assert "Nothing to publish" in response.text
    # The token was fine; only the text was missing, so do not ask for it again.
    assert 'name="token"' not in response.text
    assert browser.get("/api/drafts", headers={"Authorization": f"Bearer {TOKEN}"}).json() == {
        "drafts": []
    }


def test_the_paste_form_is_never_cached(browser):
    """Whether the token field is showing leaks whether the cookie is set."""
    assert "no-store" in browser.get("/").headers["cache-control"]


def test_the_landing_page_advertises_the_real_default_ttl(browser):
    assert "48 hours" in browser.get("/").text
