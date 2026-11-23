"""Searching the web and reading a page.

Searching goes through the `ddgs` package when it is installed; if it is not,
or it fails, two search engines' plain HTML pages are read in turn (DuckDuckGo,
then Bing), so one that is down or asks for a captcha does not end it. A page is
reduced to its readable text. Neither will fetch an address on this computer
or its local network: a web page could otherwise tell the AI to.
"""

import base64
import gzip
import html
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser

from aetheris_everyone import providers

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
PAGE_LIMIT = 15_000


class BlockedAddress(ValueError):
    pass


def check_public(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise BlockedAddress("only http and https web addresses can be opened")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise BlockedAddress(f"the address {parsed.hostname} could not be found") from None
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if not address.is_global:
            raise BlockedAddress("addresses on this computer or the local network are not opened")


class _NoPrivateRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str, data: bytes | None = None, timeout: float = 20) -> tuple:
    """(final url, decoded text) of a public web page."""
    check_public(url)
    opener = urllib.request.build_opener(
        _NoPrivateRedirects, urllib.request.HTTPSHandler(context=providers.ssl_context()))
    request = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8", "Accept-Encoding": "gzip, deflate"})
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(5_000_000)
        encoding = (response.headers.get("Content-Encoding") or "").lower()
        if encoding == "gzip":
            raw = gzip.decompress(raw)
        elif encoding == "deflate":
            raw = zlib.decompress(raw)
        charset = response.headers.get_content_charset()
        if not charset:
            match = re.search(rb'charset=["\']?([A-Za-z0-9_\-]+)', raw[:4000])
            charset = match.group(1).decode() if match else "utf-8"
        try:
            text = raw.decode(charset, "replace")
        except LookupError:
            text = raw.decode("utf-8", "replace")
        return response.geturl(), text


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


def read_page(url: str) -> str:
    final, markup = fetch(url)
    title, text = page_text(markup)
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


def search(query: str, limit: int = 8) -> list:
    errors = []
    for engine in (_ddgs, _duckduckgo, _bing):
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
