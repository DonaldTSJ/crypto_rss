from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any

from .models import RawItem, Source


DEFAULT_TIMEOUT_SECONDS = 20
MAX_TEXT_CHARS = 12000
DEFAULT_LINK_TERMS = [
    "announcement",
    "announcements",
    "article",
    "blog",
    "circular",
    "delisting",
    "help",
    "listing",
    "maintenance",
    "news",
    "notice",
    "post",
    "press",
    "release",
    "support",
]
DEFAULT_LINK_EXCLUDES = [
    "about",
    "account",
    "app",
    "career",
    "category",
    "contact",
    "cookie",
    "download",
    "events",
    "explore",
    "login",
    "newsletter",
    "privacy",
    "register",
    "sign-in",
    "signup",
    "terms",
]
LOW_VALUE_LINK_TITLES = {
    "announcements",
    "blog",
    "company news",
    "crypto education",
    "cryptocurrencies",
    "company",
    "delisting",
    "eservices",
    "help center",
    "history",
    "inside fca podcasts",
    "jupiter developer platform",
    "latest announcements",
    "latest events",
    "latest news",
    "learn more",
    "market",
    "media library",
    "new listings",
    "personal",
    "portfolio",
    "press releases",
    "product",
    "product news",
    "speeches",
    "roadmap",
    "system maintenance",
    "skip to content",
    "skip to main content",
    "subscribe",
    "terminal",
    "news stories",
    "others",
    "partnerships",
    "policy",
    "read more",
    "view all",
}


class CollectError(RuntimeError):
    pass


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


@dataclass(frozen=True)
class LinkCandidate:
    title: str
    url: str
    attrs: dict[str, str]
    position: int
    published_at: str | None = None


class LinkExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[LinkCandidate] = []
        self._active_link: dict[str, object] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {key.lower(): value or "" for key, value in attrs}
        href = attr_map.get("href", "").strip()
        if not href:
            return
        self._active_link = {
            "href": urllib.parse.urljoin(self.base_url, href),
            "attrs": attr_map,
            "parts": [],
        }

    def handle_data(self, data: str) -> None:
        if not self._active_link:
            return
        text = " ".join(data.split())
        if text:
            parts = self._active_link["parts"]
            if isinstance(parts, list):
                parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._active_link:
            return
        attrs = self._active_link["attrs"]
        href = str(self._active_link["href"])
        parts = self._active_link["parts"]
        text = " ".join(parts if isinstance(parts, list) else []).strip()
        if isinstance(attrs, dict):
            title = text or attrs.get("title") or attrs.get("aria-label") or href
            self.links.append(
                LinkCandidate(
                    title=strip_html(title).strip(),
                    url=href,
                    attrs={str(key): str(value) for key, value in attrs.items()},
                    position=len(self.links),
                )
            )
        self._active_link = None


def collect_sources(sources: list[Source], limit_per_source: int = 10) -> tuple[list[RawItem], list[str]]:
    items: list[RawItem] = []
    errors: list[str] = []
    if not sources:
        return items, errors
    if len(sources) == 1:
        try:
            items.extend(collect_source(sources[0], limit=limit_per_source))
        except Exception as exc:  # noqa: BLE001 - collection should be best-effort.
            errors.append(f"{sources[0].name}: {exc}")
        return items, errors

    results: dict[int, list[RawItem]] = {}
    max_workers = min(12, len(sources))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_sources = {
            executor.submit(collect_source, source, limit_per_source): (index, source)
            for index, source in enumerate(sources)
        }
        for future in as_completed(future_sources):
            index, source = future_sources[future]
            try:
                results[index] = future.result()
            except Exception as exc:  # noqa: BLE001 - collection should be best-effort.
                errors.append(f"{source.name}: {exc}")

    for index in range(len(sources)):
        items.extend(results.get(index, []))
    return items, errors


def collect_sources_serial(sources: list[Source], limit_per_source: int = 10) -> tuple[list[RawItem], list[str]]:
    items: list[RawItem] = []
    errors: list[str] = []
    for source in sources:
        try:
            items.extend(collect_source(source, limit=limit_per_source))
        except Exception as exc:  # noqa: BLE001 - collection should be best-effort.
            errors.append(f"{source.name}: {exc}")
    return items, errors


