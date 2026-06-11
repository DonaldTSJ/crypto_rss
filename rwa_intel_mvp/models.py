from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class Source:
    name: str
    kind: str
    url: str
    category: str = "news"
    priority: str = "normal"
    enabled: bool = True
    keywords: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    items_path: str | None = None
    title_field: str = "title"
    url_field: str = "url"
    summary_field: str = "summary"
    published_field: str = "published_at"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Source":
        return cls(
            name=str(data["name"]),
            kind=str(data.get("kind", data.get("type", "rss"))).lower(),
            url=str(data["url"]),
            category=str(data.get("category", "news")),
            priority=str(data.get("priority", "normal")),
            enabled=bool(data.get("enabled", True)),
            keywords=list(data.get("keywords", [])),
            headers=dict(data.get("headers", {})),
            items_path=data.get("items_path"),
            title_field=str(data.get("title_field", "title")),
            url_field=str(data.get("url_field", "url")),
            summary_field=str(data.get("summary_field", "summary")),
            published_field=str(data.get("published_field", "published_at")),
        )


@dataclass
class RawItem:
    source_name: str
    source_kind: str
    source_url: str
    title: str
    url: str
    published_at: str | None = None
    summary: str = ""
    raw_text: str = ""
    fetched_at: str = field(default_factory=utc_now_iso)

    @property
    def identity_material(self) -> str:
        return (self.url or f"{self.source_name}:{self.title}").strip().lower()


@dataclass
class Analysis:
    relevance_score: int
    importance_score: int
    categories: list[str]
    projects: list[str]
    asset_classes: list[str]
    chains: list[str]
    jurisdictions: list[str]
    summary: str
    business_impact: str
    next_action: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    provider: str = "rules"

    @property
    def alert_score(self) -> int:
        return max(self.relevance_score, self.importance_score)

    @classmethod
    def from_dict(cls, data: dict[str, Any], provider: str) -> "Analysis":
        return cls(
            relevance_score=_as_int(data.get("relevance_score"), 0, 100),
            importance_score=_as_int(data.get("importance_score"), 0, 100),
            categories=_as_str_list(data.get("categories")),
            projects=_as_str_list(data.get("projects")),
            asset_classes=_as_str_list(data.get("asset_classes")),
            chains=_as_str_list(data.get("chains")),
            jurisdictions=_as_str_list(data.get("jurisdictions")),
            summary=str(data.get("summary", "")).strip(),
            business_impact=str(data.get("business_impact", "")).strip(),
            next_action=str(data.get("next_action", "")).strip(),
            confidence=_as_float(data.get("confidence"), 0.0, 1.0),
            reasons=_as_str_list(data.get("reasons")),
            provider=provider,
        )


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _as_int(value: Any, low: int, high: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def _as_float(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))
