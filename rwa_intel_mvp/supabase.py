from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

from .models import Analysis, RawItem, item_hash, utc_now_iso


DEFAULT_SUPABASE_TABLE = "crypto_intel_items"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_DASHBOARD_LIMIT = 100
SELECT_DASHBOARD_FIELDS = ",".join(
    [
        "name:title",
        "url",
        "source:source_name",
        "importance:importance_score",
        "projects",
        "asset_classes",
    ]
)
STATUS_COLLECTED = "collected"
STATUS_SKIPPED_DATE = "skipped_date"
STATUS_SKIPPED_RULE = "skipped_rule"
STATUS_ANALYZED = "analyzed"
STATUS_SELECTED = "selected"
STATUS_SENT = "sent"


class SupabaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class SupabaseItemState:
    item_hash: str
    status: str
    alert_sent_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SupabaseItemState":
        return cls(
            item_hash=str(data.get("item_hash", "")),
            status=str(data.get("status") or STATUS_COLLECTED),
            alert_sent_at=str(data["alert_sent_at"]) if data.get("alert_sent_at") else None,
        )


@dataclass
class SupabaseWriteResult:
    table: str
    rows: int
    action: str

    def to_dict(self) -> dict[str, object]:
        return {"table": self.table, "rows": self.rows, "action": self.action}


def fetch_item_states(
    items: list[RawItem],
    supabase_url: str | None,
    supabase_key: str | None,
    table: str = DEFAULT_SUPABASE_TABLE,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, SupabaseItemState]:
    if not items:
        return {}
    _require_credentials(supabase_url, supabase_key)

    states: dict[str, SupabaseItemState] = {}
    hashes = sorted({item_hash(item) for item in items})
    for chunk in _chunks(hashes, 80):
        query = (
            "select=item_hash,status,alert_sent_at"
            f"&item_hash=in.({','.join(chunk)})"
        )
        endpoint = _rest_endpoint(str(supabase_url), table, query=query)
        rows = _request_json("GET", endpoint, str(supabase_key), timeout=timeout)
        if not isinstance(rows, list):
            raise SupabaseError(f"Supabase state query returned unexpected payload: {rows!r}")
        for row in rows:
            if isinstance(row, dict):
                state = SupabaseItemState.from_dict(row)
                if state.item_hash:
                    states[state.item_hash] = state
    return states


