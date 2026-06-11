from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from .models import Analysis, RawItem


DEFAULT_VAULT_NAME = "Evolution"
DEFAULT_OUTPUT_DIR = "crypto"
OBSIDIAN_CONFIG_PATH = Path.home() / "Library/Application Support/obsidian/obsidian.json"


@dataclass
class ObsidianWriteResult:
    vault_path: Path
    output_dir: str
    daily_note: Path
    base_file: Path
    item_notes: list[Path]
    project_pages: list[Path]

    def to_dict(self) -> dict[str, object]:
        return {
            "vault_path": str(self.vault_path),
            "output_dir": self.output_dir,
            "daily_note": str(self.daily_note),
            "base_file": str(self.base_file),
            "item_notes": [str(path) for path in self.item_notes],
            "project_pages": [str(path) for path in self.project_pages],
        }


def discover_vault_path(
    vault_name: str = DEFAULT_VAULT_NAME,
    vault_path: str | Path | None = None,
    config_path: str | Path = OBSIDIAN_CONFIG_PATH,
) -> Path:
    if vault_path:
        return Path(vault_path).expanduser().resolve()

    config_file = Path(config_path).expanduser()
    if config_file.exists():
        payload = json.loads(config_file.read_text(encoding="utf-8"))
        for vault in payload.get("vaults", {}).values():
            candidate = Path(str(vault.get("path", ""))).expanduser()
            if candidate.name == vault_name:
                return candidate.resolve()

    raise FileNotFoundError(f"Obsidian vault not found: {vault_name}")


