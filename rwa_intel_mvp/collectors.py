from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any

from .models import RawItem, Source


DEFAULT_TIMEOUT_SECONDS = 20
MAX_TEXT_CHARS = 12000


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


def collect_sources(sources: list[Source], limit_per_source: int = 10) -> tuple[list[RawItem], list[str]]:
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
        return [collect_web_page(source)]
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
                published_at=published_at,
                summary=text[:2000],
                raw_text=text[:MAX_TEXT_CHARS],
            )
        )
    return output


def collect_web_page(source: Source) -> RawItem:
    html = fetch_text(source.url, headers=source.headers)
    title = extract_title(html) or source.name
    text = strip_html(html)
    return RawItem(
        source_name=source.name,
        source_kind=source.kind,
        source_url=source.url,
        title=title,
        url=source.url,
        summary=text[:2000],
        raw_text=text[:MAX_TEXT_CHARS],
    )


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
                published_at=str(published_at) if published_at else None,
                summary=(summary or text)[:2000],
                raw_text=text[:MAX_TEXT_CHARS],
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