def collect_source(source: Source, limit: int = 10) -> list[RawItem]:
    if limit <= 0:
        return []
    if source.kind == "rss":
        return collect_rss(source, limit=limit)
    if source.kind in {"web", "announcement"}:
        return collect_web_items(source, limit=limit)
    if source.kind == "api":
        return collect_api(source, limit=limit)
    raise CollectError(f"unsupported source kind: {source.kind}")


def collect_rss(source: Source, limit: int = 10) -> list[RawItem]:
    body = fetch_text(source.url, headers=source.headers)
    root = ET.fromstring(body)
    entries = root.findall(".//item")
    if not entries:
        entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    output: list[RawItem] = []
    for entry in entries[:limit]:
        title = _first_text(entry, ["title", "{http://www.w3.org/2005/Atom}title"]) or "Untitled"
        link = _entry_link(entry) or source.url
        summary = _first_text(
            entry,
            [
                "description",
                "summary",
                "{http://www.w3.org/2005/Atom}summary",
                "{http://www.w3.org/2005/Atom}content",
            ],
        )
        published_at = _first_text(
            entry,
            ["pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}updated"],
        )
        text = strip_html(summary or "")
        output.append(
            RawItem(
                source_name=source.name,
                source_kind=source.kind,
                source_url=source.url,
                title=title.strip(),
                url=link.strip(),
                source_category=source.category,
                published_at=published_at,
                summary=text[:2000],
                raw_text=text[:MAX_TEXT_CHARS],
                extraction_method="feed_item",
            )
        )
    return output


def collect_web_items(source: Source, limit: int = 10) -> list[RawItem]:
    html = fetch_text(source.url, headers=source.headers)
    links = extract_listing_links(html, source, limit=limit)
    if links:
        return [build_listing_item(source, link) for link in links]
    if not source.allow_web_page_fallback:
        return []
    return [build_web_page_item(source, html)]


def collect_web_page(source: Source) -> RawItem:
    html = fetch_text(source.url, headers=source.headers)
    return build_web_page_item(source, html)


def build_listing_item(source: Source, link: LinkCandidate) -> RawItem:
    title = link.title
    text = link.title
    published_at = link.published_at
    try:
        detail_html = fetch_text(link.url, headers=source.headers)
        detail_title = extract_title(detail_html)
        if detail_title and _should_use_detail_title(title, detail_title):
            title = detail_title
        detail_text = strip_html(detail_html)
        detail_published_at = extract_published_at(detail_html, detail_text, title)
        if detail_published_at:
            published_at = detail_published_at
        if detail_text:
            text = detail_text
    except CollectError:
        text = link.title
    return RawItem(
        source_name=source.name,
        source_kind=source.kind,
        source_url=source.url,
        title=title,
        url=link.url,
        source_category=source.category,
        published_at=published_at,
        summary=text[:2000],
        raw_text=text[:MAX_TEXT_CHARS],
        extraction_method="listing_item",
    )


def build_web_page_item(source: Source, html: str) -> RawItem:
    title = extract_title(html) or source.name
    text = strip_html(html)
    published_at = extract_published_at(html, text, title)
    return RawItem(
        source_name=source.name,
        source_kind=source.kind,
        source_url=source.url,
        title=title,
        url=source.url,
        source_category=source.category,
        published_at=published_at,
        summary=text[:2000],
        raw_text=text[:MAX_TEXT_CHARS],
        extraction_method="web_page",
    )


def extract_listing_links(html: str, source: Source, limit: int = 10) -> list[LinkCandidate]:
    extractor = LinkExtractor(source.url)
    extractor.feed(html)
    listing_text = strip_html(html)
    output: list[LinkCandidate] = []
    seen_urls: set[str] = set()
    for link in extractor.links:
        normalized = _normalize_link(link)
        if not normalized:
            continue
        if normalized.url in seen_urls:
            continue
        if not _is_same_site(source.url, normalized.url):
            continue
        if not _link_allowed(normalized, source):
            continue
        published_at = normalized.published_at or _listing_date_for_link(html, listing_text, normalized.title, normalized.url)
        if published_at != normalized.published_at:
            normalized = LinkCandidate(
                title=normalized.title,
                url=normalized.url,
                attrs=normalized.attrs,
                position=normalized.position,
                published_at=published_at,
            )
        seen_urls.add(normalized.url)
        output.append(normalized)
        if len(output) >= limit:
            break
    return output


