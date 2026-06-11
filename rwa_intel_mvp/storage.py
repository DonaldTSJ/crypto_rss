from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from .models import Analysis, RawItem, utc_now_iso


DEFAULT_DB_PATH = Path(".rwa_intel/state.sqlite3")


class StateStore:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_items (
                item_hash TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                source_name TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                alert_sent_at TEXT
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_hash TEXT NOT NULL,
                score INTEGER NOT NULL,
                provider TEXT NOT NULL,
                created_at TEXT NOT NULL,
                summary TEXT NOT NULL,
                business_impact TEXT NOT NULL,
                next_action TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def has_seen(self, item: RawItem) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_items WHERE item_hash = ?",
            (item_hash(item),),
        ).fetchone()
        return row is not None

    def mark_seen(self, item: RawItem) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO seen_items (item_hash, title, url, source_name, first_seen_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (item_hash(item), item.title, item.url, item.source_name, utc_now_iso()),
        )
        self.conn.commit()

    def mark_alert_sent(self, item: RawItem, analysis: Analysis) -> None:
        digest = item_hash(item)
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT OR IGNORE INTO seen_items (item_hash, title, url, source_name, first_seen_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (digest, item.title, item.url, item.source_name, now),
        )
        self.conn.execute("UPDATE seen_items SET alert_sent_at = ? WHERE item_hash = ?", (now, digest))
        self.conn.execute(
            """
            INSERT INTO alerts (item_hash, score, provider, created_at, summary, business_impact, next_action)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                digest,
                analysis.alert_score,
                analysis.provider,
                now,
                analysis.summary,
                analysis.business_impact,
                analysis.next_action,
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


def item_hash(item: RawItem) -> str:
    return hashlib.sha256(item.identity_material.encode("utf-8")).hexdigest()
