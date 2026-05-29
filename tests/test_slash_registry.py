"""Tests for engram/validator/slash.py"""

import time

import pytest

from engram.config import SLASH_COOLDOWN_BLOCKS
from engram.validator.slash import SlashEvent, SlashRegistry


@pytest.fixture
def registry(tmp_path):
    return SlashRegistry(db_path=tmp_path / "slash.db")


def _slash(registry, uid, block=100, proof_rate=0.2, total=10, passed=2, hotkey=""):
    registry.slash(
        uid,
        hotkey=hotkey,
        current_block=block,
        proof_rate=proof_rate,
        total_challenges=total,
        passed_challenges=passed,
    )


# ── slash() and is_slashed() ──────────────────────────────────────────────────

def test_slashed_miner_is_active(registry):
    _slash(registry, uid=1, block=100)
    assert registry.is_slashed(1, current_block=101)


def test_unslashed_miner_is_not_active(registry):
    assert not registry.is_slashed(99, current_block=100)


def test_slash_cooldown_expires(registry):
    _slash(registry, uid=2, block=100)
    expiry = 100 + SLASH_COOLDOWN_BLOCKS
    assert registry.is_slashed(2, current_block=expiry - 1)
    assert not registry.is_slashed(2, current_block=expiry)


def test_expired_slash_not_in_slashed_uids(registry):
    _slash(registry, uid=3, block=100)
    uids = registry.slashed_uids(current_block=100 + SLASH_COOLDOWN_BLOCKS)
    assert 3 not in uids


def test_active_slash_in_slashed_uids(registry):
    _slash(registry, uid=4, block=200)
    uids = registry.slashed_uids(current_block=201)
    assert 4 in uids


def test_multiple_miners_tracked_independently(registry):
    _slash(registry, uid=10, block=100)
    _slash(registry, uid=11, block=200)
    uids = registry.slashed_uids(current_block=150)
    assert 10 in uids
    assert 11 in uids


def test_deduplication_no_repeat_recording(registry, tmp_path):
    import sqlite3
    db = tmp_path / "dedup.db"
    reg = SlashRegistry(db_path=db)
    _slash(reg, uid=5, block=100)
    _slash(reg, uid=5, block=101)  # should not insert again
    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM slash_events WHERE uid=5").fetchone()[0]
    assert count == 1


# ── persistence across restarts ───────────────────────────────────────────────

def test_slash_persists_across_instances(tmp_path):
    db = tmp_path / "slash.db"
    r1 = SlashRegistry(db_path=db)
    _slash(r1, uid=20, block=500)

    r2 = SlashRegistry(db_path=db)
    assert r2.is_slashed(20, current_block=501)


def test_cooldown_expiry_persists(tmp_path):
    db = tmp_path / "slash.db"
    r1 = SlashRegistry(db_path=db)
    _slash(r1, uid=21, block=500)
    r1.is_slashed(21, current_block=500 + SLASH_COOLDOWN_BLOCKS)  # expires

    r2 = SlashRegistry(db_path=db)
    assert not r2.is_slashed(21, current_block=500 + SLASH_COOLDOWN_BLOCKS + 1)


# ── history() ─────────────────────────────────────────────────────────────────

def test_history_records_slash(registry):
    _slash(registry, uid=30, block=300, proof_rate=0.1, hotkey="5FakeHotkey")
    events = registry.history(uid=30)
    assert len(events) == 1
    assert events[0].uid == 30
    assert events[0].proof_rate == pytest.approx(0.1)
    assert events[0].hotkey == "5FakeHotkey"


def test_history_all_miners(registry):
    _slash(registry, uid=40, block=400)
    _slash(registry, uid=41, block=400)
    events = registry.history()
    uids = {e.uid for e in events}
    assert {40, 41}.issubset(uids)


def test_history_empty_for_unknown_miner(registry):
    assert registry.history(uid=999) == []


# ── summary() ─────────────────────────────────────────────────────────────────

def test_summary_shows_active_count(registry):
    _slash(registry, uid=50, block=100)
    _slash(registry, uid=51, block=100)
    s = registry.summary()
    assert "active=2" in s


def test_summary_empty(registry):
    assert "active=0" in registry.summary()


# ── staking gate: _stake_for_hotkey ──────────────────────────────────────────

def test_stake_for_hotkey_returns_none_on_error():
    from engram.miner.ingest import _stake_for_hotkey

    class _BadSubtensor:
        def get_total_stake_for_hotkey(self, **_):
            raise RuntimeError("rpc error")

    result = _stake_for_hotkey(_BadSubtensor(), "5FakeHotkey")
    assert result is None


def test_stake_for_hotkey_returns_float_on_success():
    from engram.miner.ingest import _stake_for_hotkey

    class _GoodSubtensor:
        def get_total_stake_for_hotkey(self, hotkey_ss58):
            return 1.5

    result = _stake_for_hotkey(_GoodSubtensor(), "5FakeHotkey")
    assert result == pytest.approx(1.5)