def collect_api(source: Source, limit: int = 10) -> list[RawItem]:
    body = fetch_text(source.url, headers=source.headers)
    data = json.loads(body)
    if source.items_path:
        rows = _get_path(data, source.items_path, [])
    elif isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("items", data.get("data", [data]))
    else:
        rows = []
    if isinstance(rows, dict):
        rows = [rows]

    output: list[RawItem] = []
    for row in list(rows)[:limit]:
        if not isinstance(row, dict):
            continue
        title = str(_get_path(row, source.title_field) or row.get("name") or source.name)
        link = str(_get_path(row, source.url_field) or row.get("link") or source.url)
        published_at = (
            _get_path(row, source.published_field)
            or row.get("publishedAt")
            or row.get("date")
            or row.get("publishTime")
        )
        summary = str(_get_path(row, source.summary_field, "") or "")
        text = json.dumps(row, ensure_ascii=False)
        output.append(
            RawItem(
                source_name=source.name,
                source_kind=source.kind,
                source_url=source.url,
                title=title,
                url=link,
                source_category=source.category,
                published_at=str(published_at) if published_at else None,
                summary=(summary or text)[:2000],
                raw_text=text[:MAX_TEXT_CHARS],
                extraction_method="api_item",
            )
        )
    return output


def fetch_text(url: str, headers: dict[str, str] | None = None) -> str:
    request_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36 "
            "rwa-intel-mvp/0.1"
        ),
        "Accept": "text/html,application/rss+xml,application/atom+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    request_headers.update(headers or {})
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except urllib.error.URLError as exc:
        raise CollectError(str(exc)) from exc


