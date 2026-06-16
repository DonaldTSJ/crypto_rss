from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from .analyzer import deepseek_analyze, deepseek_brief_summary, heuristic_analyze, passes_rule_filter
from .collectors import collect_sources
from .config import DEFAULT_SOURCES_PATH, filter_sources, load_local_env, load_sources
from .dashboard import DEFAULT_DASHBOARD_HOST, DEFAULT_DASHBOARD_PORT, run_dashboard
from .feishu import FeishuError, build_alert_interactive_payload, format_alert, rank_alert_items, send_text
from .models import Analysis, RawItem, item_hash
from .obsidian import DEFAULT_OBSIDIAN_FOLDER, sync_obsidian_brief
from .supabase import (
    DEFAULT_SUPABASE_TABLE,
    STATUS_ANALYZED,
    STATUS_SELECTED,
    STATUS_SENT,
    STATUS_SKIPPED_DATE,
    STATUS_SKIPPED_RULE,
    SupabaseError,
    already_alerted,
    fetch_supabase_brief_rows,
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
    if args.command == "send-supabase":
        return send_supabase(args)
    if args.command == "dashboard":
        return dashboard(args)
    if args.command == "schedule":
        return schedule(args)
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
    run.add_argument(
        "--source-class",
        choices=["all", "regulatory", "message"],
        default="all",
        help="source class to run: all, regulatory, or message",
    )
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
    run.add_argument("--obsidian-sync", action="store_true", help="write the rendered brief into a local Obsidian vault")
    run.add_argument("--obsidian-vault", default=os.environ.get("OBSIDIAN_VAULT_PATH"))
    run.add_argument("--obsidian-folder", default=os.environ.get("OBSIDIAN_FOLDER", DEFAULT_OBSIDIAN_FOLDER))

    test = subparsers.add_parser("send-test", help="send a simple Feishu webhook test")
    test.add_argument("--webhook-url", default=os.environ.get("FEISHU_WEBHOOK_URL"))
    test.add_argument("--text", default="RWA Intel MVP 测试消息：飞书机器人已连通。")
    test.add_argument("--dry-run", action="store_true")

    send_supabase_parser = subparsers.add_parser(
        "send-supabase",
        help="send a Feishu brief from existing Supabase rows",
    )
    send_supabase_parser.add_argument(
        "--preset",
        choices=["recent", "regulatory", "sec", "us-regulatory"],
        default="recent",
        help="local filter preset for Supabase rows",
    )
    send_supabase_parser.add_argument("--top-n", type=int, default=10, help="maximum items in the final brief")
    send_supabase_parser.add_argument(
        "--days",
        type=int,
        help="look back this many run_date days; omit to read the latest available Supabase items",
    )
    send_supabase_parser.add_argument("--min-score", type=int, default=70)
    send_supabase_parser.add_argument(
        "--statuses",
        default=f"{STATUS_SELECTED},{STATUS_SENT}",
        help="comma-separated Supabase statuses to include",
    )
    send_supabase_parser.add_argument("--candidate-limit", type=int, default=200)
    send_supabase_parser.add_argument("--search", help="optional Supabase text search")
    send_supabase_parser.add_argument("--dry-run", action="store_true", help="print preview without sending Feishu")
    send_supabase_parser.add_argument("--sources", default=str(DEFAULT_SOURCES_PATH), help="JSON source config path")
    send_supabase_parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    send_supabase_parser.add_argument("--supabase-key", default=_supabase_key_from_env())
    send_supabase_parser.add_argument("--supabase-table", default=os.environ.get("SUPABASE_TABLE", DEFAULT_SUPABASE_TABLE))
    send_supabase_parser.add_argument("--webhook-url", default=os.environ.get("FEISHU_WEBHOOK_URL"))

    dashboard_parser = subparsers.add_parser("dashboard", help="serve a Supabase-backed local intelligence dashboard")
    dashboard_parser.add_argument("--host", default=os.environ.get("DASHBOARD_HOST", DEFAULT_DASHBOARD_HOST))
    dashboard_parser.add_argument("--port", type=int, default=int(os.environ.get("DASHBOARD_PORT", DEFAULT_DASHBOARD_PORT)))
    dashboard_parser.add_argument("--no-open", action="store_true", help="do not open the browser automatically")
    dashboard_parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    dashboard_parser.add_argument("--supabase-key", default=_supabase_key_from_env())
    dashboard_parser.add_argument("--supabase-table", default=os.environ.get("SUPABASE_TABLE", DEFAULT_SUPABASE_TABLE))

    schedule_parser = subparsers.add_parser("schedule", help="run the production pipeline on a local timer")
    schedule_parser.add_argument("--time", default="10:30", help="local wall-clock time in HH:MM, default 10:30")
    schedule_parser.add_argument(
        "--frequency",
        choices=["daily", "weekly"],
        default="daily",
        help="daily runs message sources; weekly runs regulatory sources unless --source-class overrides it",
    )
    schedule_parser.add_argument("--weekday", default="mon", help="weekly run day: mon, tue, wed, thu, fri, sat, sun")
    schedule_parser.add_argument("--sources", default=str(DEFAULT_SOURCES_PATH), help="JSON source config path")
    schedule_parser.add_argument("--source-class", choices=["all", "regulatory", "message"])
    schedule_parser.add_argument("--limit-per-source", type=int, default=8)
    schedule_parser.add_argument("--min-score", type=int, default=70)
    schedule_parser.add_argument("--top-n", type=int, default=10)
    schedule_parser.add_argument("--all-dates", action="store_true", help="include dated items outside today's local date")
    schedule_parser.add_argument("--deepseek-top-k", type=int, default=_env_int("DEEPSEEK_TOP_K", 30))
    schedule_parser.add_argument("--deepseek-workers", type=int, default=_env_int("DEEPSEEK_WORKERS", 4))
    schedule_parser.add_argument("--no-rule-filter", action="store_true", help="analyze all collected items")
    schedule_parser.add_argument("--no-supabase", action="store_true", help="skip Supabase writes for local debugging")
    schedule_parser.add_argument("--no-feishu", action="store_true", help="skip Feishu sending after processing")
    schedule_parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    schedule_parser.add_argument("--supabase-key", default=_supabase_key_from_env())
    schedule_parser.add_argument("--supabase-table", default=os.environ.get("SUPABASE_TABLE", DEFAULT_SUPABASE_TABLE))
    schedule_parser.add_argument("--webhook-url", default=os.environ.get("FEISHU_WEBHOOK_URL"))
    schedule_parser.add_argument("--obsidian-sync", action="store_true", help="write scheduled briefs into Obsidian")
    schedule_parser.add_argument("--obsidian-vault", default=os.environ.get("OBSIDIAN_VAULT_PATH"))
    schedule_parser.add_argument("--obsidian-folder", default=os.environ.get("OBSIDIAN_FOLDER", DEFAULT_OBSIDIAN_FOLDER))
    schedule_parser.add_argument("--run-on-start", action="store_true", help="run once immediately, then continue the configured schedule")
    schedule_parser.add_argument("--once", action="store_true", help="run once with the scheduled production defaults and exit")

    list_parser = subparsers.add_parser("list-sources", help="print enabled sources")
    list_parser.add_argument("--sources", default=str(DEFAULT_SOURCES_PATH))
    list_parser.add_argument("--source-class", choices=["all", "regulatory", "message"], default="all")
    return parser


def list_sources(args: argparse.Namespace) -> int:
    sources = load_sources(args.sources, source_class=args.source_class)
    rows = [
        {
            "name": src.name,
            "kind": src.kind,
            "url": src.url,
            "priority": src.priority,
            "source_class": src.source_class,
            "schedule_frequency": src.schedule_frequency,
        }
        for src in sources
    ]
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


def send_supabase(args: argparse.Namespace) -> int:
    top_n = max(1, int(args.top_n))
    statuses = _parse_statuses(args.statuses)
    run_date_gte = _send_supabase_since_date(args.days) if args.days is not None else None
    try:
        sources = load_sources(args.sources)
        rows = fetch_supabase_brief_rows(
            supabase_url=args.supabase_url,
            supabase_key=args.supabase_key,
            table=args.supabase_table,
            statuses=statuses,
            run_date_gte=run_date_gte,
            min_score=args.min_score,
            search=args.search,
            limit=args.candidate_limit,
        )
        filtered_rows = _filter_supabase_rows_by_preset(rows, args.preset, sources)
        source_by_name = {source.name: source for source in sources}
        candidates = [
            _supabase_row_to_alert_pair(row, source_by_name)
            for row in filtered_rows
            if row.get("title") or row.get("url")
        ]
        card_items = rank_alert_items(candidates)[:top_n]
        message = format_alert(card_items, max_items=top_n)
        summary = {
            "preset": args.preset,
            "top_n": top_n,
            "run_date_gte": run_date_gte,
            "statuses": statuses,
            "candidate_rows": len(rows),
            "matched_rows": len(filtered_rows),
            "card_items": len(card_items),
            "dry_run": args.dry_run,
            "writeback": False,
            "supabase": {
                "enabled": True,
                "table": args.supabase_table,
            },
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("\n--- Feishu message preview ---\n")
        print(message)

        if args.dry_run:
            return 0
        if not args.webhook_url:
            print("FEISHU_WEBHOOK_URL is required to send the Feishu card.", file=sys.stderr)
            return 2
        send_text(
            args.webhook_url,
            message,
            payload=build_alert_interactive_payload(card_items, max_items=top_n),
        )
        print("Feishu Supabase card sent. Supabase writeback skipped.")
        return 0
    except (FeishuError, SupabaseError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


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


def schedule(args: argparse.Namespace) -> int:
    try:
        hour, minute = _parse_schedule_time(args.time)
        weekday = _parse_weekday(args.weekday)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.once:
        return run_pipeline(_scheduled_run_args(args))

    print(
        json.dumps(
            {
                "scheduler": args.frequency,
                "time": f"{hour:02d}:{minute:02d}",
                "weekday": args.weekday if args.frequency == "weekly" else None,
                "source_class": _schedule_source_class(args),
                "timezone": datetime.now().astimezone().tzname(),
                "run_on_start": args.run_on_start,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.run_on_start:
        run_pipeline(_scheduled_run_args(args))

    while True:
        next_run = (
            _next_weekly_run(weekday, hour, minute)
            if args.frequency == "weekly"
            else _next_daily_run(hour, minute)
        )
        wait_seconds = max(1, int((next_run - datetime.now().astimezone()).total_seconds()))
        print(f"Next scheduled run: {next_run.isoformat()}")
        try:
            time.sleep(wait_seconds)
            code = run_pipeline(_scheduled_run_args(args))
            if code:
                print(f"Scheduled run exited with code {code}; waiting for the next day.", file=sys.stderr)
        except KeyboardInterrupt:
            print("\nScheduler stopped.")
            return 0
        except Exception as exc:  # noqa: BLE001 - local scheduler should keep the next run alive.
            print(f"Scheduled run failed: {exc}", file=sys.stderr)


def _scheduled_run_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        command="run",
        sources=args.sources,
        source_class=_schedule_source_class(args),
        limit_per_source=args.limit_per_source,
        min_score=args.min_score,
        top_n=args.top_n,
        all_dates=bool(args.all_dates or args.frequency == "weekly"),
        dry_run=False,
        include_seen=False,
        reanalyze_seen=True,
        use_deepseek=True,
        deepseek_top_k=args.deepseek_top_k,
        deepseek_workers=args.deepseek_workers,
        no_rule_filter=args.no_rule_filter,
        no_supabase=args.no_supabase,
        no_feishu=args.no_feishu,
        supabase_url=args.supabase_url,
        supabase_key=args.supabase_key,
        supabase_table=args.supabase_table,
        webhook_url=args.webhook_url,
        obsidian_sync=args.obsidian_sync,
        obsidian_vault=args.obsidian_vault,
        obsidian_folder=args.obsidian_folder,
    )


def _schedule_source_class(args: argparse.Namespace) -> str:
    if getattr(args, "source_class", None):
        return args.source_class
    return "regulatory" if args.frequency == "weekly" else "message"


def _parse_schedule_time(value: str) -> tuple[int, int]:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError("--time must use HH:MM format.")
    try:
        hour, minute = (int(part) for part in parts)
    except ValueError as exc:
        raise ValueError("--time must use HH:MM format.") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("--time must be a valid local time between 00:00 and 23:59.")
    return hour, minute


def _next_daily_run(hour: int, minute: int, now: datetime | None = None) -> datetime:
    local_now = now.astimezone() if now else datetime.now().astimezone()
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate


def _parse_weekday(value: str) -> int:
    weekdays = {
        "mon": 0,
        "monday": 0,
        "tue": 1,
        "tuesday": 1,
        "wed": 2,
        "wednesday": 2,
        "thu": 3,
        "thursday": 3,
        "fri": 4,
        "friday": 4,
        "sat": 5,
        "saturday": 5,
        "sun": 6,
        "sunday": 6,
    }
    normalized = value.strip().lower()
    if normalized not in weekdays:
        raise ValueError("--weekday must be one of mon, tue, wed, thu, fri, sat, sun.")
    return weekdays[normalized]


def _next_weekly_run(weekday: int, hour: int, minute: int, now: datetime | None = None) -> datetime:
    local_now = now.astimezone() if now else datetime.now().astimezone()
    days_ahead = (weekday - local_now.weekday()) % 7
    candidate = (local_now + timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=7)
    return candidate


def run_pipeline(args: argparse.Namespace) -> int:
    sources = load_sources(args.sources)
    sources = filter_sources(sources, getattr(args, "source_class", "all"))
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
        selected_in_message = rank_alert_items(selected)[: args.top_n]
        if args.reanalyze_seen and selected_in_message:
            card_source_items = selected_in_message
        else:
            card_source_items = alerts_in_message or selected_in_message
        alert_message_items = _with_feishu_summaries(card_source_items, args)
        obsidian_path = None
        if getattr(args, "obsidian_sync", False) and not args.dry_run:
            if not getattr(args, "obsidian_vault", None):
                print("OBSIDIAN_VAULT_PATH or --obsidian-vault is required when --obsidian-sync is set.", file=sys.stderr)
                return 2
            obsidian_path = sync_obsidian_brief(
                alert_message_items,
                vault_path=args.obsidian_vault,
                folder=getattr(args, "obsidian_folder", DEFAULT_OBSIDIAN_FOLDER),
                source_errors=source_errors,
                max_items=args.top_n,
            )
        message = format_alert(alert_message_items, source_errors=source_errors, max_items=args.top_n)
        summary = {
            "source_class": getattr(args, "source_class", "all"),
            "sources": len(sources),
            "collected": collected_count,
            "unique_collected": len(items),
            "processed": processed_count,
            "selected": len(selected),
            "selected_to_send": len(selected_to_send),
            "alerts_to_send": len(alerts_in_message),
            "card_items": len(card_source_items),
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
            "obsidian": {
                "enabled": bool(getattr(args, "obsidian_sync", False)),
                "path": str(obsidian_path) if obsidian_path else None,
            },
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("\n--- Feishu message preview ---\n")
        print(message)

        if args.dry_run:
            return 0
        if not args.no_feishu:
            if not args.webhook_url:
                print("FEISHU_WEBHOOK_URL is required to send the Feishu card.", file=sys.stderr)
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
            if alerts_in_message and use_supabase:
                mark_alert_sent(
                    alerts_in_message,
                    supabase_url=args.supabase_url,
                    supabase_key=args.supabase_key,
                    table=args.supabase_table,
                )
            if alerts_in_message:
                print("Feishu alert sent.")
            else:
                print("Feishu summary card sent.")
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


def _parse_statuses(value: str) -> list[str]:
    statuses = [part.strip() for part in (value or "").split(",") if part.strip()]
    return statuses or [STATUS_SELECTED, STATUS_SENT]


def _send_supabase_since_date(days: int) -> str:
    lookback_days = max(1, int(days))
    since = datetime.now().astimezone().date() - timedelta(days=lookback_days - 1)
    return since.isoformat()


def _filter_supabase_rows_by_preset(
    rows: list[dict[str, object]],
    preset: str,
    sources: list[object],
) -> list[dict[str, object]]:
    normalized = (preset or "recent").strip().lower()
    if normalized == "recent":
        return list(rows)

    source_by_name = {str(getattr(source, "name", "")): source for source in sources}
    filtered: list[dict[str, object]] = []
    for row in rows:
        source = source_by_name.get(_row_text(row, "source_name"))
        if normalized == "regulatory" and _row_is_regulatory(row, source):
            filtered.append(row)
        elif normalized == "sec" and _row_is_sec(row, source):
            filtered.append(row)
        elif normalized == "us-regulatory" and _row_is_us_regulatory(row, source):
            filtered.append(row)
    return filtered


def _supabase_row_to_alert_pair(
    row: dict[str, object],
    source_by_name: dict[str, object],
) -> tuple[RawItem, Analysis]:
    source_name = _row_text(row, "source_name")
    source = source_by_name.get(source_name)
    summary = _row_text(row, "summary") or _row_text(row, "raw_summary")
    item = RawItem(
        source_name=source_name,
        source_kind=_row_text(row, "source_kind"),
        source_url=_row_text(row, "source_url"),
        source_category=str(getattr(source, "category", "news")),
        title=_row_text(row, "title"),
        url=_row_text(row, "url"),
        published_at=_row_text(row, "published_at") or None,
        summary=summary,
        raw_text=_row_text(row, "raw_text"),
    )
    analysis_data = dict(row)
    alert_score = analysis_data.get("alert_score")
    if analysis_data.get("relevance_score") is None:
        analysis_data["relevance_score"] = alert_score
    if analysis_data.get("importance_score") is None:
        analysis_data["importance_score"] = alert_score
    provider = _row_text(row, "provider") or "supabase"
    analysis = Analysis.from_dict(analysis_data, provider=provider)
    if not analysis.summary:
        analysis = replace(analysis, summary=item.summary or item.title)
    return item, analysis


def _row_is_regulatory(row: dict[str, object], source: object | None) -> bool:
    if getattr(source, "source_class", None) == "regulatory":
        return True
    blob = _source_blob(row, source)
    return any(
        token in blob
        for token in [
            "sec.gov",
            "cftc.gov",
            "finra.org",
            "federalregister.gov",
            "rulemaking",
            "regulation",
            "regulatory",
            "enforcement",
        ]
    )


def _row_is_sec(row: dict[str, object], source: object | None) -> bool:
    blob = _source_blob(row, source)
    return "sec.gov" in blob or "securities and exchange commission" in blob or bool(re.search(r"\bsec\b", blob))


def _row_is_us_regulatory(row: dict[str, object], source: object | None) -> bool:
    if not _row_is_regulatory(row, source):
        return False
    blob = _source_blob(row, source)
    return any(
        token in blob
        for token in [
            "sec.gov",
            "cftc.gov",
            "finra.org",
            "federalregister.gov",
            "dtcc.com",
            "theocc.com",
            "occ.gov",
            "nyse.com",
            "nasdaq.com",
            "securities and exchange commission",
            "commodity futures trading commission",
            "financial industry regulatory authority",
            "federal register",
            "dtcc",
            "nyse",
            "nasdaq",
        ]
    )


def _source_blob(row: dict[str, object], source: object | None) -> str:
    parts: list[object] = [
        row.get("source_name"),
        row.get("source_kind"),
        row.get("source_url"),
        row.get("jurisdictions"),
    ]
    if source:
        parts.extend(
            [
                getattr(source, "name", ""),
                getattr(source, "kind", ""),
                getattr(source, "url", ""),
                getattr(source, "category", ""),
                getattr(source, "source_class", ""),
                getattr(source, "keywords", []),
            ]
        )
    return " ".join(_flatten_text_parts(parts)).lower()


def _flatten_text_parts(parts: list[object]) -> list[str]:
    texts: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (list, tuple, set)):
            texts.extend(_flatten_text_parts(list(part)))
            continue
        text = str(part).strip()
        if text:
            texts.append(text)
    return texts


def _row_text(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    return "" if value is None else str(value).strip()


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
