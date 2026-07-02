from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SimulationCache:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS simulation_cache (
                    alpha_hash TEXT PRIMARY KEY,
                    alpha_id TEXT NOT NULL,
                    row_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def lookup(self, alpha_hash: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM simulation_cache WHERE alpha_hash = ?",
                (alpha_hash,),
            ).fetchone()
        return dict(row) if row else None

    def record(self, *, alpha_hash: str, alpha_id: str, row_id: str, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO simulation_cache(alpha_hash, alpha_id, row_id, status, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(alpha_hash) DO UPDATE SET
                    alpha_id = excluded.alpha_id,
                    row_id = excluded.row_id,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (alpha_hash, alpha_id, row_id, status, now, now),
            )

    def all_rows(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM simulation_cache ORDER BY updated_at, alpha_hash"
            ).fetchall()
        return [dict(row) for row in rows]
