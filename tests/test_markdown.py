from draftbin.markdown_render import render_markdown
from tests.conftest import AUTH


def test_title_comes_from_the_first_h1():
    rendered = render_markdown("# The **real** title\n\n# Second\n")
    assert rendered.title == "The real title"


def test_title_is_none_without_an_h1():
    assert render_markdown("## Only an h2\n").title is None


def test_code_blocks_are_highlighted():
    html = render_markdown("```python\nx = 1\n```\n").html
    assert 'class="highlight"' in html


def test_unknown_code_language_still_renders():
    html = render_markdown("```notalanguage\nplain text\n```\n").html
    assert "plain text" in html


def test_tables_and_task_lists_render():
    html = render_markdown("| a |\n|---|\n| 1 |\n\n- [x] done\n").html
    assert "<table>" in html
    assert "task-list-item" in html


def test_markdown_upload_renders_a_styled_document(client):
    response = client.post(
        "/api/upload/markdown",
        json={"markdown": "# Weekly notes\n\nSome *text*.\n", "filename": "notes.md"},
        headers=AUTH,
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Weekly notes"

    view = client.get(f"/d/{response.json()['id']}")
    assert view.status_code == 200
    assert "<em>text</em>" in view.text
    assert "prefers-color-scheme" in view.text
    assert 'name="robots"' in view.text


def test_markdown_document_shows_its_expiry(client):
    response = client.post(
        "/api/upload/markdown", json={"markdown": "# Hi\n"}, headers=AUTH
    )
    view = client.get(f"/d/{response.json()['id']}")
    assert "link expires" in view.text


def test_explicit_title_beats_the_first_heading(client):
    response = client.post(
        "/api/upload/markdown",
        json={"markdown": "# Heading\n", "title": "Chosen"},
        headers=AUTH,
    )
    assert response.json()["title"] == "Chosen"


def test_title_falls_back_to_the_filename(client):
    response = client.post(
        "/api/upload/markdown",
        json={"markdown": "no heading here\n", "filename": "day-one.md"},
        headers=AUTH,
    )
    assert response.json()["title"] == "day-one"


def test_untitled_markdown_gets_a_generic_title(client):
    response = client.post("/api/upload/markdown", json={"markdown": "text\n"}, headers=AUTH)
    assert response.json()["title"] == "Untitled draft"


def test_raw_html_in_markdown_cannot_execute(client):
    response = client.post(
        "/api/upload/markdown",
        json={"markdown": "<script>alert(1)</script>\n"},
        headers=AUTH,
    )
    view = client.get(f"/d/{response.json()['id']}")
    assert "sandbox" in view.headers["content-security-policy"]
    assert "default-src 'none'" in view.headers["content-security-policy"]
