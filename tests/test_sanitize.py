from draftbin.markdown_render import render_markdown
from draftbin.sanitize import sanitize_html


def test_scripts_are_escaped_into_visible_text():
    assert sanitize_html("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_frames_and_objects_are_escaped():
    for markup in ('<iframe src="https://evil"></iframe>', "<object data='x'></object>"):
        assert "<" not in sanitize_html(markup)


def test_event_handlers_are_dropped_but_the_tag_stays():
    assert sanitize_html('<b onclick="steal()">bold</b>') == "<b>bold</b>"


def test_javascript_urls_are_dropped():
    assert sanitize_html('<a href="javascript:alert(1)">go</a>') == "<a>go</a>"


def test_ordinary_links_survive():
    markup = '<a href="https://example.com" rel="noopener">go</a>'
    assert sanitize_html(markup) == markup


def test_fragment_links_survive():
    assert sanitize_html('<a href="#section">go</a>') == '<a href="#section">go</a>'


def test_data_urls_are_images_only():
    assert "src" in sanitize_html('<img src="data:image/png;base64,AAA" alt="x">')
    assert "href" not in sanitize_html('<a href="data:text/html,<b>hi">go</a>')


def test_inline_svg_keeps_its_presentation_attributes():
    result = sanitize_html('<svg viewBox="0 0 4 4"><path d="M0 0" stroke="red"/></svg>')
    assert 'viewbox="0 0 4 4"' in result
    assert 'd="M0 0"' in result
    assert 'stroke="red"' in result


def test_foreign_object_is_not_an_svg_escape_hatch():
    assert "<foreignobject" not in sanitize_html("<foreignObject><script>x</script></foreignObject>")


def test_comments_are_removed():
    assert sanitize_html("a<!-- secret note -->b") == "ab"


def test_unbalanced_fragments_are_left_alone():
    """markdown-it splits a <details> block across tokens, so closing tags here would corrupt it."""
    assert sanitize_html("<details>") == "<details>"
    assert sanitize_html("</details>") == "</details>"


def test_details_blocks_survive_a_round_trip():
    html = render_markdown("<details><summary>More</summary>\n\nhidden **body**\n\n</details>\n").html
    assert "<details>" in html
    assert "<summary>More</summary>" in html
    assert "<strong>body</strong>" in html


def test_generated_task_list_checkboxes_are_not_escaped():
    """The task list plugin emits its checkbox as raw HTML, so the filter sees it too."""
    html = render_markdown("- [x] done\n").html
    assert '<input class="task-list-item-checkbox"' in html
    assert "&lt;input" not in html
