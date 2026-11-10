#!/usr/bin/env python3
"""Local, read-only preview of public/ with the production clean article URLs."""
from argparse import ArgumentParser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
QA_FIXTURE = ROOT / "qa" / "mobile.html"


class Handler(SimpleHTTPRequestHandler):
    def send_head(self):
        original = self.path
        url = urlsplit(self.path)
        path = url.path.rstrip("/")
        # This route exists only in this loopback preview server; fixture is outside public/.
        if path == "/__qa/mobile" and QA_FIXTURE.is_file():
            body = QA_FIXTURE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Robots-Tag", "noindex, noarchive")
            self.end_headers()
            from io import BytesIO
            return BytesIO(body)
        candidate = Path(super().translate_path(path + ".html"))
        if path and not Path(path).suffix and candidate.is_file():
            self.path = urlunsplit(("", "", path + ".html", url.query, ""))
        try:
            return super().send_head()
        finally:
            self.path = original

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def list_directory(self, path):
        self.send_error(404)
        return None

    def send_error(self, code, message=None, explain=None):
        if code == 404 and (PUBLIC / "404.html").is_file():
            body = (PUBLIC / "404.html").read_bytes()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        return super().send_error(code, message, explain)


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=str(PUBLIC)))
    print(f"XZ_PREVIEW_URL::http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
