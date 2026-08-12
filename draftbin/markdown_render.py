from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.deflist import deflist_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

TEXT_TOKEN_TYPES = frozenset({"text", "code_inline"})


def highlight_code(code: str, language: str, _attrs: str) -> str:
    try:
        lexer = get_lexer_by_name(language) if language else guess_lexer(code)
    except ClassNotFound:
        return ""
    formatter = HtmlFormatter(nowrap=True)
    return f'<pre class="highlight"><code>{highlight(code, lexer, formatter)}</code></pre>'


def scrollable_tables(parser: MarkdownIt) -> None:
    """Wrap tables so wide ones scroll inside the text column instead of overflowing it."""
    parser.add_render_rule(
        "table_open", lambda self, tokens, idx, options, env: '<div class="table-scroll"><table>'
    )
    parser.add_render_rule(
        "table_close", lambda self, tokens, idx, options, env: "</table></div>"
    )


def build_parser() -> MarkdownIt:
    parser = MarkdownIt("commonmark", {"typographer": True, "highlight": highlight_code})
    parser.enable(["table", "strikethrough", "linkify", "smartquotes", "replacements"])
    parser.use(anchors_plugin, max_level=4, permalink=True, permalinkSymbol="#").use(
        tasklists_plugin
    ).use(footnote_plugin).use(deflist_plugin)
    scrollable_tables(parser)
    return parser


@dataclass(frozen=True)
class RenderedMarkdown:
    html: str
    title: str | None


def first_heading_text(tokens: list[Token]) -> str | None:
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or token.tag != "h1":
            continue
        inline = tokens[index + 1]
        text = "".join(
            child.content for child in (inline.children or []) if child.type in TEXT_TOKEN_TYPES
        ).strip()
        return text or None
    return None


def render_markdown(text: str) -> RenderedMarkdown:
    parser = build_parser()
    tokens = parser.parse(text)
    html = parser.renderer.render(tokens, parser.options, {})
    return RenderedMarkdown(html=html, title=first_heading_text(tokens))
