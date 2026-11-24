"""Searching the web and reading a page.

Searching goes through the person's own SearXNG when they set one up in
Settings. Otherwise it uses the `ddgs` package when it is installed; if it is
not, or it fails, two search engines' plain HTML pages are read in turn
(DuckDuckGo, then Bing), so one that is down or asks for a captcha does not end
it. A page is reduced to its readable text.

Neither will fetch an address on this computer or its local network: a web
page could otherwise tell the AI to. The address is looked up once, checked,
and the connection is made to exactly that checked address, so a name that
answers differently the second time (DNS rebinding) cannot slip through. The
only exception is the SearXNG address the person typed in themselves.
"""

import base64
import html
import http.client
import ipaddress
import json
import re
import socket
import urllib.parse
import zlib
from html.parser import HTMLParser

from aetheris_everyone import documents, providers, settings

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
PAGE_LIMIT = 15_000
READ_LIMIT = 5_000_000          # bytes read from the network
DECODED_LIMIT = 10_000_000      # bytes after decompression (a small download can unpack huge)
MAX_REDIRECTS = 5


class BlockedAddress(ValueError):
    pass


class HTTPStatusError(RuntimeError):
    def __init__(self, status: int):
        super().__init__(f"the server answered HTTP {status}")
        self.status = status


def normalise_url(url: str) -> str:
    """`url` as plain ASCII: the host in IDNA, everything else percent-encoded.

    Addresses like https://ko.wikipedia.org/wiki/대한민국 cannot be sent as they
    are - the request line must be ASCII.
    """
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise BlockedAddress("only http and https web addresses can be opened")
    try:
        host = parsed.hostname.encode("idna").decode("ascii")
    except UnicodeError:
        raise BlockedAddress(f"the address {parsed.hostname} is not a valid web address") from None
    if ":" in host:
        host = f"[{host}]"
    netloc = host + (f":{parsed.port}" if parsed.port else "")
    path = urllib.parse.quote(parsed.path, safe="/%:@!$&'()*+,;=-._~")
    query = urllib.parse.quote(parsed.query, safe="=&%/:?+@,;!$'()*-._~")
    fragment = urllib.parse.quote(parsed.fragment, safe="=&%/:?+@,;!$'()*-._~#")
    return urllib.parse.urlunsplit((parsed.scheme, netloc, path or "/", query, fragment))


