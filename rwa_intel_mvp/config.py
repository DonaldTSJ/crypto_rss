from __future__ import annotations

import json
import os
from pathlib import Path

from .models import Source


DEFAULT_SOURCES_PATH = Path(__file__).with_name("default_sources.json")
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_local_env(paths: list[str | Path] | None = None) -> None:
    env_paths = [Path(path) for path in paths] if paths else [PROJECT_ROOT / ".env.local", PROJECT_ROOT / ".env"]
    for env_path in env_paths:
        if not env_path.exists():
            continue
        with env_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                key, value = _parse_env_line(line)
                if key and key not in os.environ:
                    os.environ[key] = value


def load_sources(path: str | Path | None = None) -> list[Source]:
    source_path = Path(path) if path else DEFAULT_SOURCES_PATH
    with source_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("sources", [])
    else:
        rows = []
    return [Source.from_dict(row) for row in rows if row.get("enabled", True)]


def _parse_env_line(line: str) -> tuple[str | None, str]:
    stripped = line.strip().lstrip("\ufeff")
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None, ""
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if value and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value
