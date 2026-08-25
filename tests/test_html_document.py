from draftbin.html_document import document_title, outline
from draftbin.markdown_render import render_markdown


def test_title_is_read_from_the_head():
    assert document_title("<html><head><title>The Plan</title></head></html>") == "The Plan"


def test_title_entities_are_decoded():
    assert document_title("<title>Tom &amp; Jerry</title>") == "Tom & Jerry"


def test_first_title_wins():
    assert document_title("<title>First</title><title>Second</title>") == "First"


def test_missing_title_is_none():
    assert document_title("<p>no title here</p>") is None


def test_empty_title_is_none():
    assert document_title("<title>   </title>") is None


def test_outline_collects_h2_and_h3_with_their_anchors():
    headings = outline(render_markdown("## One\n\n### Under one\n\n## Two\n").html)
    assert [(h.level, h.anchor, h.text) for h in headings] == [
        (2, "one", "One"),
        (3, "under-one", "Under one"),
        (2, "two", "Two"),
    ]


def test_outline_skips_the_title_and_the_deepest_headings():
    headings = outline(render_markdown("# Title\n\n## Section\n\n#### Detail\n").html)
    assert [h.text for h in headings] == ["Section"]


def test_outline_drops_the_permalink_glyph():
    """The anchors plugin appends a '#' link inside every heading; it is not part of the label."""
    assert outline(render_markdown("## Real text\n").html)[0].text == "Real text"


def test_outline_flattens_formatting_in_a_heading():
    assert outline(render_markdown("## A **bold** word\n").html)[0].text == "A bold word"


def test_outline_of_a_document_with_no_headings_is_empty():
    assert outline(render_markdown("just a paragraph\n").html) == []
