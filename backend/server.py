"""Serve the listing API and the built React app with Python's standard library."""

import argparse
from contextlib import suppress
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .search import SearchQuery, ValidationError, load_listings, search_listings

ROOT = Path(__file__).resolve().parent.parent


def make_handler(listings, static_dir: Path):
    static_dir = static_dir.resolve()

    class Handler(BaseHTTPRequestHandler):
        def send_body(self, status: int, body: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            # The browser may cancel a search when a new one starts.
            with suppress(BrokenPipeError, ConnectionResetError):
                self.end_headers()
                self.wfile.write(body)

        def send_json(self, status: int, data: dict):
            body = json.dumps(data, allow_nan=False).encode()
            self.send_body(status, body, "application/json; charset=utf-8")

        def send_json_error(self, status: int, message: str, **details: str):
            self.send_json(status, {"error": {"message": message, **details}})

        def send_frontend(self, request_path: str):
            filename = unquote(request_path).lstrip("/") or "index.html"
            path = (static_dir / filename).resolve()
            if path.is_relative_to(static_dir) and path.is_file():
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self.send_body(200, path.read_bytes(), content_type)
            else:
                self.send_json_error(404, "File not found. Build the UI with npm run build.")

        def do_GET(self):
            try:
                url = urlsplit(self.path)
                if url.path == "/api/listings":
                    params = parse_qs(url.query, keep_blank_values=True, max_num_fields=30)
                    query = SearchQuery.parse(params)
                    today = datetime.now(timezone.utc).date()
                    self.send_json(200, search_listings(listings, query, today))
                elif url.path == "/api/health":
                    self.send_json(200, {"status": "ok"})
                elif url.path.startswith("/api/"):
                    self.send_json_error(404, "API endpoint not found.")
                else:
                    self.send_frontend(url.path)
            except ValidationError as error:
                self.send_json_error(400, str(error), field=error.field)
            except ValueError:
                self.send_json_error(400, "Malformed request or too many query parameters.")

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Run Search on localhost.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address; use 0.0.0.0 only inside the container.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    listings = load_listings(ROOT / "sample_listings.json")
    handler = make_handler(listings, ROOT / "dist")
    with ThreadingHTTPServer((args.host, args.port), handler) as server, suppress(KeyboardInterrupt):
        print(f"Search at http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()
