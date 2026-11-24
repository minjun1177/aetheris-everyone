"""Reading pages and searching, against local servers and patched DNS - no internet needed."""

import gzip
import json
import socket
import threading
import unittest
import urllib.parse
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from aetheris_everyone import settings, tools, websearch
from helpers import Sandbox


class LocalSite:
    """A tiny HTTP server on 127.0.0.1; `routes` maps a path to (status, headers, body)."""

    def __init__(self, routes):
        self.seen = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                site.seen.append(self.path)
                status, headers, body = routes.get(urllib.parse.urlsplit(self.path).path,
                                                   (404, {}, b"missing"))
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class PageText(unittest.TestCase):
    def test_readable_text_only(self):
        title, text = websearch.page_text(
            "<html><head><title>제목 &amp; 부제</title><script>var x = 1;</script>"
            "<style>p{}</style></head><body><nav>menu</nav><h1>Heading</h1>"
            "<p>First &lt;para&gt;</p><div>Second</div><footer>foot</footer></body></html>")
        self.assertEqual(title, "제목 & 부제")
        self.assertIn("## Heading", text)
        self.assertIn("First <para>", text)
        self.assertIn("Second", text)
        for hidden in ("var x", "menu", "foot", "p{}"):
            self.assertNotIn(hidden, text)

    def test_broken_markup_does_not_raise(self):
        _, text = websearch.page_text("<p>unclosed <b>bold <div>text")
        self.assertIn("text", text)


class Addresses(unittest.TestCase):
    def test_non_ascii_url_is_encoded(self):
        self.assertEqual(websearch.normalise_url("https://ko.wikipedia.org/wiki/대한민국?q=값 1"),
                         "https://ko.wikipedia.org/wiki/%EB%8C%80%ED%95%9C%EB%AF%BC%EA%B5%AD?q=%EA%B0%92%201")
        self.assertEqual(websearch.normalise_url("http://한국.kr/"), "http://xn--3e0b707e.kr/")
        already = "https://example.com/a%20b?x=%EA%B0%92"
        self.assertEqual(websearch.normalise_url(already), already)

    def test_only_web_addresses(self):
        for url in ("file:///etc/passwd", "ftp://example.com/", "javascript:alert(1)"):
            with self.assertRaises(websearch.BlockedAddress):
                websearch.normalise_url(url)

    def test_private_addresses_are_refused(self):
        for url in ("http://127.0.0.1/", "http://localhost/", "http://10.1.2.3/", "http://192.168.0.2:11434/",
                    "http://[::1]/", "http://169.254.169.254/latest/meta-data/"):
            with self.assertRaises(websearch.BlockedAddress, msg=url):
                websearch.fetch(url)

    def test_connection_goes_to_the_checked_address(self):
        """A name that answers public first and private second (DNS rebinding) is pinned."""
        answers = iter(["93.184.216.34", "127.0.0.1", "127.0.0.1"])
        lookups, connected = [], []
        real_lookup, real_connect = socket.getaddrinfo, socket.create_connection

        def lookup(host, port, *args, **kwargs):
            lookups.append(host)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(answers), port))]

        def connect(address, *args, **kwargs):
            connected.append(address)
            raise ConnectionRefusedError("test stops here")

        socket.getaddrinfo, socket.create_connection = lookup, connect
        try:
            with self.assertRaises(ConnectionRefusedError):
                websearch.fetch("http://rebind.example/")
        finally:
            socket.getaddrinfo, socket.create_connection = real_lookup, real_connect
        self.assertEqual(lookups, ["rebind.example"])
        self.assertEqual(connected, [("93.184.216.34", 80)])

    def test_redirect_to_a_private_address_is_refused(self):
        real = websearch._request
        calls = []

        def first_redirects(url, data, timeout, public, headers=None):
            calls.append(url)
            if len(calls) == 1:
                return 302, _Headers({"Location": "http://10.0.0.1/admin"}), b""
            return real(url, data, timeout, public, headers)

        websearch._request = first_redirects
        try:
            with self.assertRaises(websearch.BlockedAddress):
                websearch.fetch("http://93.184.216.34/")
        finally:
            websearch._request = real
        self.assertEqual(calls[-1], "http://10.0.0.1/admin")


class _Headers(dict):
    def get_content_charset(self):
        return None


class Decompression(unittest.TestCase):
    def test_gzip_bomb_is_capped(self):
        bomb = gzip.compress(b"\0" * (websearch.DECODED_LIMIT * 3))
        self.assertLess(len(bomb), websearch.READ_LIMIT)
        self.assertEqual(len(websearch._decompress(bomb, "gzip")), websearch.DECODED_LIMIT)

    def test_deflate_both_kinds(self):
        wrapped = zlib.compress(b"hello")
        raw = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        raw_data = raw.compress(b"hello") + raw.flush()
        self.assertEqual(websearch._decompress(wrapped, "deflate"), b"hello")
        self.assertEqual(websearch._decompress(raw_data, "deflate"), b"hello")
        self.assertEqual(websearch._decompress(b"plain", ""), b"plain")


