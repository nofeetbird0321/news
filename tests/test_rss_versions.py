"""Wire-format tests for independently readable original and published rewrite."""
import html
import json
import unittest
from xml.etree import ElementTree as ET

from test_build import Tags, build, assert_body_in_order

VERSIONS = "{https://news.nofeetbird.tech/ns/rss/1.0}versions"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"


def payload(article):
    item = ET.fromstring(build.build_rss([article])).find("./channel/item")
    return json.loads(item.findtext(VERSIONS)), item


def specimen():
    return {
        "id": "version-specimen", "date": "2026-11-06",
        "title": "独立的改写标题", "body_md": "第一段中文改写。\n\n第二段中文改写。",
        "source": {"url": "https://example.com/source?a=1&b=2", "author": "Author", "title_en": "Source title"},
        "original": {"title": "Original title", "lang": "en", "text_md": "An independent original paragraph.", "media": []},
        "rewrite_media": [],
    }


class RssVersions(unittest.TestCase):
    def test_actual_corpus_isolation_and_exact_contract(self):
        articles = build.load_articles()
        self.assertGreaterEqual(len(articles), 3)
        feed = ET.fromstring(build.build_rss(articles))
        for a, item in zip(articles, feed.findall("./channel/item")):
            with self.subTest(article=a["id"]):
                self.assertEqual(len(item.findall(VERSIONS)), 1)
                p = json.loads(item.findtext(VERSIONS))
                self.assertEqual(set(p), {"version", "original", "rewrite"})
                self.assertEqual(p["version"], 1)
                self.assertEqual(set(p["original"]), {"title", "url", "lang", "html"})
                self.assertEqual(set(p["rewrite"]), {"title", "markdown", "html"})
                self.assertTrue(all(isinstance(v, str) for section in (p["original"], p["rewrite"]) for v in section.values()))
                self.assertEqual(p["original"]["title"], a["original"]["title"])
                self.assertEqual(p["original"]["url"], a["source"]["url"])
                self.assertEqual(p["original"]["lang"], a["original"]["lang"])
                self.assertEqual(p["rewrite"]["title"], a["title"])
                assert_body_in_order(self, a, p["rewrite"]["markdown"], markdown=True)
                assert_body_in_order(self, a, p["rewrite"]["html"])
                self.assertNotIn(build.md_to_html(a["body_md"]), p["original"]["html"])
                original = a["original"]["text_md"]
                self.assertIn(build.render_original_text(a), p["original"]["html"])
                self.assertNotIn(build.render_original_text(a), p["rewrite"]["html"])
                self.assertNotIn(original.strip(), p["rewrite"]["markdown"])
                for media in a["original"].get("media", []):
                    if media.get("url"):
                        self.assertIn(html.escape(media["url"], quote=True), p["original"]["html"])
                        self.assertIn(html.escape(media["url"], quote=True), p["rewrite"]["html"])
                        self.assertIn(media["url"], p["rewrite"]["markdown"])
                # Legacy readers still receive both complete versions.
                self.assertEqual(item.findtext("description"), item.findtext(CONTENT))
                self.assertEqual(item.findtext(CONTENT), build.rss_full_html(a))
                self.assertEqual(item.findtext("guid"), build.SITE_URL + "/a/" + a["id"])

    def test_missing_original_never_uses_rewrite(self):
        for original in ({}, {"text_md": " \n ", "completeness": "partial"}):
            a = specimen()
            a["original"] = original
            p, _ = payload(a)
            self.assertEqual(p["original"]["title"], "Source title")
            self.assertEqual(p["original"]["lang"], "und")
            self.assertIn("暂未保存原文文字", p["original"]["html"])
            self.assertNotIn("第一段中文改写", p["original"]["html"])
            del a["source"]["title_en"]
            self.assertEqual(payload(a)[0]["original"]["title"], "Original source")

    def test_excerpt_notice_survives_separation(self):
        a = specimen()
        a["original"]["completeness"] = "excerpt"
        a["source"]["type"] = "youtube"
        p, _ = payload(a)
        self.assertIn("非完整逐字稿", p["original"]["html"])
        self.assertIn("independent original paragraph", p["original"]["html"])

    def test_embedded_media_and_fallbacks_in_both_html_versions(self):
        a = specimen()
        media = [
            {"id": "img", "type": "image", "url": "https://example.com/photo.jpg", "alt": "Photo"},
            {"id": "vid", "type": "video", "url": "https://example.com/clip.mp4", "poster": "https://example.com/poster.jpg"},
            {"id": "xvid", "type": "x_video", "url": "https://example.com/x.mp4"},
            {"id": "sound", "type": "audio", "url": "https://example.com/audio.mp3"},
            {"id": "yt", "type": "youtube", "url": "https://www.youtube.com/watch?v=OrcsMi2-IcM"},
            {"id": "future", "type": "future-format", "url": "https://example.com/file"},
        ]
        a["original"]["media"] = media
        a["rewrite_media"] = [{"media_id": m["id"], "placement": "after_body", "evidence": "source_metadata_only", "placement_note": "原帖附件，位置未核验。"} for m in media]
        p, _ = payload(a)
        for section in ("original", "rewrite"):
            doc = Tags(p[section]["html"])
            self.assertEqual(len(doc.select("img")), 1)
            self.assertEqual(len(doc.select("video")), 2)
            self.assertEqual(len(doc.select("audio")), 1)
            for attrs in doc.select("video") + doc.select("audio"):
                self.assertIn("controls", attrs)
                self.assertEqual(attrs["preload"], "none")
                self.assertNotIn("autoplay", attrs)
            self.assertEqual(doc.select("video")[0]["poster"], media[1]["poster"])
            self.assertTrue(doc.select("iframe", src="https://www.youtube-nocookie.com/embed/OrcsMi2-IcM"))
            for m in media:
                self.assertEqual(len(doc.select("a", href=m["url"])), 1)
        self.assertIn("![Photo](<https://example.com/photo.jpg>)", p["rewrite"]["markdown"])
        for m in media:
            self.assertIn(m["url"], p["rewrite"]["markdown"])

    def test_media_placement_omission_and_whitespace(self):
        a = specimen()
        a["body_md"] = "\n第一段中文改写。\n\n第二段中文改写。\n"
        a["original"]["media"] = [{"id": "img", "type": "image", "url": "https://example.com/a.jpg"}, {"id": "lost", "type": "audio"}]
        a["rewrite_media"] = [
            {"media_id": "img", "placement": "after_paragraph", "after_md": "第一段中文改写。", "evidence": "source_position_verified"},
            {"media_id": "lost", "omit_reason": "音频地址缺失，无法展示。"},
        ]
        p, _ = payload(a)
        md = p["rewrite"]["markdown"]
        self.assertTrue(md.startswith("\n第一段中文改写。"))
        self.assertLess(md.index("第一段"), md.index("https://example.com/a.jpg"))
        self.assertLess(md.index("https://example.com/a.jpg"), md.index("第二段"))
        self.assertEqual(md.count("https://example.com/a.jpg"), 1)
        self.assertIn("音频地址缺失，无法展示。", md)
        self.assertIn("音频地址缺失，无法展示。", p["rewrite"]["html"])
        self.assertIn("媒体地址缺失", p["original"]["html"])

    def test_json_cdata_and_markdown_labels_are_escaped(self):
        a = specimen()
        a["title"] = '改写 ]]> " & <title>'
        a["original"]["title"] = 'Source ]]> " & <title>'
        a["body_md"] += '\n\nLiteral ]]> and "quoted" text.'
        a["original"]["media"] = [{"id": "img", "type": "image", "url": "https://example.com/a b>c.jpg", "alt": "[label](bad) <script>\nnext"}]
        a["rewrite_media"] = [{"media_id": "img", "placement": "after_body", "evidence": "source_metadata_only", "placement_note": "Text <script>"}]
        p, item = payload(a)
        self.assertEqual(item.findtext("title"), a["title"])
        self.assertEqual(p["rewrite"]["title"], a["title"])
        self.assertEqual(p["original"]["title"], a["original"]["title"])
        self.assertIn("Literal ]]>", p["rewrite"]["markdown"])
        self.assertIn("https://example.com/a%20b%3Ec.jpg", p["rewrite"]["markdown"])
        self.assertNotIn("<script>", p["rewrite"]["markdown"])
        self.assertIn(r"\[label\]", p["rewrite"]["markdown"])

    def test_unaccounted_media_rejected(self):
        a = specimen()
        a["original"]["media"] = [{"id": "img", "type": "image", "url": "https://example.com/a.jpg"}]
        with self.assertRaisesRegex(ValueError, "missing from rewrite_media"):
            payload(a)


if __name__ == "__main__":
    unittest.main()
