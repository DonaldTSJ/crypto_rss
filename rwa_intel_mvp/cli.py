from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime
from email.utils import parsedate_to_datetime

from .analyzer import deepseek_analyze, deepseek_brief_summary, heuristic_analyze, passes_rule_filter
from .collectors import collect_sources
from .config import DEFAULT_SOURCES_PATH, load_local_env, load_sources
from .dashboard import DEFAULT_DASHBOARD_HOST, DEFAULT_DASHBOARD_PORT, run_dashboard
from .feishu import FeishuError, build_alert_interactive_payload, format_alert, rank_alert_items, send_text
from .models import Analysis, RawItem, item_hash
from .supabase import (
    DEFAULT_SUPABASE_TABLE,
    STATUS_ANALYZED,
    STATUS_SELECTED,
    STATUS_SENT,
    STATUS_SKIPPED_DATE,
    STATUS_SKIPPED_RULE,
    SupabaseError,
    already_alerted,
    fetch_item_states,
    mark_alert_sent,
    should_skip_seen,
    upsert_analysis_items,
    upsert_collected_items,
    upsert_status_items,
)


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    load_local_env()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list-sources":
        return list_sources(args)
    if args.command == "send-test":
        return send_test(args)
    if args.command == "dashboard":
        return dashboard(args)
    if args.command == "run":
        return run_pipeline(args)

    parser.print_help()
    return 2


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crypto-rss", description="RWA/tokenization intelligence MVP")
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="collect, filter, analyze, and optionally push alerts")
    run.add_argument("--sources", default=str(DEFAULT_SOURCES_PATH), help="JSON source config path")
    run.add_argument("--limit-per-source", type=int, default=8)
    run.add_argument("--min-score", type=int, default=70)
    run.add_argument("--top-n", type=int, default=10, help="maximum items in the final daily brief")
    run.add_argument("--all-dates", action="store_true", help="include dated items outside today's local date")
    run.add_argument("--dry-run", action="store_true", help="print payload without writing Supabase or sending Feishu")
    run.add_argument(
        "--include-seen",
        action="store_true",
        help="reprocess items already present in Supabase and allow duplicate Feishu sends",
    )
    run.add_argument(
        "--reanalyze-seen",
        action="store_true",
        help="reanalyze items already present in Supabase without resending already-alerted items",
    )
    run.add_argument("--use-deepseek", action="store_true", help="use DeepSeek when DEEPSEEK_API_KEY is set")
    run.add_argument("--deepseek-top-k", type=int, default=_env_int("DEEPSEEK_TOP_K", 30))
    run.add_argument("--deepseek-workers", type=int, default=_env_int("DEEPSEEK_WORKERS", 4))
    run.add_argument("--no-rule-filter", action="store_true", help="analyze all collected items")
    run.add_argument("--no-supabase", action="store_true", help="skip Supabase writes for local debugging")
    run.add_argument("--no-feishu", action="store_true", help="skip Feishu sending after processing")
    run.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    run.add_argument("--supabase-key", default=_supabase_key_from_env())
    run.add_argument("--supabase-table", default=os.environ.get("SUPABASE_TABLE", DEFAULT_SUPABASE_TABLE))
    run.add_argument("--webhook-url", default=os.environ.get("FEISHU_WEBHOOK_URL"))

    test = subparsers.add_parser("send-test", help="send a simple Feishu webhook test")
    test.add_argument("--webhook-url", default=os.environ.get("FEISHU_WEBHOOK_URL"))
    test.add_argument("--text", default="RWA Intel MVP 测试消息：飞书机器人已连通。")
    test.add_argument("--dry-run", action="store_true")

    dashboard_parser = subparsers.add_parser("dashboard", help="serve a Supabase-backed local intelligence dashboard")
    dashboard_parser.add_argument("--host", default=os.environ.get("DASHBOARD_HOST", DEFAULT_DASHBOARD_HOST))
    dashboard_parser.add_argument("--port", type=int, default=int(os.environ.get("DASHBOARD_PORT", DEFAULT_DASHBOARD_PORT)))
    dashboard_parser.add_argument("--no-open", action="store_true", help="do not open the browser automatically")
    dashboard_parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    dashboard_parser.add_argument("--supabase-key", default=_supabase_key_from_env())
    dashboard_parser.add_argument("--supabase-table", default=os.environ.get("SUPABASE_TABLE", DEFAULT_SUPABASE_TABLE))

    list_parser = subparsers.add_parser("list-sources", help="print enabled sources")
    list_parser.add_argument("--sources", default=str(DEFAULT_SOURCES_PATH))
    return parser


