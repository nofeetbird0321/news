"""One sanitized Markdown renderer for originals, rewrites and RSS."""
import re
import secrets
from html import escape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token
import nh3

PARSER = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
TAGS = {
    "a", "p", "div", "span", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "b", "i", "s", "del", "blockquote", "ul", "ol", "li",
    "pre", "code", "img", "picture", "source", "table", "thead", "tbody", "tr", "th", "td",
    "details", "summary", "kbd", "sup", "sub",
}


class _ReaderHTML(HTMLParser):
    """Add reader attributes to real sanitized elements, then serialize stably."""

    def __init__(self, media=None):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.media = dict(media or {})

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            attrs.update(tabindex="0", **{"aria-label": "数据表格，可横向滚动查看"})
        elif tag == "img":
            attrs.update(loading="lazy", decoding="async", referrerpolicy="no-referrer")
        attributes = "".join(f' {key}="{escape(value or "", quote=True)}"' for key, value in sorted(attrs.items()))
        self.parts.append(f"<{tag}{attributes}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        self.parts.append(escape(data, quote=False))

    def handle_comment(self, data):
        # Only this render's unpredictable internal markers can insert trusted
        # media. Upstream HTML comments never survive into the published output.
        self.parts.append(self.media.pop(data, ""))


def normalize_paragraph(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _document(text: str):
    env = {}
    tokens = PARSER.parse(text, env)
    # CommonMark normalizes CR/LF, not Unicode separators such as U+2028.
    lines = re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", text)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    paragraphs = []
    for index, token in enumerate(tokens):
        if token.type != "paragraph_open" or token.level != 0 or not token.map:
            continue
        start, stop = token.map
        raw = text[offsets[start]:offsets[stop]].rstrip("\r\n")
        close = next(j for j in range(index + 1, len(tokens))
                     if tokens[j].type == "paragraph_close" and tokens[j].level == 0)
        paragraphs.append((normalize_paragraph(raw), offsets[start] + len(raw), close + 1))
    return tokens, env, paragraphs


def paragraph_end(text: str, anchor: str) -> int:
    """Locate a complete, unique top-level paragraph, never text inside a code block."""
    wanted = normalize_paragraph(anchor)
    matches = [end for raw, end, _ in _document(text)[2] if raw == wanted]
    if not wanted or len(matches) != 1:
        raise ValueError("placement paragraph must be complete, top-level and unique")
    return matches[0]


def render_markdown(text: str, base_url: str | None = None, *, after_paragraph: dict | None = None) -> str:
    if base_url is not None and (urlsplit(base_url).scheme != "https" or not urlsplit(base_url).netloc):
        raise ValueError("original.markdown_base_url must be an absolute HTTPS source document URL")
    # README images must resolve to file bytes, while relative document links
    # remain navigable GitHub pages at the exact recorded revision.
    image_base = re.sub(r"^https://github\.com/([^/]+/[^/]+)/blob/", r"https://raw.githubusercontent.com/\1/", (base_url or ""))

    def resolve(value, image=False):
        url = urljoin(image_base if image else (base_url or ""), value)
        return url if urlsplit(url).scheme in ("http", "https", "mailto") else None

    def attribute(tag, name, value):
        if name == "href":
            return resolve(value)
        if name == "src":
            url = resolve(value, image=True)
            return url if url and urlsplit(url).scheme in ("http", "https") else None
        if name == "srcset":
            # Source README uses a plain URL. Reject complex lists rather than
            # misparse comma-containing URLs or permit unchecked candidates.
            if re.search(r"[\s,]", value):
                return None
            url = resolve(value, image=True)
            return url if url and urlsplit(url).scheme in ("http", "https") else None
        if name == "align":
            return value if value in {"left", "center", "right"} else None
        if name == "class":
            return value if tag == "code" and re.fullmatch(r"language-[A-Za-z0-9_+-]+", value) else None
        if name in {"width", "height", "colspan", "rowspan", "start"}:
            return value if re.fullmatch(r"[0-9]{1,5}", value) else None
        return value

    def clean(fragment, media):
        cleaned = nh3.clean(
            fragment, tags=TAGS,
            attributes={"a": {"href", "title"}, "img": {"src", "alt", "width", "height"},
                        "source": {"srcset", "media"}, "th": {"colspan", "rowspan", "align"},
                        "td": {"colspan", "rowspan", "align"}, "ol": {"start"}, "code": {"class"}},
            attribute_filter=attribute, url_schemes={"http", "https", "mailto"},
            clean_content_tags={"script", "style", "iframe", "object", "template", "svg", "math"},
            link_rel="noopener noreferrer", strip_comments=False,
        ).strip()
        # Never substitute serialized markup: literal tags inside title/alt can
        # break attribute boundaries. nh3's forced attributes also have unstable
        # ordering, so serialize actual parsed elements with sorted attributes.
        reader = _ReaderHTML(media)
        reader.feed(cleaned)
        reader.close()
        if reader.media:
            raise ValueError("placement paragraph is inside malformed or removed HTML; media cannot be inserted safely")
        return "".join(reader.parts)

    tokens, env, paragraphs = _document(text)
    # markdown-it emits table alignment as CSS; convert only its known values,
    # so arbitrary upstream style attributes never enter the sanitizer allowlist.
    for token in tokens:
        if token.type in {"th_open", "td_open"}:
            style = token.attrs.pop("style", "")
            if style in {"text-align:left", "text-align:center", "text-align:right"}:
                token.attrSet("align", style.split(":")[1])
    insertions = {}
    for anchor, fragment in (after_paragraph or {}).items():
        end = paragraph_end(text, anchor)
        boundary = next(stop for _, pos, stop in paragraphs if pos == end)
        insertions.setdefault(boundary, []).append(fragment)
    media = {}
    for boundary in sorted(insertions, reverse=True):
        marker = "xz-media-" + secrets.token_hex(16)
        media[marker] = "\n".join(insertions[boundary])
        token = Token("html_block", "", 0)
        token.content = f"<!--{marker}-->\n"
        tokens.insert(boundary, token)
    # Sanitize the entire document once: splitting at paragraph boundaries would
    # prematurely close surrounding raw HTML containers such as <details>.
    return clean(PARSER.renderer.render(tokens, PARSER.options, env), media)


def render_source_markdown(text: str, base_url: str) -> str:
    return render_markdown(text, base_url)
