from draftbin.app import ACCESS_COOKIE
from tests.conftest import AUTH, TOKEN


def publish(browser, markdown="# Private\n\nNot for strangers."):
    return browser.post("/api/upload/markdown", json={"markdown": markdown}, headers=AUTH).json()


def test_a_link_alone_no_longer_opens_a_draft(browser):
    draft = publish(browser)

    response = browser.get(f"/d/{draft['id']}")
    assert response.status_code == 401
    assert "Enter your token" in response.text
    assert "Not for strangers" not in response.text


def test_the_gate_says_the_same_thing_for_an_id_that_was_never_minted(browser):
    """Otherwise a scanner maps the whole keyspace without ever holding the token, and
    two words is only ~1.7M ids. The form action is the only thing allowed to differ."""
    draft = publish(browser)

    real = browser.get(f"/d/{draft['id']}")
    invented = browser.get("/d/acorn-bagel")
    assert real.status_code == invented.status_code == 401
    assert real.text.replace(draft["id"], "ID") == invented.text.replace("acorn-bagel", "ID")


def test_the_gate_is_not_served_under_the_draft_sandbox(browser):
    """The draft CSP sandboxes onto an opaque origin and sets form-action 'none'. A gate
    page carrying those headers could not submit the form that unlocks it."""
    response = browser.get("/d/acorn-bagel")
    assert "content-security-policy" not in response.headers
    assert 'action="/d/acorn-bagel"' in response.text


def test_unlocking_sets_the_cookie_and_lands_you_on_the_draft(browser):
    draft = publish(browser)
    target = f"/d/{draft['id']}"

    response = browser.post(target, data={"token": TOKEN})
    assert response.status_code == 303
    assert response.headers["location"] == target
    assert f"{ACCESS_COOKIE}=" in response.headers["set-cookie"]
    assert "Not for strangers" in browser.get(target).text


def test_the_cookie_opens_every_later_draft_too(browser):
    first = publish(browser)
    browser.post(f"/d/{first['id']}", data={"token": TOKEN})

    second = publish(browser, "# Second\n\nAlso private.")
    assert "Also private" in browser.get(f"/d/{second['id']}").text


def test_a_bad_token_at_the_gate_is_refused_and_remembers_nothing(browser):
    draft = publish(browser)

    response = browser.post(f"/d/{draft['id']}", data={"token": "wrong-token-entirely"})
    assert response.status_code == 401
    assert "not accepted" in response.text
    assert "set-cookie" not in response.headers


def test_unlocking_a_malformed_id_sends_you_home_rather_than_echoing_it(browser):
    """Only a well-formed id is worth putting in a Location header."""
    response = browser.post("/d/not-a-real-draft-id-shape", data={"token": TOKEN})
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_a_bearer_token_still_reads_a_draft_for_curl(browser):
    draft = publish(browser)
    assert "Not for strangers" in browser.get(f"/d/{draft['id']}", headers=AUTH).text


def test_a_non_ascii_cookie_is_a_refusal_rather_than_a_crash(browser):
    """compare_digest raises on non-ASCII str, and the cookie is attacker-supplied on
    every read now. Sent as raw bytes because that is the only way one gets here: httpx
    refuses to encode it, but headers reach the app latin-1 decoded, so curl can."""
    response = browser.get("/d/acorn-bagel", headers={b"Cookie": b"draftbin_token=t\xf6ken"})
    assert response.status_code == 401


def test_the_gate_is_never_cached(browser):
    assert "no-store" in browser.get("/d/acorn-bagel").headers["cache-control"]


def test_a_draft_still_carries_the_sandbox_once_you_are_through_the_gate(client):
    draft = client.post("/api/upload/markdown", json={"markdown": "# Ok\n"}, headers=AUTH).json()

    csp = client.get(f"/d/{draft['id']}").headers["content-security-policy"]
    assert "sandbox" in csp
