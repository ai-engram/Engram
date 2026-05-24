"""
SQLite-backed store for namespace key shares on a miner.

One share per namespace. Only returned to callers that prove namespace ownership
via namespace_sig auth — the miner never reconstructs the full key.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_DEFAULT_DB = Path(os.getenv("KEY_SHARE_DB_PATH", "data/key_shares.db"))


class KeyShareStore:
    def __init__(self, db_path: Path = _DEFAULT_DB) -> None:
        self._db_path = db_path
        self._conn = self._open_db()

    def _open_db(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS key_shares (
                namespace   TEXT PRIMARY KEY,
                share_index INTEGER NOT NULL,
                share_hex   TEXT NOT NULL,
                threshold   INTEGER NOT NULL,
                total       INTEGER NOT NULL,
                stored_at   REAL NOT NULL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.commit()
        return conn

    def store(self, namespace: str, share_index: int, share_hex: str,
              threshold: int, total: int) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO key_shares
                (namespace, share_index, share_hex, threshold, total)
            VALUES (?, ?, ?, ?, ?)
        """, (namespace, share_index, share_hex, threshold, total))
        self._conn.commit()

    def get(self, namespace: str) -> dict | None:
        row = self._conn.execute(
            "SELECT share_index, share_hex, threshold, total FROM key_shares WHERE namespace = ?",
            (namespace,),
        ).fetchone()
        if row is None:
            return None
        return {"share_index": row[0], "share_hex": row[1], "threshold": row[2], "total": row[3]}

    def delete(self, namespace: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM key_shares WHERE namespace = ?", (namespace,)
        )
        self._conn.commit()
        return cur.rowcount > 0