def list_sources(args: argparse.Namespace) -> int:
    sources = load_sources(args.sources)
    rows = [{"name": src.name, "kind": src.kind, "url": src.url, "priority": src.priority} for src in sources]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def send_test(args: argparse.Namespace) -> int:
    if args.dry_run:
        print(json.dumps({"payload": {"msg_type": "text", "content": {"text": args.text}}}, ensure_ascii=False, indent=2))
        return 0
    if not args.webhook_url:
        print("FEISHU_WEBHOOK_URL is required unless --dry-run is set.", file=sys.stderr)
        return 2
    result = send_text(args.webhook_url, args.text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def dashboard(args: argparse.Namespace) -> int:
    try:
        run_dashboard(
            host=args.host,
            port=args.port,
            supabase_url=args.supabase_url,
            supabase_key=args.supabase_key,
            table=args.supabase_table,
            open_browser=not args.no_open,
        )
    except (OSError, SupabaseError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def run_pipeline(args: argparse.Namespace) -> int:
    sources = load_sources(args.sources)
    items, source_errors = collect_sources(sources, limit_per_source=args.limit_per_source)
    collected_count = len(items)
    items = _dedupe_raw_items(items)
    use_supabase = not args.dry_run and not args.no_supabase
    item_states = {}
    selected = []
    selected_to_send = []
    skipped_date_items = []
    skipped_rule_items = []
    analysis_updates = []
    processed_count = 0
    skipped_seen = 0
    skipped_rule = 0
    skipped_date = 0
    candidates: list[tuple[RawItem, Analysis]] = []
    analysis_stats: dict[str, object] = {}

    try:
        if use_supabase:
            item_states = fetch_item_states(
                items,
                supabase_url=args.supabase_url,
                supabase_key=args.supabase_key,
                table=args.supabase_table,
            )
            upsert_collected_items(
                items,
                supabase_url=args.supabase_url,
                supabase_key=args.supabase_key,
                table=args.supabase_table,
                existing_states=item_states,
            )

        for item in items:
            if use_supabase and not args.include_seen and not args.reanalyze_seen and should_skip_seen(item, item_states):
                skipped_seen += 1
                continue
            if not args.all_dates and not _is_today_or_undated(item):
                skipped_date += 1
                skipped_date_items.append(item)
                continue
            extra_keywords = _source_keywords(sources, item.source_name)
            if not args.no_rule_filter and not passes_rule_filter(item, extra_keywords):
                skipped_rule += 1
                skipped_rule_items.append(item)
                continue
            candidates.append((item, heuristic_analyze(item)))

        analyzed_items, analysis_stats = _analyze_candidates(candidates, args)
        processed_count = len(analyzed_items)
        for item, analysis in analyzed_items:
            if analysis.alert_score >= args.min_score:
                selected.append((item, analysis))
                status = _analysis_status(item, analysis, args.min_score, item_states)
                if args.include_seen or not already_alerted(item, item_states):
                    selected_to_send.append((item, analysis))
            else:
                status = _analysis_status(item, analysis, args.min_score, item_states)
            analysis_updates.append((item, analysis, status))

        if use_supabase:
            upsert_status_items(
                skipped_date_items,
                STATUS_SKIPPED_DATE,
                supabase_url=args.supabase_url,
                supabase_key=args.supabase_key,
                table=args.supabase_table,
            )
            upsert_status_items(
                skipped_rule_items,
                STATUS_SKIPPED_RULE,
                supabase_url=args.supabase_url,
                supabase_key=args.supabase_key,
                table=args.supabase_table,
            )
            upsert_analysis_items(
                analysis_updates,
                supabase_url=args.supabase_url,
                supabase_key=args.supabase_key,
                table=args.supabase_table,
            )

        alerts_in_message = rank_alert_items(selected_to_send)[: args.top_n]
        alert_message_items = _with_feishu_summaries(alerts_in_message, args)
        message = format_alert(alert_message_items, source_errors=source_errors, max_items=args.top_n)
        summary = {
            "collected": collected_count,
            "unique_collected": len(items),
            "processed": processed_count,
            "selected": len(selected),
            "selected_to_send": len(selected_to_send),
            "alerts_to_send": len(alerts_in_message),
            "skipped_seen": skipped_seen,
            "skipped_rule": skipped_rule,
            "skipped_date": skipped_date,
            "source_errors": source_errors,
            "dry_run": args.dry_run,
            "reanalyze_seen": args.reanalyze_seen,
            "deepseek_enabled": bool(args.use_deepseek and os.environ.get("DEEPSEEK_API_KEY")),
            "analysis": analysis_stats,
            "supabase": {
                "enabled": use_supabase,
                "table": args.supabase_table if use_supabase else None,
                "existing_items": len(item_states),
                "collected_rows": len(items) if use_supabase else 0,
                "status_rows": (len(skipped_date_items) + len(skipped_rule_items)) if use_supabase else 0,
                "analysis_rows": len(analysis_updates) if use_supabase else 0,
            },
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("\n--- Feishu message preview ---\n")
        print(message)

        if args.dry_run:
            return 0
        if alerts_in_message and not args.no_feishu:
            if not args.webhook_url:
                print("FEISHU_WEBHOOK_URL is required to send alerts.", file=sys.stderr)
                return 2
            send_text(
                args.webhook_url,
                message,
                payload=build_alert_interactive_payload(
                    alert_message_items,
                    source_errors=source_errors,
                    max_items=args.top_n,
                ),
            )
            if use_supabase:
                mark_alert_sent(
                    alerts_in_message,
                    supabase_url=args.supabase_url,
                    supabase_key=args.supabase_key,
                    table=args.supabase_table,
                )
            print("Feishu alert sent.")
        return 0
    except (FeishuError, SupabaseError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _analyze_candidates(
    candidates: list[tuple[RawItem, Analysis]],
    args: argparse.Namespace,
) -> tuple[list[tuple[RawItem, Analysis]], dict[str, object]]:
    if not candidates:
        return [], {
            "deepseek_targets": 0,
            "deepseek_successes": 0,
            "deepseek_fallbacks": 0,
            "deepseek_workers": 0,
            "provider_counts": {},
        }

    use_deepseek = bool(args.use_deepseek and os.environ.get("DEEPSEEK_API_KEY"))
    deepseek_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash") if use_deepseek else None
    deepseek_targets: set[str] = set()
    if use_deepseek:
        top_k = max(0, int(getattr(args, "deepseek_top_k", 30)))
        ranked = sorted(candidates, key=lambda pair: pair[1].alert_score, reverse=True)
        deepseek_targets = {item_hash(item) for item, _ in ranked[:top_k]}

    if not deepseek_targets:
        results = list(candidates)
        return results, {
            "deepseek_targets": 0,
            "deepseek_successes": 0,
            "deepseek_fallbacks": 0,
            "deepseek_workers": 0,
            "deepseek_model": deepseek_model,
            "provider_counts": _provider_counts(results),
        }

    workers = max(1, min(int(getattr(args, "deepseek_workers", 4)), len(deepseek_targets)))
    results: list[tuple[RawItem, Analysis] | None] = [None] * len(candidates)

    def analyze_one(index: int, item: RawItem, fallback: Analysis) -> tuple[int, RawItem, Analysis]:
        if item_hash(item) in deepseek_targets:
            return index, item, deepseek_analyze(item, fallback)
        return index, item, fallback

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(analyze_one, index, item, fallback)
            for index, (item, fallback) in enumerate(candidates)
        ]
        for future in as_completed(futures):
            index, item, analysis = future.result()
            results[index] = (item, analysis)

    analyzed = [result for result in results if result is not None]
    deepseek_successes = sum(
        1 for item, analysis in analyzed if item_hash(item) in deepseek_targets and analysis.provider == "deepseek"
    )
    return analyzed, {
        "deepseek_targets": len(deepseek_targets),
        "deepseek_successes": deepseek_successes,
        "deepseek_fallbacks": len(deepseek_targets) - deepseek_successes,
        "deepseek_workers": workers,
        "deepseek_model": deepseek_model,
        "provider_counts": _provider_counts(analyzed),
    }


def _with_feishu_summaries(
    items: list[tuple[RawItem, Analysis]],
    args: argparse.Namespace,
) -> list[tuple[RawItem, Analysis]]:
    if not items:
        return []

    configured_workers = _env_int("DEEPSEEK_FEISHU_SUMMARY_WORKERS", 1)
    workers = max(1, min(configured_workers, len(items)))
    results: list[tuple[RawItem, Analysis] | None] = [None] * len(items)

    def summarize_one(index: int, item: RawItem, analysis: Analysis) -> tuple[int, RawItem, Analysis]:
        summary = deepseek_brief_summary(item, analysis, limit=50)
        return index, item, replace(analysis, summary=summary)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(summarize_one, index, item, analysis)
            for index, (item, analysis) in enumerate(items)
        ]
        for future in as_completed(futures):
            index, item, analysis = future.result()
            results[index] = (item, analysis)
    return [result for result in results if result is not None]


def _provider_counts(items: list[tuple[RawItem, Analysis]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for _, analysis in items:
        counts[analysis.provider] = counts.get(analysis.provider, 0) + 1
    return counts


def _analysis_status(
    item: RawItem,
    analysis: Analysis,
    min_score: int,
    item_states: dict[str, object],
) -> str:
    if already_alerted(item, item_states):
        return STATUS_SENT
    if analysis.alert_score < min_score:
        return STATUS_ANALYZED
    return STATUS_SELECTED


def _dedupe_raw_items(items: list[RawItem]) -> list[RawItem]:
    seen: set[str] = set()
    unique: list[RawItem] = []
    for item in items:
        digest = item_hash(item)
        if digest in seen:
            continue
        seen.add(digest)
        unique.append(item)
    return unique


def _source_keywords(sources: list[object], source_name: str) -> list[str]:
    for source in sources:
        if getattr(source, "name", None) == source_name:
            return list(getattr(source, "keywords", []))
    return []


def _supabase_key_from_env() -> str | None:
    return (
        os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY")
    )


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _is_today_or_undated(item: object, now: datetime | None = None) -> bool:
    published_at = getattr(item, "published_at", None)
    if not published_at:
        return True
    parsed = _parse_datetime(str(published_at))
    if not parsed:
        return True

    local_now = now.astimezone() if now else datetime.now().astimezone()
    if parsed.tzinfo is None:
        return parsed.date() == local_now.date()
    return parsed.astimezone(local_now.tzinfo).date() == local_now.date()


def _parse_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass

    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
