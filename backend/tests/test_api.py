from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import json
import tempfile
import threading
import unittest

from backend.search import load_listings
from backend.server import make_handler


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.static = Path(cls.directory.name) / "dist"
        cls.static.mkdir()
        (cls.static / "index.html").write_text("<h1>Search</h1>")
        (Path(cls.directory.name) / "private.txt").write_text("Not public")
        (cls.static / "symlink.txt").symlink_to(Path(cls.directory.name) / "private.txt")
        listings = load_listings(Path(__file__).resolve().parents[2] / "sample_listings.json")
        handler = make_handler(listings, cls.static)
        handler.log_message = lambda *args: None
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.directory.cleanup()

    def request(self, path):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_search_contract(self):
        status, headers, body = self.request("/api/listings?city=Reston&pageSize=1&targetBudget=600000")
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["totalPages"], 2)
        self.assertEqual(len(data["items"]), 1)
        self.assertIn("relevanceScore", data["items"][0])
        self.assertIn("asOf", data)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(int(headers["Content-Length"]), len(body))

    def test_validation_returns_structured_400(self):
        for path, field in [("?pageSize=0", "pageSize"), ("?minPrice=20&maxPrice=10", "minPrice"),
                            ("?city=A&city=B", "city"), ("?minPrice=", "minPrice"),
                            ("?minPrice=NaN", "minPrice"), ("?unknown=1", "unknown")]:
            with self.subTest(path=path):
                status, _, body = self.request("/api/listings" + path)
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(body)["error"]["field"], field)

    def test_no_matches_is_a_successful_empty_result(self):
        status, _, body = self.request("/api/listings?city=Atlantis")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["items"], [])

    def test_past_last_page_returns_empty_items_with_total(self):
        status, _, body = self.request("/api/listings?page=99")
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total"], 12)

    def test_health_and_unknown_route(self):
        self.assertEqual(self.request("/api/health")[0], 200)
        self.assertEqual(self.request("/api/missing")[0], 404)

    def test_static_files_and_security_headers(self):
        status, headers, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"<h1>Search</h1>", body)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("object-src 'none'", headers["Content-Security-Policy"])

    def test_static_paths_cannot_escape_build_directory(self):
        for path in ["/../private.txt", "/%2e%2e/private.txt", "/symlink.txt", "/sample_listings.json", "/.env"]:
            with self.subTest(path=path):
                status, _, body = self.request(path)
                self.assertEqual(status, 404)
                self.assertNotIn(b"Not public", body)

    def test_query_parameter_limit(self):
        status, _, body = self.request("/api/listings?" + "&".join(f"x{i}=1" for i in range(31)))
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(body))
