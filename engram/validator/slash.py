"""
Engram Validator — Persistent Slash Registry

Records miners that have been formally slashed (below proof-rate threshold)
so that:
  - Slash decisions survive validator restarts
  - Slashed miners stay at weight=0 for SLASH_COOLDOWN_BLOCKS before
    re-evaluation (prevents immediate weight recovery after being caught)
  - Every slash event is auditable: who, when, why, at what proof rate

A miner exits the "active slash" state when:
  1. Their cooldown period has elapsed (based on block number), AND
  2. They have not been re-slashed since

Schema:
    slash_events
        id             INTEGER PRIMARY KEY
        uid            INTEGER NOT NULL
        hotkey         TEXT    NOT NULL
        slashed_at_block INTEGER NOT NULL
        proof_rate     REAL    NOT NULL
        total_challenges INTEGER NOT NULL
        passed_challenges INTEGER NOT NULL
        active         INTEGER NOT NULL DEFAULT 1  -- 1=active, 0=expired
        created_at     REAL    NOT NULL
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from engram.config import SLASH_COOLDOWN_BLOCKS

_DEFAULT_DB = Path(os.getenv("SLASH_DB_PATH", "data/slash_registry.db"))


@dataclass
class SlashEvent:
    uid: int
    hotkey: str
    slashed_at_block: int
    proof_rate: float
    total_challenges: int
    passed_challenges: int
    active: bool
    created_at: float


class SlashRegistry:
    """
    Persists slash decisions so they survive validator restarts and enforce
    a cooldown window before a miner can be re-evaluated.

    Thread-safe for single-process use.
    """

    def __init__(self, db_path: Path = _DEFAULT_DB) -> None:
        self._db_path = db_path
        self._conn = self._open_db()

    def _open_db(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS slash_events (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                uid               INTEGER NOT NULL,
                hotkey            TEXT    NOT NULL DEFAULT '',
                slashed_at_block  INTEGER NOT NULL,
                proof_rate        REAL    NOT NULL,
                total_challenges  INTEGER NOT NULL,
                passed_challenges INTEGER NOT NULL,
                active            INTEGER NOT NULL DEFAULT 1,
                created_at        REAL    NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_uid_active ON slash_events(uid, active)")
        conn.commit()
        return conn

    # ── Public API ─────────────────────────────────────────────────────────────

    def slash(
        self,
        uid: int,
        *,
        hotkey: str = "",
        current_block: int,
        proof_rate: float,
        total_challenges: int,
        passed_challenges: int,
    ) -> None:
        """
        Record a slash event for a miner.

        Deduplicates: if the miner is already actively slashed, this updates
        the record rather than appending a duplicate (avoids log spam on every
        weight-setting cycle).
        """
        existing = self._active_event(uid)
        if existing is not None:
            return  # already slashed — don't re-record until cooldown expires

        self._conn.execute("""
            INSERT INTO slash_events
                (uid, hotkey, slashed_at_block, proof_rate,
                 total_challenges, passed_challenges, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """, (uid, hotkey, current_block, proof_rate,
              total_challenges, passed_challenges, time.time()))
        self._conn.commit()
        logger.error(
            "SLASH RECORDED | uid=%d | hotkey=%s | block=%d | "
            "proof_rate=%.2f | challenges=%d/%d",
            uid, hotkey[:12] if hotkey else "?", current_block,
            proof_rate, passed_challenges, total_challenges,
        )

    def is_slashed(self, uid: int, current_block: int) -> bool:
        """
        True if the miner is within their slash cooldown window.

        The miner exits the active slash state once current_block exceeds
        slashed_at_block + SLASH_COOLDOWN_BLOCKS.
        """
        event = self._active_event(uid)
        if event is None:
            return False
        cooldown_end = event.slashed_at_block + SLASH_COOLDOWN_BLOCKS
        if current_block >= cooldown_end:
            self._expire(uid)
            logger.info(
                "Slash cooldown expired | uid=%d | block=%d | cooldown_end=%d",
                uid, current_block, cooldown_end,
            )
            return False
        return True

    def slashed_uids(self, current_block: int) -> set[int]:
        """Return all UIDs currently within their slash cooldown."""
        rows = self._conn.execute(
            "SELECT uid, slashed_at_block FROM slash_events WHERE active=1"
        ).fetchall()
        active: set[int] = set()
        expired: list[int] = []
        for uid, slashed_at in rows:
            if current_block >= slashed_at + SLASH_COOLDOWN_BLOCKS:
                expired.append(uid)
            else:
                active.add(uid)
        for uid in expired:
            self._expire(uid)
        return active

    def history(self, uid: int | None = None, limit: int = 100) -> list[SlashEvent]:
        """Return slash history, optionally filtered to one miner."""
        if uid is not None:
            rows = self._conn.execute(
                "SELECT uid, hotkey, slashed_at_block, proof_rate, total_challenges, "
                "passed_challenges, active, created_at FROM slash_events "
                "WHERE uid=? ORDER BY id DESC LIMIT ?",
                (uid, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT uid, hotkey, slashed_at_block, proof_rate, total_challenges, "
                "passed_challenges, active, created_at FROM slash_events "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [SlashEvent(*r) for r in rows]

    def summary(self) -> str:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM slash_events WHERE active=1"
        ).fetchone()
        active = row[0] if row else 0
        row = self._conn.execute("SELECT COUNT(*) FROM slash_events").fetchone()
        total = row[0] if row else 0
        return f"slash: active={active} total_events={total}"

    # ── Internal ───────────────────────────────────────────────────────────────

    def _active_event(self, uid: int) -> SlashEvent | None:
        row = self._conn.execute(
            "SELECT uid, hotkey, slashed_at_block, proof_rate, total_challenges, "
            "passed_challenges, active, created_at FROM slash_events "
            "WHERE uid=? AND active=1 ORDER BY id DESC LIMIT 1",
            (uid,),
        ).fetchone()
        return SlashEvent(*row) if row else None

    def _expire(self, uid: int) -> None:
        self._conn.execute(
            "UPDATE slash_events SET active=0 WHERE uid=? AND active=1", (uid,)
        )
        self._conn.commit()
