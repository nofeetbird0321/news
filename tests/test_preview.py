"""Read-only local HTTP/fixture checks, not browser or mobile visual verification."""
import importlib.util
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("xz_preview", ROOT / "scripts/preview.py")
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)

class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(preview.Handler, directory=str(preview.PUBLIC)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=2)

    def test_qa_fixture_and_real_routes_are_served_from_the_same_origin(self):
        with urlopen(self.base + "/__qa/mobile") as response:
            fixture = response.read().decode()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["X-Robots-Tag"], "noindex, noarchive")
        class Frames(HTMLParser):
            def __init__(self): super().__init__(); self.frames = []
            def handle_starttag(self, tag, attrs):
                if tag == "iframe": self.frames.append(dict(attrs))
        parser = Frames(); parser.feed(fixture)
        self.assertEqual([int(f["width"]) for f in parser.frames], [320, 390, 768] * 2)
        for frame in parser.frames:
            self.assertTrue(frame["src"].startswith("/"))
            with urlopen(self.base + frame["src"]) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("data-open-reader" if frame["src"] == "/" else "data-article-id", response.read().decode())
        self.assertNotIn("transform:scale", fixture)

    def test_fixture_is_not_a_deploy_asset_and_unknown_routes_stay_404(self):
        self.assertTrue((ROOT / "qa/mobile.html").is_file())
        self.assertFalse((ROOT / "public/__qa").exists())
        self.assertFalse((ROOT / "public/qa").exists())
        with self.assertRaises(HTTPError) as error: urlopen(self.base + "/__qa/not-a-fixture")
        self.assertEqual(error.exception.code, 404)

    def test_every_clean_article_and_small_local_asset_returns_200(self):
        for file in (ROOT / "public/a").glob("*.html"):
            with urlopen(self.base + "/a/" + file.stem) as response: self.assertEqual(response.status, 200)
        for file in (ROOT / "public/media").glob("*.jpg"):
            with urlopen(self.base + "/media/" + file.name) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get_content_type(), "image/jpeg")
                self.assertEqual(response.read(), file.read_bytes())
