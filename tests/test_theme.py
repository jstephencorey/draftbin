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


def test_unknown_theme_is_rejected(monkeypatch):
    monkeypatch.setenv("DRAFTBIN_TOKEN", TOKEN)
    monkeypatch.setenv("DRAFTBIN_THEME", "solarized")
    with pytest.raises(ConfigError, match="DRAFTBIN_THEME"):
        load_config()


def test_theme_defaults_to_auto(monkeypatch):
    monkeypatch.setenv("DRAFTBIN_TOKEN", TOKEN)
    monkeypatch.delenv("DRAFTBIN_THEME", raising=False)
    assert load_config().theme == "auto"