class LocalServerPages(unittest.TestCase):
    def setUp(self):
        self.site = LocalSite({
            "/start": (302, {"Location": "/final"}, b""),
            "/final": (200, {"Content-Type": "text/html; charset=utf-8", "Content-Encoding": "gzip"},
                       gzip.compress("<title>끝</title><p>도착</p>".encode())),
            "/euc": (200, {"Content-Type": "text/html"},
                     '<meta charset="euc-kr"><p>한글</p>'.encode("euc-kr")),
        })

    def tearDown(self):
        self.site.close()

    def test_redirect_gzip_and_charset(self):
        final, text = websearch.fetch(self.site.base + "/start", public=False)
        self.assertTrue(final.endswith("/final"))
        self.assertIn("도착", text)
        _, text = websearch.fetch(self.site.base + "/euc", public=False)
        self.assertIn("한글", text)

    def test_non_ascii_path_reaches_the_server_encoded(self):
        with self.assertRaises(websearch.HTTPStatusError):
            websearch.fetch(self.site.base + "/문서", public=False)
        self.assertEqual(self.site.seen[-1], "/%EB%AC%B8%EC%84%9C")


class SearXNG(Sandbox):
    def setUp(self):
        super().setUp()
        results = {"results": [{"title": "Aetheris", "url": "https://example.com/a", "content": "snippet"},
                               {"title": "no url"}]}
        self.site = LocalSite({"/search": (200, {"Content-Type": "application/json"},
                                           json.dumps(results).encode())})
        self.refusing = LocalSite({"/search": (403, {}, b"Forbidden")})

    def tearDown(self):
        self.site.close()
        self.refusing.close()
        super().tearDown()

    def test_search_goes_to_searxng_only(self):
        settings.update({"search_engine": "searxng", "searxng_url": self.site.base})
        self.assertEqual(websearch.engines(), (websearch._searxng,))
        results = websearch.search("한국어 검색")
        self.assertEqual(results, [{"title": "Aetheris", "url": "https://example.com/a", "snippet": "snippet"}])
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.site.seen[-1]).query)
        self.assertEqual(query, {"q": ["한국어 검색"], "format": ["json"]})
        status, text, _ = tools.dispatch(self.context(), "web_search", {"query": "x"})
        self.assertEqual(status, "ok", text)
        self.assertIn("https://example.com/a", text)

    def test_default_engines_without_searxng(self):
        settings.update({"search_engine": "searxng", "searxng_url": ""})
        self.assertNotIn(websearch._searxng, websearch.engines())

    def test_json_turned_off_is_explained(self):
        with self.assertRaises(RuntimeError) as caught:
            websearch.searxng("x", self.refusing.base)
        self.assertIn("settings.yml", str(caught.exception))

    def test_page_reading_still_refuses_the_local_network(self):
        settings.update({"search_engine": "searxng", "searxng_url": self.site.base})
        status, result, _ = tools.dispatch(self.context(), "read_webpage", {"url": self.site.base + "/search"})
        self.assertEqual(status, "error")
        self.assertIn("local network", result)


if __name__ == "__main__":
    unittest.main()


def _tiny_pdf(text: str) -> bytes:
    """A one-page PDF showing `text`, built by hand (offsets included)."""
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return out


class ReadingFiles(unittest.TestCase):
    def setUp(self):
        self.site = LocalSite({
            "/report": (200, {"Content-Type": "application/pdf"}, _tiny_pdf("Quarterly sales grew")),
            "/photo": (200, {"Content-Type": "image/jpeg"}, b"\xff\xd8\xff\xe0\x00\x10JFIF"),
            "/mislabelled": (200, {"Content-Type": "application/octet-stream"},
                             b"<title>Plain</title><p>Readable after all</p>"),
        })

    def tearDown(self):
        self.site.close()

    def test_a_pdf_link_is_read_as_its_text(self):
        try:
            import pypdf  # noqa: F401
        except ImportError:
            self.skipTest("pypdf is not installed")
        text = websearch.read_page(self.site.base + "/report", public=False)
        self.assertIn("PDF document", text)
        self.assertIn("Quarterly sales grew", text)

    def test_a_picture_is_refused_and_a_mislabelled_page_still_read(self):
        with self.assertRaises(ValueError) as caught:
            websearch.read_page(self.site.base + "/photo", public=False)
        self.assertIn("image/jpeg", str(caught.exception))
        self.assertIn("Readable after all", websearch.read_page(self.site.base + "/mislabelled",
                                                                public=False))