def upsert_collected_items(
    items: list[RawItem],
    supabase_url: str | None,
    supabase_key: str | None,
    table: str = DEFAULT_SUPABASE_TABLE,
    existing_states: dict[str, SupabaseItemState] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> SupabaseWriteResult:
    rows = build_collected_rows(_dedupe_items(items), existing_states=existing_states)
    _upsert_rows(rows, supabase_url, supabase_key, table, timeout=timeout)
    return SupabaseWriteResult(table=table, rows=len(rows), action="collected")


def upsert_status_items(
    items: list[RawItem],
    status: str,
    supabase_url: str | None,
    supabase_key: str | None,
    table: str = DEFAULT_SUPABASE_TABLE,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> SupabaseWriteResult:
    rows = [build_status_update_row(item, status) for item in _dedupe_items(items)]
    _upsert_rows(rows, supabase_url, supabase_key, table, timeout=timeout)
    return SupabaseWriteResult(table=table, rows=len(rows), action=status)


def upsert_analysis_items(
    items: list[tuple[RawItem, Analysis, str]],
    supabase_url: str | None,
    supabase_key: str | None,
    table: str = DEFAULT_SUPABASE_TABLE,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> SupabaseWriteResult:
    rows = [
        build_analysis_update_row(item, analysis, status)
        for item, analysis, status in _dedupe_analysis_items(items)
    ]
    _upsert_rows(rows, supabase_url, supabase_key, table, timeout=timeout)
    return SupabaseWriteResult(table=table, rows=len(rows), action="analysis")


def mark_alert_sent(
    items: list[tuple[RawItem, Analysis]],
    supabase_url: str | None,
    supabase_key: str | None,
    table: str = DEFAULT_SUPABASE_TABLE,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> SupabaseWriteResult:
    sent_at = utc_now_iso()
    rows = [
        {
            **build_analysis_update_row(item, analysis, STATUS_SENT),
            "alert_sent_at": sent_at,
        }
        for item, analysis in _dedupe_alert_items(items)
    ]
    _upsert_rows(rows, supabase_url, supabase_key, table, timeout=timeout)
    return SupabaseWriteResult(table=table, rows=len(rows), action=STATUS_SENT)


def fetch_dashboard_items(
    supabase_url: str | None,
    supabase_key: str | None,
    table: str = DEFAULT_SUPABASE_TABLE,
    status: str | None = None,
    run_date: str | None = None,
    search: str | None = None,
    limit: int = DEFAULT_DASHBOARD_LIMIT,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    _require_credentials(supabase_url, supabase_key)
    bounded_limit = max(1, min(limit, 500))
    query_parts = [
        ("select", SELECT_DASHBOARD_FIELDS),
        ("order", "run_date.desc,importance_score.desc,last_seen_at.desc"),
        ("limit", str(bounded_limit)),
    ]
    if status:
        query_parts.append(("status", f"eq.{status}"))
    if run_date:
        query_parts.append(("run_date", f"eq.{run_date}"))
    if search:
        safe_search = _sanitize_search(search)
        if safe_search:
            pattern = f"*{safe_search}*"
            query_parts.append(
                (
                    "or",
                    f"(title.ilike.{pattern},summary.ilike.{pattern},source_name.ilike.{pattern},business_impact.ilike.{pattern})",
                )
            )

    query = urllib.parse.urlencode(query_parts, doseq=True, safe="(),.*")
    endpoint = _rest_endpoint(str(supabase_url), table, query=query)
    rows = _request_json("GET", endpoint, str(supabase_key), timeout=timeout)
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise SupabaseError(f"Supabase dashboard query returned unexpected payload: {rows!r}")
    return [row for row in rows if isinstance(row, dict)]


def build_collected_rows(
    items: list[RawItem],
    existing_states: dict[str, SupabaseItemState] | None = None,
    run_date: str | None = None,
) -> list[dict[str, object]]:
    today = run_date or datetime.now().astimezone().date().isoformat()
    states = existing_states or {}
    rows: list[dict[str, object]] = []
    for item in items:
        digest = item_hash(item)
        existing = states.get(digest)
        status = existing.status if existing else STATUS_COLLECTED
        if existing:
            rows.append(
                {
                    "item_hash": digest,
                    "run_date": today,
                    "title": item.title,
                    "url": item.url,
                    "source_name": item.source_name,
                    "source_kind": item.source_kind,
                    "source_url": item.source_url,
                    "published_at": _normalize_datetime(item.published_at),
                    "fetched_at": _normalize_datetime(item.fetched_at),
                    "last_seen_at": utc_now_iso(),
                    "status": status,
                }
            )
            continue
        rows.append(
            {
                "item_hash": digest,
                "run_date": today,
                "title": item.title,
                "url": item.url,
                "source_name": item.source_name,
                "source_kind": item.source_kind,
                "source_url": item.source_url,
                "published_at": _normalize_datetime(item.published_at),
                "fetched_at": _normalize_datetime(item.fetched_at),
                "last_seen_at": utc_now_iso(),
                "status": status,
                "raw_summary": _clip(item.summary, 4000),
                "raw_text": _clip(item.raw_text, 12000),
            }
        )
    return rows


def build_status_row(item: RawItem, status: str, run_date: str | None = None) -> dict[str, object]:
    row = build_collected_rows([item], run_date=run_date)[0]
    row["status"] = status
    return row


def build_analysis_row(
    item: RawItem,
    analysis: Analysis,
    status: str,
    run_date: str | None = None,
) -> dict[str, object]:
    row = build_status_row(item, status, run_date=run_date)
    row.update(
        {
            "relevance_score": analysis.relevance_score,
            "importance_score": analysis.importance_score,
            "alert_score": analysis.alert_score,
            "confidence": round(analysis.confidence, 3),
            "provider": analysis.provider,
            "categories": analysis.categories,
            "projects": analysis.projects,
            "asset_classes": analysis.asset_classes,
            "chains": analysis.chains,
            "jurisdictions": analysis.jurisdictions,
            "summary": analysis.summary,
            "business_impact": analysis.business_impact,
            "next_action": analysis.next_action,
            "reasons": analysis.reasons,
            "tags": _tags_for_analysis(analysis),
        }
    )
    return row


def build_status_update_row(item: RawItem, status: str, run_date: str | None = None) -> dict[str, object]:
    return {
        "item_hash": item_hash(item),
        "run_date": run_date or datetime.now().astimezone().date().isoformat(),
        "title": item.title,
        "url": item.url,
        "source_name": item.source_name,
        "source_kind": item.source_kind,
        "source_url": item.source_url,
        "published_at": _normalize_datetime(item.published_at),
        "fetched_at": _normalize_datetime(item.fetched_at),
        "status": status,
        "last_seen_at": utc_now_iso(),
    }


def build_analysis_update_row(
    item: RawItem,
    analysis: Analysis,
    status: str,
    run_date: str | None = None,
) -> dict[str, object]:
    row = build_status_update_row(item, status, run_date=run_date)
    row.update(
        {
            "relevance_score": analysis.relevance_score,
            "importance_score": analysis.importance_score,
            "alert_score": analysis.alert_score,
            "confidence": round(analysis.confidence, 3),
            "provider": analysis.provider,
            "categories": analysis.categories,
            "projects": analysis.projects,
            "asset_classes": analysis.asset_classes,
            "chains": analysis.chains,
            "jurisdictions": analysis.jurisdictions,
            "summary": analysis.summary,
            "business_impact": analysis.business_impact,
            "next_action": analysis.next_action,
            "reasons": analysis.reasons,
            "tags": _tags_for_analysis(analysis),
        }
    )
    return row


def already_alerted(item: RawItem, states: dict[str, SupabaseItemState]) -> bool:
    state = states.get(item_hash(item))
    return bool(state and state.alert_sent_at)


def should_skip_seen(item: RawItem, states: dict[str, SupabaseItemState]) -> bool:
    state = states.get(item_hash(item))
    if not state:
        return False
    if state.status == STATUS_SELECTED and not state.alert_sent_at:
        return False
    return state.status != STATUS_COLLECTED


def _dedupe_items(items: list[RawItem]) -> list[RawItem]:
    seen: set[str] = set()
    unique: list[RawItem] = []
    for item in items:
        digest = item_hash(item)
        if digest in seen:
            continue
        seen.add(digest)
        unique.append(item)
    return unique


def _dedupe_analysis_items(items: list[tuple[RawItem, Analysis, str]]) -> list[tuple[RawItem, Analysis, str]]:
    unique: dict[str, tuple[RawItem, Analysis, str]] = {}
    for item, analysis, status in items:
        unique[item_hash(item)] = (item, analysis, status)
    return list(unique.values())


def _dedupe_alert_items(items: list[tuple[RawItem, Analysis]]) -> list[tuple[RawItem, Analysis]]:
    unique: dict[str, tuple[RawItem, Analysis]] = {}
    for item, analysis in items:
        unique[item_hash(item)] = (item, analysis)
    return list(unique.values())


def _upsert_rows(
    rows: list[dict[str, object]],
    supabase_url: str | None,
    supabase_key: str | None,
    table: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    if not rows:
        return
    _require_credentials(supabase_url, supabase_key)
    endpoint = _rest_endpoint(str(supabase_url), table, query="on_conflict=item_hash")
    for batch in _batches_by_keys(rows):
        _request_json(
            "POST",
            endpoint,
            str(supabase_key),
            data=batch,
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            timeout=timeout,
        )


def _batches_by_keys(rows: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    batches: dict[tuple[str, ...], list[dict[str, object]]] = {}
    for row in rows:
        key = tuple(sorted(row))
        batches.setdefault(key, []).append(row)
    return list(batches.values())


def _request_json(
    method: str,
    endpoint: str,
    supabase_key: str,
    data: object | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> object:
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
    request_headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
    }
    request_headers.update(headers or {})
    request = urllib.request.Request(endpoint, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise SupabaseError(f"Supabase request failed ({exc.code}): {error_body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise SupabaseError(f"Supabase request failed: {exc}") from exc
    except OSError as exc:
        raise SupabaseError(f"Supabase request timed out or failed: {exc}") from exc

    if not response_body:
        return None
    try:
        return json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise SupabaseError(f"Supabase returned non-JSON response: {response_body[:200]}") from exc


def _require_credentials(supabase_url: str | None, supabase_key: str | None) -> None:
    if not supabase_url:
        raise SupabaseError("SUPABASE_URL is required for live Supabase storage.")
    if not supabase_key:
        raise SupabaseError("SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY is required for live Supabase storage.")


def _rest_endpoint(supabase_url: str, table: str, query: str | None = None) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise SupabaseError(f"Invalid Supabase table name: {table}")

    base = supabase_url.rstrip("/")
    if "supabase.com/dashboard" in base:
        raise SupabaseError(
            "SUPABASE_URL should be your project API URL, for example https://PROJECT_REF.supabase.co, "
            "not the dashboard URL."
        )
    if not base.endswith("/rest/v1"):
        base = f"{base}/rest/v1"
    quoted_table = urllib.parse.quote(table, safe="")
    suffix = f"?{query}" if query else ""
    return f"{base}/{quoted_table}{suffix}"


def _normalize_datetime(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.isoformat()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text).isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _tags_for_analysis(analysis: Analysis) -> list[str]:
    tags = ["crypto/intel"]
    for label in analysis.asset_classes or analysis.categories:
        safe = re.sub(r"[^a-z0-9_-]+", "-", label.lower()).strip("-")
        if safe:
            tags.append(f"crypto/{safe}")
    return sorted(set(tags))


def _clip(text: str, limit: int) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _sanitize_search(value: str) -> str:
    return re.sub(r"[\s,()]+", " ", value).strip()[:80]


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]
