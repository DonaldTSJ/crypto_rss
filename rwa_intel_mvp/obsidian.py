from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .feishu import rank_alert_items
from .models import Analysis, RawItem


DEFAULT_OBSIDIAN_FOLDER = "RWA Intel"


def sync_obsidian_brief(
    items: list[tuple[RawItem, Analysis]],
    vault_path: str | Path,
    folder: str = DEFAULT_OBSIDIAN_FOLDER,
    source_errors: list[str] | None = None,
    max_items: int = 10,
    now: datetime | None = None,
) -> Path:
    vault = Path(vault_path).expanduser()
    target_dir = _safe_target_dir(vault, folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now or datetime.now().astimezone()
    output_path = _unique_note_path(target_dir, timestamp)
    output_path.write_text(
        _render_markdown(
            rank_alert_items(items)[:max_items],
            source_errors=source_errors or [],
            generated_at=timestamp,
        ),
        encoding="utf-8",
    )
    return output_path


def _safe_target_dir(vault: Path, folder: str) -> Path:
    clean_parts = [part for part in Path(folder or DEFAULT_OBSIDIAN_FOLDER).parts if part not in {"", ".", ".."}]
    target = vault.joinpath(*clean_parts).resolve()
    vault_resolved = vault.resolve()
    if target != vault_resolved and vault_resolved not in target.parents:
        raise ValueError("Obsidian target folder must stay inside the configured vault path.")
    return target


def _unique_note_path(target_dir: Path, timestamp: datetime) -> Path:
    stem = f"{timestamp:%Y-%m-%d-%H%M%S}-crypto-intel"
    candidate = target_dir / f"{stem}.md"
    index = 2
    while candidate.exists():
        candidate = target_dir / f"{stem}-{index}.md"
        index += 1
    return candidate


def _render_markdown(
    items: list[tuple[RawItem, Analysis]],
    source_errors: list[str],
    generated_at: datetime,
) -> str:
    lines = [
        "---",
        f"title: Crypto RWA Intel {generated_at:%Y-%m-%d %H:%M}",
        f"created: {generated_at.isoformat()}",
        "source: crypto_rss",
        "tags:",
        "  - crypto/intel",
        "  - rwa",
        "---",
        "",
        f"# Crypto / RWA Intel - {generated_at:%Y-%m-%d %H:%M}",
        "",
        f"- Items: {len(items)}",
        f"- Source errors: {len(source_errors)}",
        "",
    ]
    if not items:
        lines.extend(["本轮没有达到阈值的资讯。", ""])
    for index, (item, analysis) in enumerate(items, start=1):
        lines.extend(
            [
                f"## {index}. {_escape_markdown_heading(item.title)}",
                "",
                f"- source: {item.source_name}",
                f"- published: {item.published_at or 'unknown'}",
                f"- importance: {analysis.importance_score}",
                f"- alert_score: {analysis.alert_score}",
                f"- url: {item.url}",
                f"- categories: {', '.join(analysis.categories) if analysis.categories else 'none'}",
                f"- asset_classes: {', '.join(analysis.asset_classes) if analysis.asset_classes else 'none'}",
                "",
                analysis.summary.strip() or item.summary.strip() or item.title.strip(),
                "",
            ]
        )
    if source_errors:
        lines.extend(["## Source Errors", ""])
        lines.extend(f"- {error}" for error in source_errors)
        lines.append("")
    return "\n".join(lines)


def _escape_markdown_heading(value: str) -> str:
    return re.sub(r"\s+", " ", value or "Untitled").strip().replace("#", "\\#")
