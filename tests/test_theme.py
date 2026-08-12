import dataclasses

import pytest
from fastapi.testclient import TestClient

from draftbin.app import create_app
from draftbin.config import ConfigError, load_config
from draftbin.templates import theme_css
from tests.conftest import AUTH, TOKEN


def published_html(config) -> str:
    with TestClient(create_app(config)) as client:
        draft_id = client.post(
            "/api/upload/markdown", json={"markdown": "# Theme\n"}, headers=AUTH
        ).json()["id"]
        return client.get(f"/d/{draft_id}").text


def test_auto_theme_follows_the_reader(config):
    html = published_html(config)
    assert "color-scheme: light dark" in html
    assert "prefers-color-scheme: dark" in html


def test_dark_theme_is_unconditional(config):
    html = published_html(dataclasses.replace(config, theme="dark"))
    assert "color-scheme: dark" in html
    assert "prefers-color-scheme" not in html
    assert "#16181d" in html


def test_light_theme_is_unconditional(config):
    html = published_html(dataclasses.replace(config, theme="light"))
    assert "color-scheme: light;" in html
    assert "prefers-color-scheme" not in html
    assert "#fdfdfc" in html


def test_every_theme_ships_syntax_highlighting():
    for theme in ("auto", "light", "dark"):
        assert ".highlight" in theme_css(theme)


def test_auto_theme_ships_both_highlight_palettes():
    css = theme_css("auto")
    assert css.count("prefers-color-scheme") == 1
    assert "#F8F8F2" in css and "#19177C" in css


def test_query_param_overrides_the_server_default(client):
    draft_id = client.post(
        "/api/upload/markdown", json={"markdown": "# Q\n"}, headers=AUTH
    ).json()["id"]

    assert "prefers-color-scheme: dark" in client.get(f"/d/{draft_id}").text
    forced = client.get(f"/d/{draft_id}?theme=dark").text
    assert "color-scheme: dark" in forced
    assert "prefers-color-scheme" not in forced


def test_query_param_overrides_the_drafts_own_theme(client):
    draft_id = client.post(
        "/api/upload/markdown", json={"markdown": "# Q\n", "theme": "dark"}, headers=AUTH
    ).json()["id"]

    assert "prefers-color-scheme" not in client.get(f"/d/{draft_id}").text
    assert "#fdfdfc" in client.get(f"/d/{draft_id}?theme=light").text


def test_draft_theme_applies_without_a_query_param(client):
    response = client.post(
        "/api/upload/markdown", json={"markdown": "# Q\n", "theme": "light"}, headers=AUTH
    ).json()
    assert response["theme"] == "light"
    assert "#fdfdfc" in client.get(f"/d/{response['id']}").text


def test_unrecognised_query_theme_falls_back(client):
    draft_id = client.post(
        "/api/upload/markdown", json={"markdown": "# Q\n"}, headers=AUTH
    ).json()["id"]
    assert "prefers-color-scheme: dark" in client.get(f"/d/{draft_id}?theme=solarized").text


def test_upload_rejects_an_unknown_theme(client):
    response = client.post(
        "/api/upload/markdown", json={"markdown": "# Q\n", "theme": "solarized"}, headers=AUTH
    )
    assert response.status_code == 422


def test_html_drafts_ignore_the_query_param(client):
    doc = "<!doctype html><html><body><p>fixed</p></body></html>"
    response = client.post("/api/upload", json={"html": doc}, headers=AUTH).json()
    assert response["themeable"] is False
    assert client.get(f"/d/{response['id']}?theme=dark").text == doc


def test_markdown_is_stored_as_a_body_fragment(client, app):
    draft_id = client.post(
        "/api/upload/markdown", json={"markdown": "# Fragment\n"}, headers=AUTH
    ).json()["id"]

    stored = app.state.store.path_for(draft_id).read_text(encoding="utf-8")
    assert "<!doctype" not in stored
    assert "color-scheme" not in stored
    assert "<h1" in stored


def test_reported_size_bounds_every_theme(client):
    response = client.post(
        "/api/upload/markdown", json={"markdown": "# Size\n", "theme": "dark"}, headers=AUTH
    ).json()
    for theme in ("auto", "light", "dark"):
        served = len(client.get(f"/d/{response['id']}?theme={theme}").text.encode("utf-8"))
        assert served <= response["size_bytes"]


def test_unknown_theme_is_rejected(monkeypatch):
    monkeypatch.setenv("DRAFTBIN_TOKEN", TOKEN)
    monkeypatch.setenv("DRAFTBIN_THEME", "solarized")
    with pytest.raises(ConfigError, match="DRAFTBIN_THEME"):
        load_config()


def test_theme_defaults_to_auto(monkeypatch):
    monkeypatch.setenv("DRAFTBIN_TOKEN", TOKEN)
    monkeypatch.delenv("DRAFTBIN_THEME", raising=False)
    assert load_config().theme == "auto"
