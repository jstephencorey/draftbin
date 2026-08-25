from draftbin.storage import HtmlStore


def test_write_leaves_nothing_staged_behind(tmp_path):
    store = HtmlStore(tmp_path)
    store.initialize()
    store.write("aaaaaaaaaaaaaaaaaaaaaa", "<p>one</p>")

    assert [path.name for path in tmp_path.iterdir()] == ["aaaaaaaaaaaaaaaaaaaaaa.html"]
    assert store.read("aaaaaaaaaaaaaaaaaaaaaa") == "<p>one</p>"


def test_rewriting_a_draft_replaces_it_whole(tmp_path):
    store = HtmlStore(tmp_path)
    store.initialize()
    store.write("aaaaaaaaaaaaaaaaaaaaaa", "<p>a much longer first version</p>")
    store.write("aaaaaaaaaaaaaaaaaaaaaa", "<p>short</p>")

    assert store.read("aaaaaaaaaaaaaaaaaaaaaa") == "<p>short</p>"


def test_staged_writes_from_a_crash_are_discarded(tmp_path):
    store = HtmlStore(tmp_path)
    store.initialize()
    (tmp_path / "aaaaaaaaaaaaaaaaaaaaaa.html.tmp").write_text("half a doc", encoding="utf-8")

    store.discard_staged_writes()

    assert list(tmp_path.iterdir()) == []