def write_obsidian_markdown(
    items: list[tuple[RawItem, Analysis]],
    vault_name: str = DEFAULT_VAULT_NAME,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    vault_path: str | Path | None = None,
    max_items: int = 10,
) -> ObsidianWriteResult:
    resolved_vault = discover_vault_path(vault_name=vault_name, vault_path=vault_path)
    root = resolved_vault / output_dir
    today = datetime.now().astimezone().date().isoformat()
    ranked = sorted(items, key=_business_rank_key, reverse=True)[:max_items]

    item_dir = root / "items" / today
    project_dir = root / "projects"
    daily_dir = root / "daily"
    for directory in [root, item_dir, project_dir, daily_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    base_file = root / "Crypto Intelligence.base"
    base_file.write_text(_base_content(output_dir), encoding="utf-8")

    item_notes: list[Path] = []
    project_pages: dict[str, Path] = {}
    daily_links: list[str] = []

    for item, analysis in ranked:
        item_path = item_dir / f"{_item_slug(item)}.md"
        note_body = _item_note_content(item, analysis, today)
        item_path.write_text(note_body, encoding="utf-8")
        item_notes.append(item_path)

        vault_link = _vault_link(item_path, resolved_vault, item.title)
        daily_links.append(f"- {vault_link} · {item.source_name} · score {analysis.alert_score}")

        for project in analysis.projects:
            project_path = project_dir / f"{_safe_filename(project)}.md"
            _upsert_project_page(project_path, resolved_vault, project, item, analysis, item_path)
            project_pages[project] = project_path

    daily_note = daily_dir / f"{today} Crypto Intelligence.md"
    daily_note.write_text(
        _daily_note_content(today, output_dir, daily_links),
        encoding="utf-8",
    )

    return ObsidianWriteResult(
        vault_path=resolved_vault,
        output_dir=output_dir,
        daily_note=daily_note,
        base_file=base_file,
        item_notes=item_notes,
        project_pages=list(project_pages.values()),
    )


def write_obsidian_smoke_test(
    vault_name: str = DEFAULT_VAULT_NAME,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    vault_path: str | Path | None = None,
) -> Path:
    resolved_vault = discover_vault_path(vault_name=vault_name, vault_path=vault_path)
    test_dir = resolved_vault / output_dir / "tests"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "cytop-obsidian-smoke-test.md"
    test_file.write_text(
        "\n".join(
            [
                "---",
                "type: cytop_smoke_test",
                "tags:",
                "  - crypto/test",
                "  - cytop/obsidian",
                f"created: {_obsidian_datetime(datetime.now().astimezone())}",
                "---",
                "# Cytop Obsidian Smoke Test",
                "",
                "Obsidian Markdown 写入链路已连通。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return test_file


def _item_note_content(item: RawItem, analysis: Analysis, today: str) -> str:
    title = item.title.strip() or "Untitled intelligence"
    tags = _tags_for_analysis(analysis)
    properties = {
        "type": "crypto_intel",
        "status": "inbox",
        "source": item.source_name,
        "source_kind": item.source_kind,
        "source_url": item.source_url,
        "url": item.url,
        "published": _date_part(item.published_at) or today,
        "fetched": _obsidian_datetime(_parse_datetime(item.fetched_at) or datetime.now().astimezone()),
        "relevance": analysis.relevance_score,
        "importance": analysis.importance_score,
        "alert_score": analysis.alert_score,
        "confidence": round(analysis.confidence, 3),
        "provider": analysis.provider,
        "projects": analysis.projects,
        "asset_classes": analysis.asset_classes,
        "categories": analysis.categories,
        "chains": analysis.chains,
        "jurisdictions": analysis.jurisdictions,
        "tags": tags,
    }
    return "\n".join(
        [
            _frontmatter(properties),
            f"# {title}",
            "",
            f"[原文链接]({item.url})" if item.url else "",
            "",
            "## 摘要",
            analysis.summary or item.summary or title,
            "",
            "## 业务影响",
            analysis.business_impact,
            "",
            "## 下一步",
            analysis.next_action,
            "",
            "## 识别理由",
            _bullet_list(analysis.reasons),
            "",
            "## 原始摘要",
            item.summary or item.raw_text[:2000] or "无",
            "",
        ]
    )


def _daily_note_content(today: str, output_dir: str, daily_links: list[str]) -> str:
    body = daily_links or ["- 今日暂无写入条目。"]
    return "\n".join(
        [
            "---",
            "type: crypto_daily",
            "tags:",
            "  - crypto/daily",
            "  - crypto/intel",
            f"date: {today}",
            "---",
            f"# Crypto Intelligence {today}",
            "",
            f"Base: [[{output_dir}/Crypto Intelligence.base|Crypto Intelligence]]",
            "",
            "## 今日情报",
            *body,
            "",
        ]
    )


def _base_content(output_dir: str) -> str:
    item_folder = f"{output_dir}/items"
    return "\n".join(
        [
            'filters:',
            '  and:',
            f'    - file.inFolder("{item_folder}")',
            '    - file.hasTag("crypto/intel")',
            'properties:',
            '  source:',
            '    displayName: Source',
            '  published:',
            '    displayName: Published',
            '  importance:',
            '    displayName: Importance',
            '  relevance:',
            '    displayName: Relevance',
            '  alert_score:',
            '    displayName: Alert Score',
            '  asset_classes:',
            '    displayName: Asset Classes',
            '  projects:',
            '    displayName: Projects',
            '  status:',
            '    displayName: Status',
            '  url:',
            '    displayName: URL',
            'views:',
            '  - type: table',
            '    name: "今日高价值"',
            '    limit: 50',
            '    order:',
            '      - file.name',
            '      - note.source',
            '      - note.published',
            '      - note.importance',
            '      - note.alert_score',
            '      - note.asset_classes',
            '      - note.projects',
            '      - note.status',
            '      - note.url',
            '  - type: table',
            '    name: "待深挖"',
            '    limit: 100',
            '    filters:',
            '      and:',
            '        - \'status == "inbox"\'',
            '    order:',
            '      - file.name',
            '      - note.source',
            '      - note.importance',
            '      - note.projects',
            '      - note.asset_classes',
            '',
        ]
    )


def _upsert_project_page(
    path: Path,
    vault_path: Path,
    project: str,
    item: RawItem,
    analysis: Analysis,
    item_path: Path,
) -> None:
    link = _vault_link(item_path, vault_path, item.title)
    entry = f"- {link} · {item.source_name} · score {analysis.alert_score}"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if entry in existing:
            return
        path.write_text(existing.rstrip() + "\n" + entry + "\n", encoding="utf-8")
        return

    path.write_text(
        "\n".join(
            [
                "---",
                "type: crypto_project",
                "status: tracking",
                "tags:",
                "  - crypto/project",
                f"project: {_yaml_scalar(project)}",
                "---",
                f"# {project}",
                "",
                "## 相关情报",
                entry,
                "",
            ]
        ),
        encoding="utf-8",
    )


def _business_rank_key(pair: tuple[RawItem, Analysis]) -> tuple[int, int, float]:
    item, analysis = pair
    labels = set(analysis.asset_classes + analysis.categories)
    source_text = f"{item.source_name} {item.source_kind} {item.source_url}".lower()
    if "regulation" in labels:
        tier = 6
    elif "exchange_operations" in labels:
        tier = 5
    elif {"stablecoin_reserves", "infrastructure"} & labels:
        tier = 4
    elif {"tokenized_treasuries", "tokenized_equities", "private_credit", "rwa"} & labels:
        tier = 3
    elif "github" in source_text or "x.com" in source_text or "twitter" in source_text:
        tier = 2
    else:
        tier = 1
    return (tier, analysis.alert_score, analysis.confidence)


def _frontmatter(properties: dict[str, object]) -> str:
    lines = ["---"]
    for key, value in properties.items():
        lines.extend(_yaml_property(key, value))
    lines.append("---")
    return "\n".join(lines)


def _yaml_property(key: str, value: object) -> list[str]:
    if isinstance(value, list):
        if not value:
            return [f"{key}: []"]
        return [f"{key}:"] + [f"  - {_yaml_scalar(item)}" for item in value]
    return [f"{key}: {_yaml_scalar(value)}"]


def _yaml_scalar(value: object) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    text = str(value).strip()
    if not text:
        return '""'
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _tags_for_analysis(analysis: Analysis) -> list[str]:
    tags = ["crypto/intel"]
    for label in analysis.asset_classes or analysis.categories:
        safe = re.sub(r"[^a-z0-9_-]+", "-", label.lower()).strip("-")
        if safe:
            tags.append(f"crypto/{safe}")
    return sorted(set(tags))


def _bullet_list(values: list[str]) -> str:
    if not values:
        return "- 无"
    return "\n".join(f"- {value}" for value in values)


def _item_slug(item: RawItem) -> str:
    digest = hashlib.sha1(item.identity_material.encode("utf-8")).hexdigest()[:8]
    return f"{_safe_filename(item.title)[:80]}-{digest}"


def _safe_filename(value: str) -> str:
    text = re.sub(r"[\\/:*?\"<>|#\n\r\t]+", " ", value).strip()
    text = re.sub(r"\s+", "-", text)
    return text or "untitled"


def _vault_link(path: Path, vault_path: Path, title: str) -> str:
    relative = path.relative_to(vault_path).with_suffix("")
    display = title.replace("|", " ").strip() or relative.name
    return f"[[{relative.as_posix()}|{display}]]"


def _date_part(value: str | None) -> str | None:
    if not value:
        return None
    parsed = _parse_datetime(value)
    return parsed.date().isoformat() if parsed else None


def _parse_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _obsidian_datetime(value: datetime) -> str:
    return value.astimezone().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
