from draftbin.html_document import document_title


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
