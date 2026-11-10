"""Non-visual regression tests for D, static routes, RSS and immutable source data."""
import importlib.util
import copy
import hashlib
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("xz_build", ROOT / "scripts/build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class Tags(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
    def select(self, tag, **attrs):
        return [a for t, a in self.tags if t == tag and all(a.get(k) == v for k, v in attrs.items())]


def assert_body_in_order(case, article, rendered, *, markdown=False):
    """Media can split the body; every original block must remain in order."""
    cursor = 0
    for block in re.split(r"\n\s*\n", article["body_md"].strip()):
        expected = block if markdown else build.md_to_html(block)
        position = rendered.find(expected, cursor)
        case.assertGreaterEqual(position, 0, f"{article['id']}: missing or reordered body block: {block[:80]}")
        cursor = position + len(expected)


class BuildRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.articles = build.load_articles()
        cls.public = ROOT / "public"
        cls.feed = ET.parse(cls.public / "feed.xml")

    def test_all_ids_and_stable_article_urls(self):
        ids = [a["id"] for a in self.articles]
        self.assertEqual(len(ids), len(set(ids)))
        for a in self.articles:
            self.assertRegex(a["id"], r"^[a-z0-9-]+$")
            page = (self.public / "a" / (a["id"] + ".html")).read_text()
            doc = Tags(page)
            self.assertTrue(doc.select("article", **{"data-article-id": a["id"]}))
            self.assertTrue(doc.select("link", rel="canonical", href=build.SITE_URL + "/a/" + a["id"]))

    def test_complete_static_bodies_and_no_js_navigation(self):
        for a in self.articles:
            page = (self.public / "a" / (a["id"] + ".html")).read_text()
            assert_body_in_order(self, a, page)
            original = (a.get("original") or {}).get("text_md", "")
            if original:
                self.assertIn(build.render_original_text(a), page)
            doc = Tags(page)
            for panel in ("rewrite", "original"):
                self.assertTrue(doc.select("a", href="#" + panel))
                section = doc.select("section", id=panel)[0]
                self.assertNotIn("hidden", section)
            self.assertTrue(doc.select("a", href=a["source"]["url"]))
            ids = [attrs["id"] for _, attrs in doc.tags if "id" in attrs]
            self.assertEqual(len(ids), len(set(ids)))

    def test_rss_item_count_ids_guids_and_full_bodies(self):
        items = self.feed.findall("./channel/item")
        self.assertEqual(len(items), len(self.articles))
        for a, item in zip(self.articles, items):
            url = build.SITE_URL + "/a/" + a["id"]
            self.assertEqual(item.findtext("link"), url)
            self.assertEqual(item.findtext("guid"), url)
            self.assertEqual(item.findtext("title"), a["title"])
            full = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            self.assertEqual(item.findtext("description"), full)
            assert_body_in_order(self, a, full)
            self.assertIn(a["source"]["url"], full)
            original = a.get("original") or {}
            if original.get("text_md"):
                self.assertIn(build.render_original_text(a), full)
            for media in original.get("media") or []:
                if media.get("url"):
                    self.assertIn(media["url"].replace("&", "&amp;"), full)
            if a["source"].get("related_url"):
                self.assertIn(a["source"]["related_url"], full)

    def test_existing_articles_json_contract(self):
        expected = [{"id": a["id"], "date": a["date"], "title": a["title"], "dek": a.get("dek"), "url": "/a/" + a["id"], "source_url": a["source"]["url"], "tags": a.get("tags", [])} for a in self.articles]
        self.assertEqual(json.loads((self.public / "articles.json").read_text()), expected)

    def test_homepage_orders_by_site_ingest_not_original_date(self):
        ids = [a["id"] for a in self.articles]
        self.assertEqual(ids, [a["id"] for a in sorted(self.articles, key=build.ingested_sort_key)])
        home = (self.public / "index.html").read_text()
        for a in self.articles:
            site_day, orig_day = build.ingested_date(a), build.source_date(a)
            self.assertIn(f'datetime="{site_day}"', home)
            if site_day != orig_day:
                self.assertIn("收录 " + build.fmt_short_date(site_day), home)
                self.assertIn("原文 " + build.fmt_short_date(orig_day), home)
            page = (self.public / "a" / (a["id"] + ".html")).read_text()
            self.assertIn("本站收录 " + build.fmt_date(site_day), page)
            self.assertIn("原文发布 " + build.fmt_date(orig_day), page)

    def test_rss_keeps_original_pubdate_while_item_order_follows_ingest(self):
        items = self.feed.findall("./channel/item")
        self.assertEqual([item.findtext("guid") for item in items], [build.SITE_URL + "/a/" + a["id"] for a in self.articles])
        for a, item in zip(self.articles, items):
            self.assertEqual(item.findtext("pubDate"), build.format_datetime(build.parse_dt(a).astimezone(build.timezone.utc)))
        sample = copy.deepcopy(self.articles[-1])
        sample["title"] = sample["title"] + "（校对）"
        sample["body_md"] = sample["body_md"] + "\n\n校对备注。"
        resorted = sorted([sample] + [a for a in self.articles if a["id"] != sample["id"]], key=build.ingested_sort_key)
        self.assertEqual([a["id"] for a in resorted], [a["id"] for a in self.articles])

    def test_missing_or_invalid_ingested_at_sorts_predictably(self):
        valid = {"id": "z-valid", "ingested_at": "2026-11-08T08:00:00+08:00"}
        missing = {"id": "a-missing"}
        bad = {"id": "b-bad", "ingested_at": "not-a-date"}
        ordered = sorted([valid, missing, bad], key=build.ingested_sort_key)
        self.assertEqual([a["id"] for a in ordered], ["z-valid", "a-missing", "b-bad"])

    def test_chronological_cards_and_source_only_covers(self):

        doc = Tags((self.public / "index.html").read_text())
        cards = [attrs for t, attrs in doc.tags if t == "a" and "data-open-reader" in attrs]
        self.assertEqual([a["href"] for a in cards], ["/a/" + a["id"] for a in self.articles])
        expected_covers = {build.cover_asset(a)[0] for a in self.articles if build.cover_asset(a)[0]}
        self.assertEqual({a["src"] for a in doc.select("img")}, expected_covers)
        self.assertNotIn('class="sidebar"', (self.public / "index.html").read_text())
        for a in self.articles:
            if not build.cover_asset(a)[0]:
                card = build.build_feed_items([a])
                self.assertNotIn("<img", card)
                self.assertIn("type-cover", card)

    def test_media_never_autoplay_and_has_original_fallback(self):
        for a in self.articles:
            page = (self.public / "a" / (a["id"] + ".html")).read_text()
            doc = Tags(page)
            for tag, attrs in doc.tags:
                if tag in ("video", "audio"):
                    self.assertNotIn("autoplay", attrs)
                    self.assertIn("controls", attrs)
                    self.assertEqual(attrs.get("preload"), "none")
                if tag == "iframe":
                    self.assertNotIn("autoplay", attrs.get("allow", ""))
                    self.assertNotIn("autoplay=1", attrs.get("src", ""))
                    self.assertEqual(attrs.get("loading"), "lazy")
            if (a.get("original") or {}).get("media"):
                self.assertIn("无法显示？去原文查看", page)


    def test_every_source_media_accounted_for_in_rewrite_and_full_rss(self):
        for a in self.articles:
            available, refs = build.rewrite_media_plan(a)
            ui = build.render_rewrite(a)
            full = build.rss_full_html(a)
            rss_rewrite = full.split("<h2>原文</h2>")[0]
            doc, rss_doc = Tags(ui), Tags(rss_rewrite)
            for ref in refs:
                mid = ref["media_id"]
                if "omit_reason" in ref:
                    self.assertIn(ref["omit_reason"], ui)
                    self.assertIn(ref["omit_reason"], rss_rewrite)
                else:
                    self.assertEqual(len(doc.select("figure", **{"data-media-id": mid})), 1)
                    self.assertEqual(len(rss_doc.select("figure", **{"data-media-id": mid})), 1)
                    self.assertIn(available[mid]["url"].replace("&", "&amp;"), rss_rewrite)
            self.assertEqual(len(refs), len(available))
            self.assertNotIn('src="/media/', full)
            self.assertNotIn('poster="/media/', full)

    def test_source_cache_is_small_verified_image_bytes_and_rendering_only(self):
        manifest = json.loads((ROOT / "src/media-manifest.json").read_text())
        self.assertLess(sum(asset["bytes"] for asset in manifest["assets"]), 1024 * 1024)
        for asset in manifest["assets"]:
            file = self.public / asset["local_url"].lstrip("/")
            data = file.read_bytes()
            if asset["content_type"] == "image/webp":
                self.assertTrue(data.startswith(b"RIFF") and data[8:12] == b"WEBP")
                self.assertEqual(asset["transformation"], "Resize to maximum 1920 pixels and encode WebP quality 88")
            else:
                self.assertTrue(data.startswith(b"\xff\xd8\xff"))
            self.assertEqual(len(data), asset["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), asset["sha256"])
            self.assertEqual(build.local_media_url(asset["source_url"]), asset["local_url"])
        self.assertEqual(build.local_media_url("https://example.invalid/unfetched.jpg"), "https://example.invalid/unfetched.jpg")
        for a in self.articles:
            html = build.render_media_html((a.get("original") or {}).get("media") or [], a["source"]["url"])
            doc = Tags(html)
            for media in (a.get("original") or {}).get("media") or []:
                if media["type"] == "image":
                    self.assertTrue(doc.select("img", src=build.local_media_url(media["url"]), **{"data-original-src": media["url"]}))
                if media["type"] in ("video", "x_video"):
                    video = doc.select("video", src=media["url"])[0]
                    self.assertEqual(video.get("poster"), build.local_media_url(media["poster"]))
                    self.assertEqual(video.get("data-original-poster"), media["poster"])

    def media_fixture(self):
        return {"id": "test-only-multimodal", "source": {"url": "https://example.invalid/source"},
                "body_md": "引言。\n\n已核对的完整段落。\n\n结尾。", "original": {"media": [
                    {"id": "image_one", "type": "image", "url": "https://example.invalid/source.jpg"},
                    {"id": "audio_one", "type": "audio", "url": "https://example.invalid/source.mp3"}]},
                "rewrite_media": [
                    {"media_id": "image_one", "placement": "after_paragraph", "after_md": "已核对的完整段落。", "evidence": "source_position_verified"},
                    {"media_id": "audio_one", "placement": "after_paragraph", "after_md": "已核对的完整段落。", "evidence": "source_position_verified"}]}

    def test_semantic_positions_order_audio_and_per_section_deduplication(self):
        a = self.media_fixture()
        for rendered in (build.render_rewrite(a), build.render_rewrite(a, rss=True)):
            self.assertLess(rendered.index("引言"), rendered.index("已核对"))
            self.assertLess(rendered.index("已核对"), rendered.index('data-media-id="image_one"'))
            self.assertLess(rendered.index('data-media-id="image_one"'), rendered.index('data-media-id="audio_one"'))
            self.assertLess(rendered.index('data-media-id="audio_one"'), rendered.index("结尾"))
            self.assertEqual(len(Tags(rendered).select("audio")), 1)
            self.assertNotIn("autoplay", rendered)
        duplicate = [a["original"]["media"][0]] * 2
        self.assertEqual(len(Tags(build.render_media_html(duplicate)).select("figure")), 1)
        self.assertEqual(len(Tags(build.rss_media_html(duplicate)).select("figure")), 1)
        self.assertEqual(build.media_id({"type": "audio", "url": "same"}), build.media_id({"url": "same", "type": "audio"}))

    def test_missing_duplicate_unknown_empty_omission_and_false_precision_fail(self):
        original = self.media_fixture()
        variants = []
        missing = copy.deepcopy(original); missing["rewrite_media"].pop(); variants.append(missing)
        duplicate = copy.deepcopy(original); duplicate["rewrite_media"].append(duplicate["rewrite_media"][0]); variants.append(duplicate)
        unknown = copy.deepcopy(original); unknown["rewrite_media"][0]["media_id"] = "absent"; variants.append(unknown)
        empty = copy.deepcopy(original); empty["rewrite_media"][0] = {"media_id": "image_one", "omit_reason": " "}; variants.append(empty)
        wrong = copy.deepcopy(original); wrong["rewrite_media"][0]["after_md"] = "并不存在的段落"; variants.append(wrong)
        invented = copy.deepcopy(original); invented["rewrite_media"][0]["evidence"] = "source_metadata_only"; variants.append(invented)
        ambiguous = copy.deepcopy(original); ambiguous["body_md"] += "\n\n已核对的完整段落。"; variants.append(ambiguous)
        for a in variants:
            with self.assertRaises(ValueError): build.render_rewrite(a)
        omitted = copy.deepcopy(original)
        omitted["rewrite_media"][0] = {"media_id": "image_one", "omit_reason": "测试用明确遗漏说明，不是发布素材"}
        self.assertIn("测试用明确遗漏说明", build.render_rewrite(omitted))
        self.assertIn("测试用明确遗漏说明", build.render_rewrite(omitted, rss=True))
        self.assertEqual(omitted["original"], original["original"])

    def test_prompt_and_schema_publish_the_multimodal_contract(self):
        prompt = (ROOT / "content/EDITORIAL_PROMPT.md").read_text()
        schema = (ROOT / "content/SCHEMA.md").read_text()
        for token in ("rewrite_media", "after_paragraph", "after_body", "omit_reason", "source_metadata_only", "RSS"):
            self.assertIn(token, prompt); self.assertIn(token, schema)
        self.assertIn("不要发明字幕", prompt)
        self.assertIn("source_position_verified", schema)


    def test_excerpt_label_is_rendered_when_marked(self):
        sample = {"id": "excerpt", "date": "2026-11-06", "title": "视频摘录", "source": {"type": "youtube", "url": "https://www.youtube.com/watch?v=OrcsMi2-IcM"}, "body_md": "正文。", "original": {"text_md": "Excerpt.", "completeness": "excerpt"}}
        self.assertIn("非完整逐字稿", build.render_article(sample))
        self.assertIn("非完整逐字稿", build.rss_full_html(sample))

    def test_asset_sources_survive_rebuild(self):
        self.assertEqual((self.public / "app.css").read_text(), (ROOT / "src/site.css").read_text())
        self.assertEqual((self.public / "app.js").read_text(), (ROOT / "src/site.js").read_text())

    def test_branding_has_no_upstream_identity_or_third_party_scripts(self):
        for page in list(self.public.rglob("*.html")) + [self.public / "feed.xml", self.public / "sitemap.xml", self.public / "robots.txt"]:
            text = page.read_text()
            for banned in ("qiaomu", "乔木", "X News", "umami", "vista8", "xnews.qiaomu.ai"):
                self.assertNotIn(banned, text, f"{page.name}: {banned}")
            for attrs in Tags(text).select("script"):
                self.assertFalse(attrs.get("src", "").startswith("http"), page.name)
        self.assertEqual((self.public / "CNAME").read_text().strip(), "news.nofeetbird.tech")
        self.assertTrue((self.public / ".nojekyll").exists())
        about = (self.public / "about.html").read_text()
        self.assertIn("joeseesun/xnews", about)
        self.assertIn("MIT", about)
        self.assertIn('xmlns:xinzhi="https://news.nofeetbird.tech/ns/rss/1.0"', (self.public / "feed.xml").read_text())

    def test_rehosted_media_exists_and_matches_recorded_checksum(self):
        for a in self.articles:
            for m in (a.get("original") or {}).get("media") or []:
                if m.get("url", "").startswith(build.SITE_URL + "/media/"):
                    local = self.public / m["url"][len(build.SITE_URL) + 1:]
                    self.assertTrue(local.is_file(), m["url"])
                    self.assertIn(hashlib.sha256(local.read_bytes()).hexdigest(), m.get("source_note", ""))

    def test_responsive_css_and_motion_contract(self):
        css = (ROOT / "src/site.css").read_text()
        for required in ["@media(max-width:1050px)", "@media(max-width:680px)", "prefers-reduced-motion", "pointer:fine", "grid-template-columns:minmax(0,1fr)", "overscroll-behavior:contain", "100dvh", "font-style:normal"]:
            self.assertIn(required, css)
        self.assertNotRegex(css, r"font-style\s*:\s*italic|transition\s*:\s*all")
        # Compact tracking is intentional on the Latin wordmark and author covers only.
        for selector, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            if re.search(r"letter-spacing\s*:\s*-", declarations):
                self.assertIn(selector.strip(), {".brand-name", ".card--text .cover-word"})
        self.assertNotIn("grid-auto-flow:dense", css)

    def test_rss_cdata_edge_and_media_variants(self):
        sample = {"id": "test-escape", "date": "2026-11-06", "title": "测试 & 样例", "source": {"type": "web", "url": "https://example.com/?a=1&b=2"}, "body_md": "保留完整正文。 ]]> &", "original": {"text_md": "Original full text.", "media": [{"type": "audio", "url": "https://example.com/audio.mp3"}, {"type": "video", "url": "https://example.com/video.mp4"}]}}
        sample["rewrite_media"] = [{"media_id": build.media_id(m), "placement": "after_body", "placement_note": "测试用来源媒体区块", "evidence": "source_metadata_only"} for m in sample["original"]["media"]]
        feed = ET.fromstring(build.build_rss([sample]))
        full = feed.findtext("./channel/item/{http://purl.org/rss/1.0/modules/content/}encoded")
        self.assertIn("Original full text.", full)
        self.assertIn("audio.mp3", full)
        self.assertIn("video.mp4", full)
        self.assertIn("a=1&amp;b=2", full)
        self.assertNotIn("autoplay", build.render_article(sample))

    def test_missing_original_is_honest_and_recoverable(self):
        sample = {"id": "missing", "date": "2026-11-06", "title": "已有中文正文", "source": {"type": "web", "url": "https://example.com/"}, "body_md": "正文没有丢失。"}
        page = build.render_article(sample)
        self.assertIn("暂未保存原文文字", page)
        self.assertIn("正文没有丢失", page)
        self.assertIn('href="https://example.com/"', page)
        self.assertIn("还没有文章", build.build_feed_items([]))


if __name__ == "__main__":
    unittest.main()