def resolve(url: str, public: bool = True) -> str:
    """The one IP address to connect to for `url`, refused if it is not public."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise BlockedAddress("only http and https web addresses can be opened")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(parsed.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise BlockedAddress(f"the address {parsed.hostname} could not be found") from None
    addresses = [info[4][0].split("%")[0] for info in infos]
    if public and any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise BlockedAddress("addresses on this computer or the local network are not opened")
    if not addresses:
        raise BlockedAddress(f"the address {parsed.hostname} could not be found")
    return addresses[0]


def check_public(url: str) -> None:
    resolve(normalise_url(url))


class _PinnedHTTP(http.client.HTTPConnection):
    """A connection to an address already checked, whatever the name resolves to now."""

    def __init__(self, host, ip, **kwargs):
        super().__init__(host, **kwargs)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, **kwargs):
        super().__init__(host, **kwargs)
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _decompress(raw: bytes, encoding: str) -> bytes:
    """Unpack gzip/deflate without letting a small download expand without limit."""
    if encoding in ("gzip", "x-gzip"):
        modes = (16 + zlib.MAX_WBITS,)
    elif encoding == "deflate":
        modes = (zlib.MAX_WBITS, -zlib.MAX_WBITS)      # zlib-wrapped, or raw as some servers send
    else:
        return raw
    for wbits in modes:
        try:
            return zlib.decompressobj(wbits).decompress(raw, DECODED_LIMIT)
        except zlib.error:
            continue
    raise ValueError("the page's compressed data is damaged")


def _request(url: str, data, timeout: float, public: bool, headers: dict | None = None):
    """(status, headers, body bytes) for one request, connected to the checked address."""
    parsed = urllib.parse.urlsplit(url)
    ip = resolve(url, public)
    kwargs = {"port": parsed.port, "timeout": timeout}
    if parsed.scheme == "https":
        connection = _PinnedHTTPS(parsed.hostname, ip, context=providers.ssl_context(), **kwargs)
    else:
        connection = _PinnedHTTP(parsed.hostname, ip, **kwargs)
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    sent = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8", "Accept-Encoding": "gzip, deflate"}
    sent.update(headers or {})
    if data is not None:
        sent["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        connection.request("POST" if data is not None else "GET", target, body=data, headers=sent)
        response = connection.getresponse()
        body = response.read(READ_LIMIT)
        return response.status, response.headers, body
    finally:
        connection.close()


def fetch(url: str, data: bytes | None = None, timeout: float = 20, public: bool = True,
          headers: dict | None = None) -> tuple:
    """(final url, decoded text) of a web page - a public one unless `public` is False."""
    url, response_headers, raw = fetch_raw(url, data, timeout, public, headers)
    return url, _decode(raw, response_headers)


def _decode(raw: bytes, response_headers) -> str:
    charset = response_headers.get_content_charset()
    if not charset:
        match = re.search(rb'charset=["\']?([A-Za-z0-9_\-]+)', raw[:4000])
        charset = match.group(1).decode() if match else "utf-8"
    try:
        return raw.decode(charset, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def fetch_raw(url: str, data: bytes | None = None, timeout: float = 20, public: bool = True,
              headers: dict | None = None) -> tuple:
    """(final url, response headers, unpacked body bytes) after following redirects."""
    url = normalise_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        status, response_headers, raw = _request(url, data, timeout, public, headers)
        location = response_headers.get("Location")
        if status in (301, 302, 303, 307, 308) and location:
            url = normalise_url(urllib.parse.urljoin(url, location))
            if status in (301, 302, 303):
                data = None
            continue
        if status >= 400:
            raise HTTPStatusError(status)
        raw = _decompress(raw, (response_headers.get("Content-Encoding") or "").lower())
        return url, response_headers, raw
    raise RuntimeError("the page redirected too many times")


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form",
            "aside", "iframe", "template", "button"}
    BLOCK = {"p", "div", "section", "article", "li", "tr", "br", "h1", "h2", "h3", "h4",
             "h5", "h6", "table", "ul", "ol", "pre", "blockquote", "main", "dd", "dt"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip, self.title, self._in_title = [], 0, "", False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3") and not self.skip:
            self.parts.append("## ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)


def page_text(markup: str) -> tuple:
    parser = _Text()
    try:
        parser.feed(markup)
    except Exception:
        pass
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    return parser.title.strip(), "\n".join(lines).strip()


_MEDIA = ("image/", "audio/", "video/", "font/")


def read_page(url: str, public: bool = True) -> str:
    final, response_headers, raw = fetch_raw(url, public=public)
    kind = (response_headers.get_content_type() or "").lower()
    if kind == "application/pdf" or raw[:5] == b"%PDF-":
        if len(raw) >= READ_LIMIT:
            raise ValueError("the PDF is larger than can be downloaded here (5 MB); ask the user "
                             "to download it and attach it")
        text = documents.pdf_bytes_text(raw)
        if len(text) > PAGE_LIMIT * 2:
            text = text[:PAGE_LIMIT * 2] + "\n... (the rest of the PDF was cut off)"
        return f"PDF document\nURL: {final}\n\n{text or '(no readable text)'}"
    if kind.startswith(_MEDIA) or b"\x00" in raw[:4096]:
        # A picture, a zip, a program: decoding it as text would only hand the AI noise.
        raise ValueError(f"that address is not a web page but a file ({kind}); it cannot be read "
                         "as text here")
    title, text = page_text(_decode(raw, response_headers))
    if len(text) > PAGE_LIMIT:
        text = text[:PAGE_LIMIT] + "\n... (the rest of the page was cut off)"
    return f"Title: {title or '(none)'}\nURL: {final}\n\n{text or '(no readable text)'}"


def _strip_tags(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _duckduckgo(query: str) -> list:
    _, markup = fetch("https://html.duckduckgo.com/html/",
                      data=urllib.parse.urlencode({"q": query}).encode())
    results = []
    for block in re.findall(r'<div class="result results_links.*?(?=<div class="result results_links|$)',
                            markup, re.DOTALL):
        link = re.search(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not link:
            continue
        href = html.unescape(link.group(1))
        target = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg")
        url = target[0] if target else href
        if "duckduckgo.com/y.js" in url:
            continue                                  # an advert
        snippet = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL)
        results.append({"title": _strip_tags(link.group(2)), "url": url,
                        "snippet": _strip_tags(snippet.group(1)) if snippet else ""})
    return results


def _bing(query: str) -> list:
    _, markup = fetch("https://www.bing.com/search?" + urllib.parse.urlencode({"q": query}))
    results = []
    for block in re.findall(r'<li class="b_algo".*?</li>', markup, re.DOTALL):
        link = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not link:
            continue
        snippet = re.search(r"<p[^>]*>(.*?)</p>", block, re.DOTALL)
        url = html.unescape(link.group(1))
        target = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("u")
        if target and target[0].startswith("a1"):
            try:                      # Bing's click-tracking link: the real address is base64
                encoded = target[0][2:]
                url = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
            except (ValueError, UnicodeDecodeError):
                pass
        results.append({"title": _strip_tags(link.group(2)), "url": url,
                        "snippet": _strip_tags(snippet.group(1)) if snippet else ""})
    return results


def _ddgs(query: str) -> list:
    """The `ddgs` package: several engines behind a browser-like client.

    Search engines increasingly answer plain scripted requests with a captcha
    or with unrelated results; this is what Aetheris used, and it holds up.
    """
    from ddgs import DDGS
    region = "kr-kr" if re.search(r"[\uac00-\ud7a3]", query) else "wt-wt"
    found = DDGS(timeout=15).text(query, region=region, max_results=10) or []
    return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
            for r in found if r.get("href")]


def searxng(query: str, base: str) -> list:
    """Results from a SearXNG instance's JSON API. Its address is the person's own choice,
    so it may be on the local network."""
    url = f"{base.rstrip('/')}/search?" + urllib.parse.urlencode({"q": query, "format": "json"})
    try:
        _, body = fetch(url, public=False, headers={"Accept": "application/json"})
    except HTTPStatusError as error:
        if error.status == 403:
            raise RuntimeError("SearXNG refused to answer in JSON. Add 'json' under "
                               "search: formats: in its settings.yml") from None
        raise
    try:
        data = json.loads(body)
    except ValueError:
        raise RuntimeError("the SearXNG address did not answer like SearXNG "
                           "(check the address in Settings)") from None
    return [{"title": str(r.get("title") or ""), "url": str(r["url"]),
             "snippet": str(r.get("content") or "")}
            for r in data.get("results") or [] if isinstance(r, dict) and r.get("url")]


def _searxng(query: str) -> list:
    return searxng(query, settings.get("searxng_url") or "")


def engines() -> tuple:
    current = settings.load()
    if current["search_engine"] == "searxng" and current["searxng_url"]:
        # The person chose their own engine; their queries do not go anywhere else.
        return (_searxng,)
    return (_ddgs, _duckduckgo, _bing)


def search(query: str, limit: int = 8) -> list:
    errors = []
    for engine in engines():
        try:
            results = engine(query)
        except Exception as error:
            errors.append(f"{engine.__name__.strip('_')}: {error}")
            continue
        if results:
            return results[:limit]
    if errors:
        raise RuntimeError("; ".join(errors))
    return []
