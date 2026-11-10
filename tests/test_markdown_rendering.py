"""Markdown semantics, source safety and paragraph/media placement regressions."""
import copy
import json
import unittest
from html.parser import HTMLParser

from test_build import ROOT, Tags, build


class TableRows(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("th", "td"):
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("th", "td") and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


class DetailsContent(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.inside = []
        self.outside = []
        self.inside_images = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == "details":
            self.depth += 1
        elif tag == "img" and self.depth:
            self.inside_images.append(dict(attrs))

    def handle_endtag(self, tag):
        if tag == "details":
            self.depth -= 1

    def handle_data(self, data):
        (self.inside if self.depth else self.outside).append(data)


def specimen(body="第一段。\n\n第二段。"):
    return {
        "id": "markdown-specimen", "date": "2026-11-07", "title": "中文测试",
        "body_md": body,
        "source": {"url": "https://example.org/source", "author": "Source", "title_en": "Source"},
        "original": {"title": "Original", "lang": "en", "text_md": "Original text.", "media": []},
        "rewrite_media": [],
    }


def with_media(body, anchor):
    a = specimen(body)
    a["original"]["media"] = [{"id": "photo", "type": "image", "url": "https://example.org/photo.jpg"}]
    a["rewrite_media"] = [{"media_id": "photo", "placement": "after_paragraph",
                            "after_md": anchor, "evidence": "source_position_verified"}]
    return a


class MarkdownRendering(unittest.TestCase):
    def test_pricing_table_is_structural_and_preserves_all_values(self):
        a = json.loads((ROOT / "content/articles/simonw-muse-ember-pricing.json").read_text())
        rendered = build.md_to_html(a["body_md"])
        self.assertIn("<table", rendered)
        self.assertEqual(rendered.count("<tr>"), 7)
        for value in ("$0.10", "$0.004", "$0.012", "$2.50", "≤272k", ">100k".replace(">", "&gt;")):
            self.assertIn(value, rendered)

    def test_commonmark_lists_headings_quotes_fences_and_strikethrough(self):
        output = build.md_to_html('''#### Small heading

##### Smaller heading

###### Smallest heading

3. Start at three
4. Continue

- Parent
  - Child with **bold** and *emphasis*

> First quoted paragraph.
>
> Second quoted paragraph.

~~withdrawn~~

```html
<script>literalExample()</script>
  indented code | stays code
```
''')
        doc = Tags(output)
        for tag in ("h4", "h5", "h6", "blockquote", "pre", "code", "strong", "em"):
            self.assertTrue(doc.select(tag), tag)
        self.assertTrue(doc.select("s") or doc.select("del"))
        self.assertEqual(len(doc.select("ul")), 2)
        self.assertTrue(doc.select("ol", start="3"))
        self.assertIn("<p>First quoted paragraph.</p>", output)
        self.assertIn("<p>Second quoted paragraph.</p>", output)
        self.assertIn("&lt;script&gt;literalExample()&lt;/script&gt;", output)
        self.assertIn("  indented code | stays code", output)
        self.assertFalse(doc.select("script"))

    def test_table_alignment_escaped_pipes_and_inline_markup(self):
        output = build.md_to_html(r'''| Left | Center | Right |
| :--- | :---: | ---: |
| a\|b | **strong** | `x\|y` |
''')
        doc = Tags(output)
        self.assertEqual(TableRows(output).rows, [["Left", "Center", "Right"], ["a|b", "strong", "x|y"]])
        self.assertEqual([a.get("align") for a in doc.select("th")], ["left", "center", "right"])
        self.assertEqual([a.get("align") for a in doc.select("td")], ["left", "center", "right"])
        self.assertFalse(any("style" in attrs for _, attrs in doc.tags))

    def test_links_images_and_reference_definitions_use_full_document_context(self):
        output = build.md_to_html('''[Read][paper] and [parentheses](https://example.org/a_(b)).

![A source image][image]

<https://example.org/autolink>

[paper]: https://example.org/paper "Paper title"
[image]: https://example.org/image.png
''')
        doc = Tags(output)
        for url in ("https://example.org/paper", "https://example.org/a_(b)", "https://example.org/autolink"):
            self.assertTrue(doc.select("a", href=url), url)
        self.assertTrue(doc.select("img", src="https://example.org/image.png", alt="A source image"))
        self.assertNotIn("[paper]:", output)

    def test_relative_urls_without_explicit_base_are_not_guessed(self):
        output = build.md_to_html('[relative document](./guide.md)\n\n![relative image](./photo.png)\n\n<a href="/guide">raw relative label</a><img src="../raw.png" alt="raw image">')
        doc = Tags(output)
        self.assertIn("relative document", output)
        self.assertIn("raw relative label", output)
        self.assertTrue(doc.select("img", alt="relative image"))
        for tag, attrs in doc.tags:
            self.assertNotIn("href", attrs, (tag, attrs))
            self.assertNotIn("src", attrs, (tag, attrs))

    def test_raw_html_is_sanitized_without_breaking_safe_structure(self):
        output = build.md_to_html('''<script>doNotExecute()</script>
<style>body{display:none}</style>
<iframe src="https://example.org/embed">doNotEmbed</iframe>
<img src="javascript:bad()" onerror="bad()">
<img src="data:image/svg+xml,evil">
<a href="javascript:bad()" id="rewrite" name="location" onclick="bad()" style="position:fixed">visible label</a>
<details open><summary>Details</summary><p>Safe<br>content</p></details>
<table><tr><td style="position:fixed;text-align:right" onclick="bad()">cell</td></tr></table>
''')
        doc = Tags(output)
        for tag in ("script", "style", "iframe"):
            self.assertFalse(doc.select(tag), tag)
        for tag in ("details", "summary", "br", "table", "td"):
            self.assertTrue(doc.select(tag), tag)
        self.assertNotIn("doNotExecute", output)
        self.assertIn("visible label", output)
        for tag, attrs in doc.tags:
            self.assertFalse(any(k in attrs for k in ("onclick", "onerror", "id", "name", "style")), (tag, attrs))
            for key in ("href", "src"):
                if key in attrs:
                    self.assertTrue(attrs[key].startswith(("https://", "http://", "mailto:")), (tag, attrs))

    def test_source_relative_links_and_picture_keep_the_pinned_revision(self):
        base = "https://github.com/owner/project/blob/fixed-revision/docs/README.md"
        a = specimen()
        a["original"].update({"markdown_base_url": base, "text_md": '''[guide](./guide.md)

![diagram](../images/diagram.png)

<picture><source srcset="../images/dark.svg" media="(prefers-color-scheme: dark)"><img src="../images/light.svg" alt="scheme"></picture>
'''})
        for output in (build.render_original_text(a), build.rss_versions(a)["original"]["html"]):
            doc = Tags(output)
            self.assertTrue(doc.select("a", href=base.replace("README.md", "guide.md")))
            raw = "https://raw.githubusercontent.com/owner/project/fixed-revision/images/"
            self.assertTrue(doc.select("img", src=raw + "diagram.png"))
            self.assertTrue(doc.select("img", src=raw + "light.svg"))
            self.assertTrue(doc.select("source", srcset=raw + "dark.svg"))

    def test_literal_tags_inside_safe_attributes_never_become_markup_or_events(self):
        cases = [
            ('<a title="literal <img onmouseover=alert(1)>" href="https://example.org">label</a>',
             "a", "title", "literal <img onmouseover=alert(1)>"),
            ('<img alt="literal <img onerror=alert(1)>" src="https://example.org/photo.png">',
             "img", "alt", "literal <img onerror=alert(1)>"),
            ('<a title="literal <table>" href="https://example.org">label</a>',
             "a", "title", "literal <table>"),
        ]
        for source, tag, attribute, expected in cases:
            with self.subTest(source=source):
                output = build.md_to_html(source)
                doc = Tags(output)
                self.assertEqual(len(doc.select(tag)), 1)
                self.assertEqual(doc.select(tag)[0].get(attribute), expected)
                self.assertFalse(doc.select("table"))
                if tag == "a":
                    self.assertFalse(doc.select("img"))
                    self.assertEqual(doc.select("a")[0].get("href"), "https://example.org")
                else:
                    self.assertEqual(doc.select("img")[0].get("src"), "https://example.org/photo.png")
                for _, attrs in doc.tags:
                    self.assertFalse(any(key.startswith("on") for key in attrs), attrs)

    def test_reference_link_paragraph_gets_media_after_it_in_html_and_markdown(self):
        anchor = "介绍[原始论文][paper]。"
        body = anchor + "\n\n另一段。\n\n[paper]: https://example.org/paper\n"
        a = with_media(body, anchor)
        for output in (build.render_rewrite(a), build.render_rewrite(a, rss=True), build.rss_versions(a)["rewrite"]["html"]):
            self.assertTrue(Tags(output).select("a", href="https://example.org/paper"))
            self.assertEqual(len(Tags(output).select("img", src="https://example.org/photo.jpg")), 1)
            self.assertLess(output.index("原始论文"), output.index('data-media-id="photo"'))
            self.assertLess(output.index('data-media-id="photo"'), output.index("另一段"))
        md = build.render_rewrite_markdown(a)
        self.assertIn("[paper]: https://example.org/paper", md)
        self.assertLess(md.index(anchor), md.index("https://example.org/photo.jpg"))
        self.assertLess(md.index("https://example.org/photo.jpg"), md.index("另一段"))

    def test_media_insertion_preserves_surrounding_html_container(self):
        body = '''<details>
<summary>Details summary</summary>

First paragraph.

Second paragraph.

<!-- ordinary source comment -->
</details>

Outside paragraph.
'''
        a = with_media(body, "First paragraph.")
        outputs = (build.render_rewrite(a), build.render_rewrite(a, rss=True),
                   build.rss_versions(a)["rewrite"]["html"],
                   build.md_to_html(build.render_rewrite_markdown(a)))
        for output in outputs:
            with self.subTest(output=output[:60]):
                doc = DetailsContent(output)
                self.assertEqual(len(Tags(output).select("details")), 1)
                self.assertIn("First paragraph.", "".join(doc.inside))
                self.assertIn("Second paragraph.", "".join(doc.inside))
                self.assertNotIn("Second paragraph.", "".join(doc.outside))
                self.assertIn("Outside paragraph.", "".join(doc.outside))
                self.assertEqual([img.get("src") for img in doc.inside_images], ["https://example.org/photo.jpg"])
                self.assertLess(output.index("First paragraph."), output.index("https://example.org/photo.jpg"))
                self.assertLess(output.index("https://example.org/photo.jpg"), output.index("Second paragraph."))
                self.assertNotIn("ordinary source comment", output)

    def test_malformed_html_cannot_silently_swallow_anchored_media(self):
        # CommonMark sees a paragraph after the blank line, while the HTML
        # parser still sees an unclosed attribute. Losing its media must fail.
        body = '<div title="\n\nFirst paragraph.\n\n">\n\nAfter.\n\n</div>'
        a = with_media(body, "First paragraph.")
        for render in (build.render_rewrite, lambda item: build.render_rewrite(item, rss=True), build.rss_versions):
            with self.subTest(renderer=render.__name__), self.assertRaisesRegex(ValueError, "media cannot be inserted safely"):
                render(a)

    def test_normalized_anchor_aliases_preserve_all_media_in_reference_order(self):
        anchors = ["First line.\nSecond line.", " First line.\r\nSecond line. ", "\nFirst line.\nSecond line.\n"]
        a = specimen(anchors[0] + "\n\nAfter.")
        urls = ["https://example.org/z-first.jpg", "https://example.org/a-second.jpg", "https://example.org/m-third.jpg"]
        a["original"]["media"] = [{"id": f"photo{i}", "type": "image", "url": url}
                                   for i, url in enumerate(urls)]
        a["rewrite_media"] = [{"media_id": f"photo{i}", "placement": "after_paragraph",
                                "after_md": anchor, "evidence": "source_position_verified"}
                               for i, anchor in enumerate(anchors)]
        for output in (build.render_rewrite(a), build.render_rewrite(a, rss=True), build.rss_versions(a)["rewrite"]["html"]):
            self.assertEqual([img.get("src") for img in Tags(output).select("img")], urls)
            self.assertLess(output.index("Second line."), output.index(urls[0]))
            self.assertLess(output.index(urls[-1]), output.index("After."))
        md = build.render_rewrite_markdown(a)
        for url in urls:
            self.assertEqual(md.count(url), 1)
        self.assertEqual([md.index(url) for url in urls], sorted(md.index(url) for url in urls))
        # The shared renderer must also avoid overwriting aliases when called
        # without build.py's grouping layer.
        markers = {anchor: f"<p>Media marker {i}</p>" for i, anchor in enumerate(anchors)}
        rendered = build.render_markdown(a["body_md"], after_paragraph=markers)
        positions = [rendered.index(f"Media marker {i}") for i in range(3)]
        self.assertEqual(positions, sorted(positions))

    def test_multiline_crlf_paragraph_and_surrounding_whitespace_keep_media_order(self):
        anchor = "第一行。\r\n第二行。"
        a = with_media("\r\n" + anchor + "\r\n\r\n尾段。\r\n", anchor)
        output = build.render_rewrite(a)
        self.assertLess(output.index("第二行"), output.index('data-media-id="photo"'))
        self.assertLess(output.index('data-media-id="photo"'), output.index("尾段"))
        md = build.render_rewrite_markdown(a)
        self.assertTrue(md.startswith("\r\n" + anchor))
        self.assertTrue(md.endswith("尾段。\r\n"))
        self.assertLess(md.index("第二行"), md.index("https://example.org/photo.jpg"))
        self.assertLess(md.index("https://example.org/photo.jpg"), md.index("尾段"))

    def test_trusted_generated_players_survive_markdown_sanitization(self):
        a = specimen("正文段落。\n\n结束段落。")
        a["original"]["media"] = [
            {"id": "video", "type": "video", "url": "https://example.org/video.mp4"},
            {"id": "audio", "type": "audio", "url": "https://example.org/audio.mp3"},
            {"id": "youtube", "type": "youtube", "url": "https://www.youtube.com/watch?v=OrcsMi2-IcM"},
        ]
        a["rewrite_media"] = [{"media_id": media["id"], "placement": "after_paragraph",
                                "after_md": "正文段落。", "evidence": "source_position_verified"}
                               for media in a["original"]["media"]]
        for output, rss in ((build.render_rewrite(a), False), (build.render_rewrite(a, rss=True), True),
                            (build.rss_versions(a)["rewrite"]["html"], True)):
            doc = Tags(output)
            self.assertEqual(len(doc.select("video", src="https://example.org/video.mp4")), 1)
            self.assertEqual(len(doc.select("audio", src="https://example.org/audio.mp3")), 1)
            self.assertEqual(len(doc.select("iframe", src="https://www.youtube-nocookie.com/embed/OrcsMi2-IcM")), 1)
            for attrs in doc.select("video") + doc.select("audio"):
                self.assertIn("controls", attrs)
                self.assertEqual(attrs.get("preload"), "none")
                self.assertNotIn("autoplay", attrs)
            if rss:
                for media in a["original"]["media"]:
                    self.assertTrue(doc.select("a", href=media["url"]))
            else:
                self.assertEqual(len(doc.select("a", href=a["source"]["url"])), 3)
            self.assertLess(output.index("正文段落"), output.index("<video"))
            self.assertLess(output.index("<video"), output.index("<audio"))
            self.assertLess(output.index("<audio"), output.index("<iframe"))
            self.assertLess(output.index("<iframe"), output.index("结束段落"))

    def test_only_unique_top_level_paragraphs_can_anchor_media(self):
        fake = "已核对的完整段落。"
        invalid = [
            ("```md\n\n" + fake + "\n\n```", fake),
            ("> " + fake, "> " + fake),
            ("- " + fake, "- " + fake),
            ("| A | B |\n| --- | --- |\n| C | D |", "| A | B |\n| --- | --- |\n| C | D |"),
            ("## Heading", "## Heading"),
            (fake + "\n\n" + fake, fake),
        ]
        for body, anchor in invalid:
            a = with_media(body, anchor)
            for render in (build.render_rewrite, build.render_rewrite_markdown):
                with self.subTest(body=body, renderer=render.__name__), self.assertRaises(ValueError):
                    render(a)


if __name__ == "__main__":
    unittest.main()
