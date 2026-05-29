"""Tests for ChallengeDispatcher SQLite persistence."""

import pytest

from engram.validator.challenge import ChallengeDispatcher, MinerProofRecord


@pytest.fixture
def dispatcher(tmp_path):
    return ChallengeDispatcher(db_path=tmp_path / "challenges.db")


# ── record_result persists ────────────────────────────────────────────────────

def test_record_survives_restart(tmp_path):
    db = tmp_path / "challenges.db"
    d1 = ChallengeDispatcher(db_path=db)
    for _ in range(5):
        d1.record_result("42", passed=True)
    d1.record_result("42", passed=False)

    d2 = ChallengeDispatcher(db_path=db)
    rec = d2.get_record("42")
    assert rec.total_challenges == 6
    assert rec.passed_challenges == 5


def test_multiple_miners_persist(tmp_path):
    db = tmp_path / "challenges.db"
    d1 = ChallengeDispatcher(db_path=db)
    d1.record_result("1", passed=True)
    d1.record_result("2", passed=False)
    d1.record_result("2", passed=False)

    d2 = ChallengeDispatcher(db_path=db)
    assert d2.get_record("1").total_challenges == 1
    assert d2.get_record("2").total_challenges == 2
    assert d2.get_record("2").passed_challenges == 0


def test_success_rate_preserved(tmp_path):
    db = tmp_path / "challenges.db"
    d1 = ChallengeDispatcher(db_path=db)
    d1.record_result("10", passed=True)
    d1.record_result("10", passed=True)
    d1.record_result("10", passed=False)

    d2 = ChallengeDispatcher(db_path=db)
    rec = d2.get_record("10")
    assert rec.success_rate == pytest.approx(2 / 3)


def test_should_slash_survives_restart(tmp_path):
    from engram.config import MIN_CHALLENGES_BEFORE_SLASH, SLASH_THRESHOLD
    db = tmp_path / "challenges.db"
    d1 = ChallengeDispatcher(db_path=db)
    # Record enough failures to hit slash threshold
    for _ in range(MIN_CHALLENGES_BEFORE_SLASH):
        d1.record_result("99", passed=False)

    d2 = ChallengeDispatcher(db_path=db)
    assert d2.get_record("99").should_slash


def test_fresh_dispatcher_starts_empty(tmp_path):
    d = ChallengeDispatcher(db_path=tmp_path / "fresh.db")
    assert d.get_record("0").total_challenges == 0


def test_accumulated_challenges_increment_correctly(dispatcher):
    for i in range(10):
        dispatcher.record_result("5", passed=(i % 2 == 0))
    rec = dispatcher.get_record("5")
    assert rec.total_challenges == 10
    assert rec.passed_challenges == 5
    assert rec.success_rate == pytest.approx(0.5)


def test_last_challenged_at_updated(dispatcher):
    import time
    before = time.time()
    dispatcher.record_result("3", passed=True)
    rec = dispatcher.get_record("3")
    assert rec.last_challenged_at >= before


def test_upsert_does_not_duplicate(tmp_path):
    db = tmp_path / "challenges.db"
    d = ChallengeDispatcher(db_path=db)
    for _ in range(3):
        d.record_result("7", passed=True)

    import sqlite3
    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM challenge_records WHERE uid='7'").fetchone()[0]
    assert count == 1