def strip_html(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    text = parser.text()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return re.sub(r"\s+", " ", strip_html(match.group(1))).strip()


def extract_published_at(html: str, text: str | None = None, title: str | None = None) -> str | None:
    for candidate in _metadata_date_candidates(html):
        normalized = _normalize_published_date(candidate)
        if normalized:
            return normalized
    visible_text = text or strip_html(html)
    scoped_text = _article_date_scope(visible_text, title)
    for candidate in _visible_date_candidates(scoped_text):
        normalized = _normalize_published_date(candidate)
        if normalized:
            return normalized
    return None


def _metadata_date_candidates(html: str) -> list[str]:
    candidates: list[str] = []
    date_keys = {
        "article:published_time",
        "article:modified_time",
        "date",
        "datepublished",
        "datecreated",
        "dc.date",
        "dcterms.created",
        "og:published_time",
        "pubdate",
        "publishdate",
        "published_time",
        "sailthru.date",
    }
    for tag in re.findall(r"<meta\b[^>]*>", html, flags=re.IGNORECASE | re.DOTALL):
        attrs = _tag_attrs(tag)
        key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").strip().lower()
        content = attrs.get("content", "").strip()
        if key in date_keys and content:
            candidates.append(content)
    for tag in re.findall(r"<time\b[^>]*>", html, flags=re.IGNORECASE | re.DOTALL):
        value = _tag_attrs(tag).get("datetime", "").strip()
        if value:
            candidates.append(value)
    candidates.extend(_json_ld_date_candidates(html))
    return candidates


def _json_ld_date_candidates(html: str) -> list[str]:
    candidates: list[str] = []
    for match in re.finditer(
        r"<script\b[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        body = unescape(match.group(1)).strip()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        candidates.extend(_walk_json_dates(data))
    return candidates


def _walk_json_dates(value: object) -> list[str]:
    candidates: list[str] = []
    if isinstance(value, dict):
        for key in ["datePublished", "dateCreated", "dateModified", "uploadDate"]:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                candidates.append(item.strip())
        for item in value.values():
            candidates.extend(_walk_json_dates(item))
    elif isinstance(value, list):
        for item in value:
            candidates.extend(_walk_json_dates(item))
    return candidates


def _visible_date_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    month_names = (
        "Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
        "Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
    )
    patterns = [
        rf"\b(?:{month_names})\s+\d{{1,2}},\s+\d{{4}}\b",
        rf"\b\d{{1,2}}\s+(?:{month_names})\s+\d{{4}}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{4}/\d{1,2}/\d{1,2}\b",
        r"\b\d{1,2}\.\d{1,2}\.\d{4}\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            candidates.append(match.group(0))
    return candidates


def _normalize_published_date(value: str) -> str | None:
    text = unescape(str(value)).strip()
    if not text:
        return None
    iso_match = re.match(r"^\d{4}-\d{2}-\d{2}(?:[T\s].*)?$", text)
    if iso_match:
        return text
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%Y/%m/%d", "%Y/%-m/%-d"]:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    slash_match = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", text)
    if slash_match:
        year, month, day = (int(part) for part in slash_match.groups())
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return None
    dot_match = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", text)
    if dot_match:
        month, day, year = (int(part) for part in dot_match.groups())
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return None
    return None


def _listing_date_for_link(html: str, text: str, title: str, url: str) -> str | None:
    html_segment = _listing_html_segment(html, title, url)
    if html_segment:
        for candidate in _metadata_date_candidates(html_segment):
            normalized = _normalize_published_date(candidate)
            if normalized:
                return normalized
        html_text = strip_html(html_segment)
        for candidate in _visible_date_candidates(html_text):
            normalized = _normalize_published_date(candidate)
            if normalized:
                return normalized

    clean = re.sub(r"\s+", " ", text or "").strip()
    needle = re.sub(r"\s+", " ", title or "").strip().lower()
    if len(needle) < 8:
        return None
    lower = clean.lower()
    start = 0
    while True:
        index = lower.find(needle, start)
        if index < 0:
            return None
        segment = clean[index : index + 700]
        for candidate in _visible_date_candidates(segment):
            normalized = _normalize_published_date(candidate)
            if normalized:
                return normalized
        start = index + 1


def _listing_html_segment(html: str, title: str, url: str) -> str:
    lower = html.lower()
    parsed = urllib.parse.urlparse(url)
    needles = [parsed.path.lower()]
    title_needle = re.sub(r"\s+", " ", title or "").strip().lower()
    if len(title_needle) >= 8:
        needles.append(title_needle)
    indexes = [lower.find(needle) for needle in needles if needle and lower.find(needle) >= 0]
    if not indexes:
        return ""
    index = min(indexes)
    return html[max(0, index - 1000) : index + 3000]


def _article_date_scope(text: str, title: str | None) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not title:
        return clean[:8000]
    needle = re.sub(r"\s+", " ", title).strip().lower()
    if len(needle) < 8:
        return clean[:8000]
    lower = clean.lower()
    positions: list[int] = []
    start = 0
    while True:
        index = lower.find(needle, start)
        if index < 0:
            break
        positions.append(index)
        start = index + 1
    for index in positions:
        segment = clean[index : index + 4000]
        if _visible_date_candidates(segment):
            return segment
    late_positions = [index for index in positions if index > 500]
    if late_positions:
        return clean[late_positions[-1] : late_positions[-1] + 4000]
    if positions:
        return clean[positions[0] : positions[0] + 4000]
    return clean[:8000]


def _tag_attrs(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in re.finditer(r"([A-Za-z_:.-]+)\s*=\s*(['\"])(.*?)\2", tag, flags=re.DOTALL):
        attrs[match.group(1).lower()] = unescape(match.group(3))
    return attrs


def _normalize_link(link: LinkCandidate) -> LinkCandidate | None:
    parsed = urllib.parse.urlparse(link.url)
    if parsed.scheme not in {"http", "https"}:
        return None
    clean_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))
    title = re.sub(r"\s+", " ", link.title).strip()
    if len(title) < 6:
        return None
    return LinkCandidate(title=title[:240], url=clean_url, attrs=link.attrs, position=link.position)


def _is_same_site(source_url: str, item_url: str) -> bool:
    source_host = urllib.parse.urlparse(source_url).netloc.lower().removeprefix("www.")
    item_host = urllib.parse.urlparse(item_url).netloc.lower().removeprefix("www.")
    return bool(source_host and item_host and source_host == item_host)


def _link_allowed(link: LinkCandidate, source: Source) -> bool:
    haystack = f"{link.title} {link.url} {' '.join(link.attrs.values())}".lower()
    if _is_low_value_link(link, source):
        return False
    excludes = [*DEFAULT_LINK_EXCLUDES, *source.link_exclude]
    if any(term.lower() in haystack for term in excludes):
        return False

    if source.link_selector and not _matches_link_selector(link, source.link_selector):
        return False

    includes = [term.lower() for term in source.link_include if term]
    if includes:
        return any(term in haystack for term in includes)

    source_terms = [term.lower() for term in source.keywords if term]
    default_terms = [term.lower() for term in DEFAULT_LINK_TERMS]
    return any(term in haystack for term in [*source_terms, *default_terms])


def _is_low_value_link(link: LinkCandidate, source: Source) -> bool:
    title = re.sub(r"\s+", " ", link.title).strip().lower()
    if title in LOW_VALUE_LINK_TITLES:
        return True
    if _same_normalized_url(link.url, source.url):
        return True
    parsed = urllib.parse.urlparse(link.url)
    path = parsed.path.rstrip("/").lower()
    if any(fragment in path for fragment in ["/category/", "/categories/", "/support/categories", "/support/sections"]):
        return True
    if parsed.query and any(term in parsed.query.lower() for term in ["tag=", "category="]):
        return True
    return False


def _same_normalized_url(left: str, right: str) -> bool:
    def normalize(value: str) -> str:
        parsed = urllib.parse.urlparse(value)
        return urllib.parse.urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower().removeprefix("www."),
                parsed.path.rstrip("/"),
                "",
                parsed.query,
                "",
            )
        )

    return normalize(left) == normalize(right)


