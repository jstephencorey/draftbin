import time

from tests.conftest import AUTH, TOKEN


def publish(client, title):
    return client.post(
        "/api/upload/markdown", json={"markdown": "# Body\n", "title": title}, headers=AUTH
    ).json()


def test_the_listing_needs_the_token_too(browser):
    response = browser.get("/drafts")
    assert response.status_code == 401
    assert "Enter your token" in response.text
    assert 'action="/drafts"' in response.text


def test_unlocking_the_listing_lands_back_on_it(browser):
    publish(browser, "Visible once unlocked")

    response = browser.post("/drafts", data={"token": TOKEN})
    assert response.status_code == 303
    assert response.headers["location"] == "/drafts"
    assert "Visible once unlocked" in browser.get("/drafts").text


def test_every_live_draft_is_listed_newest_first(client):
    older = publish(client, "Older note")
    newer = publish(client, "Newer note")

    page = client.get("/drafts").text
    assert page.index("Newer note") < page.index("Older note")
    assert f'href="/d/{older["id"]}"' in page
    assert f'href="/d/{newer["id"]}"' in page


def test_an_expired_draft_drops_off_the_listing(client, monkeypatch):
    client.post(
        "/api/upload/markdown",
        json={"markdown": "# Fleeting\n", "title": "Fleeting", "ttl_seconds": 60},
        headers=AUTH,
    )
    later = time.time() + 61
    monkeypatch.setattr(time, "time", lambda: later)

    assert "Fleeting" not in client.get("/drafts").text


def test_an_empty_listing_says_so(client):
    assert "Nothing published" in client.get("/drafts").text


def test_the_listing_links_relatively_so_the_hostname_survives(client):
    """Reached over the tunnel or over the LAN, you stay on the host you arrived on."""
    draft = publish(client, "Anywhere")
    assert f'href="/d/{draft["id"]}"' in client.get("/drafts").text


def test_the_listing_is_never_cached(client):
    assert "no-store" in client.get("/drafts").headers["cache-control"]
