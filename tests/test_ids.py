import time

from draftbin.ids import is_draft_id, new_draft_id
from draftbin.wordlist import WORDS
from tests.conftest import AUTH

LEGACY_ID = "UH4jXBAR958NTaH1e0Blhg"


def publish(client, **body) -> dict:
    return client.post(
        "/api/upload/markdown", json={"markdown": "# Words\n", **body}, headers=AUTH
    ).json()


def test_a_new_id_is_two_words_from_the_list():
    first, second = new_draft_id().split("-")
    assert first in WORDS and second in WORDS


def test_ids_are_short_enough_to_type():
    """The whole point of the change: readable off a phone screen, typable into one."""
    assert max(len(word) for word in WORDS) == 5
    assert all(word.isalpha() and word.islower() for word in WORDS)


def test_published_ids_use_the_word_form(client):
    assert is_draft_id(publish(client)["id"])
    assert "-" in publish(client)["id"]


def test_the_url_carries_the_word_id(client):
    draft = publish(client)
    assert draft["url"].endswith(f"/d/{draft['id']}")


def test_legacy_ids_are_still_recognised():
    """Links already written into notes must not start reading as typos."""
    assert is_draft_id(LEGACY_ID)


def test_a_legacy_draft_still_resolves(client, app):
    """Rows minted before the switch keep serving; only new ids changed shape."""
    now = int(time.time())
    draft = publish(client)
    with app.state.database.connect() as connection:
        connection.execute("UPDATE drafts SET id = ? WHERE id = ?", (LEGACY_ID, draft["id"]))
    app.state.store.write(LEGACY_ID, app.state.store.read(draft["id"]))

    assert client.get(f"/d/{LEGACY_ID}").status_code == 200
    assert app.state.database.find_live(LEGACY_ID, now) is not None


def test_nonsense_is_not_a_draft_id():
    for value in ("", "one", "-", "notaword-either", "a-b", "UPPER-CASE", "one-two-three"):
        assert not is_draft_id(value), value


def test_a_live_id_is_never_handed_out_twice(client, monkeypatch):
    taken = publish(client)["id"]
    minted = iter([taken, taken, "spare-word"])
    monkeypatch.setattr("draftbin.app.new_draft_id", lambda: next(minted))

    assert publish(client)["id"] == "spare-word"


def test_a_tombstoned_id_is_never_reissued(client, app, monkeypatch):
    """Reusing a retired id would silently point a link someone still holds at new content."""
    retired = publish(client, ttl_seconds=60)["id"]
    client.delete(f"/api/drafts/{retired}", headers=AUTH)
    assert app.state.database.id_in_use(retired)

    minted = iter([retired, "fresh-word"])
    monkeypatch.setattr("draftbin.app.new_draft_id", lambda: next(minted))
    assert publish(client)["id"] == "fresh-word"


def test_giving_up_beats_spinning_forever(client, monkeypatch):
    monkeypatch.setattr("draftbin.app.new_draft_id", lambda: "same-word")
    assert publish(client)  # first one takes the id

    response = client.post("/api/upload/markdown", json={"markdown": "# Again\n"}, headers=AUTH)
    assert response.status_code == 503