def _should_use_detail_title(current_title: str, detail_title: str) -> bool:
    current = re.sub(r"\s+", " ", current_title).strip()
    detail = re.sub(r"\s+", " ", detail_title).strip()
    if len(detail) < 6:
        return False
    parsed = urllib.parse.urlparse(current)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return True
    if current.lower() in LOW_VALUE_LINK_TITLES:
        return True
    return False


def _matches_link_selector(link: LinkCandidate, selector: str) -> bool:
    for part in selector.split(","):
        if _matches_single_link_selector(link, part.strip()):
            return True
    return False


def _matches_single_link_selector(link: LinkCandidate, selector: str) -> bool:
    if not selector:
        return False
    if not selector.startswith("a"):
        return True
    class_match = re.search(r"\.([A-Za-z0-9_-]+)", selector)
    if class_match:
        classes = set(link.attrs.get("class", "").split())
        if class_match.group(1) not in classes:
            return False
    attr_match = re.search(r"\[([A-Za-z0-9_-]+)([*^$]?=)?['\"]?([^'\"]*)['\"]?\]", selector)
    if not attr_match:
        return True
    attr_name, operator, expected = attr_match.groups()
    actual = link.attrs.get(attr_name.lower(), "")
    if operator == "*=":
        return expected in actual
    if operator == "^=":
        return actual.startswith(expected)
    if operator == "$=":
        return actual.endswith(expected)
    if operator == "=":
        return actual == expected
    return bool(actual)


def _first_text(entry: ET.Element, names: list[str]) -> str | None:
    for name in names:
        node = entry.find(name)
        if node is not None and node.text:
            return node.text.strip()
    return None


def _entry_link(entry: ET.Element) -> str | None:
    link = _first_text(entry, ["link"])
    if link:
        return link
    for node in entry.findall("{http://www.w3.org/2005/Atom}link"):
        href = node.attrib.get("href")
        if href:
            return href
    return None


def _get_path(data: Any, path: str, default: Any = None) -> Any:
    current = data
    for part in path.split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part, default)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else default
        else:
            return default
    return current
