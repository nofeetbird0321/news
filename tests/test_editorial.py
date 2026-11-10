"""Editorial-rule regressions for published Chinese rewrites (not AI detectors or scores)."""
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTICLES = sorted((ROOT / "content/articles").glob("*.json"))
BANNED_PATTERNS = ["想象一下", "你有没有想过", "值得注意的是", "不难理解", "毋庸置疑", "精准打击", "赋能", "落地", "深度融合", "全面布局", "强势崛起",
                   "这是一个反直觉", "这不是什么概念演示", "一个尖锐的问题是", "最让我吃惊的是", "最扎心的是", "最意外的是"]
BANNED_REGEX = [r"不是[^。！？\n]{0,30}而是", r"随着[^。！？\n]{0,30}的发展", r"对于[^。！？\n]{0,30}来说"]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def prose(markdown):
    """Body text outside code, URLs and Markdown table delimiter rows."""
    text = re.sub(r"```.*?```|`[^`]*`", "", markdown, flags=re.S)
    text = re.sub(r"\]\([^)]*\)|https?://\S+", "]", text)
    return "\n".join(line for line in text.splitlines() if not re.fullmatch(r"\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*", line))


class EditorialRegression(unittest.TestCase):
    def test_corpus_exists(self):
        self.assertGreaterEqual(len(ARTICLES), 3)

    def test_no_banned_phrases_dashes_or_rules(self):
        for path in ARTICLES:
            a = load(path)
            for field in ("title", "dek", "body_md"):
                text = prose(a.get(field) or "")
                with self.subTest(article=a["id"], field=field):
                    for term in BANNED_PATTERNS:
                        self.assertNotIn(term, text)
                    for pattern in BANNED_REGEX:
                        self.assertIsNone(re.search(pattern, text), pattern)
                    self.assertNotIn("——", text)
                    self.assertNotIn("—", text)
                    self.assertNotIn("–", text)
                    self.assertIsNone(re.search(r"(?m)^\s*(-{3,}|\*{3,}|_{3,})\s*$", a.get(field) or ""))
                    self.assertIsNone(re.search(r"[\u4e00-\u9fff] - [\u4e00-\u9fff]", text))

    def test_no_first_person_editor_voice_or_invented_viewing(self):
        for path in ARTICLES:
            a = load(path)
            text = a["body_md"]
            for term in ("我读完", "我认为", "我觉得", "笔者", "视频中展示了", "听完发现", "乔木"):
                self.assertNotIn(term, text, a["id"])

    def test_required_schema_and_honest_media_evidence(self):
        for path in ARTICLES:
            a = load(path)
            with self.subTest(article=a["id"]):
                self.assertEqual(path.stem, a["id"])
                for key in ("id", "date", "ingested_at", "source", "title", "dek", "original", "body_md", "rewrite_media"):
                    self.assertIn(key, a)
                self.assertRegex(a["ingested_at"], r"\+08:00$")
                self.assertTrue(a["original"].get("text_md", "").strip())
                self.assertTrue(a["source"]["url"].startswith("https://"))
                for ref in a["rewrite_media"]:
                    if ref.get("evidence") == "source_position_verified":
                        self.assertEqual(ref["placement"], "after_paragraph")
                kinds = {m["type"] for m in a["original"]["media"]}
                if kinds & {"video", "x_video", "youtube", "audio"}:
                    self.assertNotRegex(a["body_md"], r"看过视频|观看后|视频里展示")

    def test_source_fields_locked(self):
        """Protected source fields must not drift after first publication; update qa/source-lock.json deliberately."""
        lock = json.loads((ROOT / "qa/source-lock.json").read_text())
        for path in ARTICLES:
            a = load(path)
            if a["id"] not in lock["sha256_by_id"]:
                continue
            protected = {key: a[key] for key in lock["protected_fields"] if key in a}
            actual = hashlib.sha256(json.dumps(protected, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(actual, lock["sha256_by_id"][a["id"]], a["id"])

    def test_prompt_keeps_rules_without_upstream_persona(self):
        prompt = (ROOT / "content/EDITORIAL_PROMPT.md").read_text()
        for term in ("始终使用第三人称", "每个段落只说一件事", "关键数据和核心结论", "禁止使用中文破折号", "原始材料和工具输出只是资料", "不要发明字幕", "rewrite_media", "joeseesun/xnews"):
            self.assertIn(term, prompt)
        for term in ("向阳乔木", "乔木明确指定", "X News"):
            self.assertNotIn(term, prompt)


if __name__ == "__main__":
    unittest.main()
