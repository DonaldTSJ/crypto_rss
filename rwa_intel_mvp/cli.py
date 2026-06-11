from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from .analyzer import analyze_item, passes_rule_filter
from .collectors import collect_sources
from .config import DEFAULT_SOURCES_PATH, load_local_env, load_sources
from .feishu import FeishuError, format_alert, send_text
from .obsidian import DEFAULT_OUTPUT_DIR, DEFAULT_VAULT_NAME, write_obsidian_markdown, write_obsidian_smoke_test
from .storage import DEFAULT_DB_PATH, StateStore


def main(argv: list[str] | None = None) -> int:
    load_local_env()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list-sources":
        return list_sources(args)
    if args.command == "send-test":
        return send_test(args)
    if args.command == "obsidian-test":
        return obsidian_test(args)
    if args.command == "run":
        return run_pipeline(args)

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crypto-rss", description="RWA/tokenization intelligence MVP")
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="collect, filter, analyze, and optionally push alerts")
    run.add_argument("--sources", default=str(DEFAULT_SOURCES_PATH), help="JSON source config path")
    run.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite state path")
    run.add_argument("--limit-per-source", type=int, default=8)
    run.add_argument("--min-score", type=int, default=70)
    run.add_argument("--top-n", type=int, default=10, help="maximum items in the final daily brief")
    run.add_argument("--all-dates", action="store_true", help="include dated items outside today's local date")
    run.add_argument("--dry-run", action="store_true", help="print payload without writing state or sending Feishu")
    run.add_argument("--include-seen", action="store_true", help="process items already present in state DB")
    run.add_argument("--use-deepseek", action="store_true", help="use DeepSeek when DEEPSEEK_API_KEY is set")
    run.add_argument("--no-rule-filter", action="store_true", help="analyze all collected items")
    run.add_argument("--write-obsidian", action="store_true", help="write selected items into Obsidian Markdown")
    run.add_argument("--no-feishu", action="store_true", help="skip Feishu sending after processing")
    run.add_argument("--obsidian-vault", default=os.environ.get("OBSIDIAN_VAULT_NAME", DEFAULT_VAULT_NAME))
    run.add_argument("--obsidian-vault-path", default=os.environ.get("OBSIDIAN_VAULT_PATH"))
    run.add_argument("--obsidian-dir", default=os.environ.get("OBSIDIAN_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
    run.add_argument("--webhook-url", default=os.environ.get("FEISHU_WEBHOOK_URL"))

    test = subparsers.add_parser("send-test", help="send a simple Feishu webhook test")
    test.add_argument("--webhook-url", default=os.environ.get("FEISHU_WEBHOOK_URL"))
    test.add_argument("--text", default="RWA Intel MVP 测试消息：飞书机器人已连通。")
    test.add_argument("--dry-run", action="store_true")

    obsidian = subparsers.add_parser("obsidian-test", help="write and verify a small Obsidian test note")
    obsidian.add_argument("--obsidian-vault", default=os.environ.get("OBSIDIAN_VAULT_NAME", DEFAULT_VAULT_NAME))
    obsidian.add_argument("--obsidian-vault-path", default=os.environ.get("OBSIDIAN_VAULT_PATH"))
    obsidian.add_argument("--obsidian-dir", default=os.environ.get("OBSIDIAN_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))

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


def obsidian_test(args: argparse.Namespace) -> int:
    path = write_obsidian_smoke_test(
        vault_name=args.obsidian_vault,
        vault_path=args.obsidian_vault_path,
        output_dir=args.obsidian_dir,
    )
    print(json.dumps({"obsidian_test_note": str(path)}, ensure_ascii=False, indent=2))
    return 0


def run_pipeline(args: argparse.Namespace) -> int:
    sources = load_sources(args.sources)
    items, source_errors = collect_sources(sources, limit_per_source=args.limit_per_source)
    store = None if args.dry_run else StateStore(args.db)
    selected = []
    processed_count = 0
    skipped_seen = 0
    skipped_rule = 0
    skipped_date = 0

    try:
        for item in items:
            if store and not args.include_seen and store.has_seen(item):
                skipped_seen += 1
                continue
            if not args.all_dates and not _is_today_or_undated(item):
                skipped_date += 1
                if store:
                    store.mark_seen(item)
                continue
            extra_keywords = _source_keywords(sources, item.source_name)
            if not args.no_rule_filter and not passes_rule_filter(item, extra_keywords):
                skipped_rule += 1
                if store:
                    store.mark_seen(item)
                continue
            analysis = analyze_item(item, use_deepseek=args.use_deepseek)
            processed_count += 1
            if store:
                store.mark_seen(item)
            if analysis.alert_score >= args.min_score:
                selected.append((item, analysis))

        message = format_alert(selected, source_errors=source_errors, max_items=args.top_n)
        obsidian_result = None
        if args.write_obsidian and not args.dry_run:
            obsidian_result = write_obsidian_markdown(
                selected,
                vault_name=args.obsidian_vault,
                vault_path=args.obsidian_vault_path,
                output_dir=args.obsidian_dir,
                max_items=args.top_n,
            )
        summary = {
            "collected": len(items),
            "processed": processed_count,
            "alerts": len(selected),
            "skipped_seen": skipped_seen,
            "skipped_rule": skipped_rule,
            "skipped_date": skipped_date,
            "source_errors": source_errors,
            "dry_run": args.dry_run,
            "deepseek_enabled": bool(args.use_deepseek and os.environ.get("DEEPSEEK_API_KEY")),
            "obsidian": obsidian_result.to_dict() if obsidian_result else ("dry_run_skipped" if args.write_obsidian else None),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("\n--- Feishu message preview ---\n")
        print(message)

        if args.dry_run:
            return 0
        if obsidian_result:
            print("Obsidian Markdown written.")
        if selected and not args.no_feishu:
            if not args.webhook_url:
                print("FEISHU_WEBHOOK_URL is required to send alerts.", file=sys.stderr)
                return 2
            send_text(args.webhook_url, message)
            for item, analysis in selected:
                store.mark_alert_sent(item, analysis)
            print("Feishu alert sent.")
        return 0
    except (FeishuError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if store:
            store.close()


def _source_keywords(sources: list[object], source_name: str) -> list[str]:
    for source in sources:
        if getattr(source, "name", None) == source_name:
            return list(getattr(source, "keywords", []))
    return []


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
