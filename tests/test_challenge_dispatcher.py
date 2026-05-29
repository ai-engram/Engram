"""Tests for engram/validator/challenge.py — ChallengeDispatcher (no Rust required)."""

import pytest
from engram.validator.challenge import ChallengeDispatcher, MinerProofRecord
from engram.config import MIN_CHALLENGES_BEFORE_SLASH, SLASH_THRESHOLD


@pytest.fixture
def dispatcher(tmp_path) -> ChallengeDispatcher:
    return ChallengeDispatcher(validator_hotkey_hex="0" * 64, db_path=tmp_path / "challenges.db")


TEST_CID = "v1::" + "a" * 64


# ── CID registration ──────────────────────────────────────────────────────────

def test_register_cid_and_pick(dispatcher: ChallengeDispatcher) -> None:
    dispatcher.register_cid(TEST_CID)
    picked = dispatcher.pick_random_cid()
    assert picked == TEST_CID


def test_pick_random_cid_empty_returns_none(dispatcher: ChallengeDispatcher) -> None:
    assert dispatcher.pick_random_cid() is None


def test_duplicate_cid_not_added_twice(dispatcher: ChallengeDispatcher) -> None:
    dispatcher.register_cid(TEST_CID)
    dispatcher.register_cid(TEST_CID)
    assert dispatcher._known_cids.count(TEST_CID) == 1


def test_max_cids_evicts_oldest(dispatcher: ChallengeDispatcher) -> None:
    from engram.config import MAX_KNOWN_CIDS
    cids = ["v1::" + chr(ord("a") + i % 26) * 64 + str(i)[-1] for i in range(MAX_KNOWN_CIDS + 1)]
    # Use unique CIDs to avoid dedup
    for i, c in enumerate(cids):
        unique = f"v1::{'%064d' % i}"
        dispatcher.register_cid(unique)
    assert len(dispatcher._known_cids) == MAX_KNOWN_CIDS


# ── MinerProofRecord ──────────────────────────────────────────────────────────

def test_initial_success_rate_is_zero(dispatcher: ChallengeDispatcher) -> None:
    record = dispatcher.get_record("miner1")
    assert record.success_rate == 0.0


def test_success_rate_after_passes(dispatcher: ChallengeDispatcher) -> None:
    dispatcher.register_cid(TEST_CID)
    for _ in range(3):
        dispatcher.record_result("miner1", passed=True)
    dispatcher.record_result("miner1", passed=False)
    record = dispatcher.get_record("miner1")
    assert record.success_rate == pytest.approx(0.75)


def test_should_slash_below_threshold(dispatcher: ChallengeDispatcher) -> None:
    for _ in range(MIN_CHALLENGES_BEFORE_SLASH):
        dispatcher.record_result("bad_miner", passed=False)
    record = dispatcher.get_record("bad_miner")
    assert record.should_slash is True


def test_should_not_slash_insufficient_challenges(dispatcher: ChallengeDispatcher) -> None:
    for _ in range(MIN_CHALLENGES_BEFORE_SLASH - 1):
        dispatcher.record_result("new_miner", passed=False)
    record = dispatcher.get_record("new_miner")
    assert record.should_slash is False


def test_should_not_slash_high_pass_rate(dispatcher: ChallengeDispatcher) -> None:
    for _ in range(MIN_CHALLENGES_BEFORE_SLASH):
        dispatcher.record_result("good_miner", passed=True)
    record = dispatcher.get_record("good_miner")
    assert record.should_slash is False


# ── UID validation ────────────────────────────────────────────────────────────

def test_invalid_uid_raises(dispatcher: ChallengeDispatcher) -> None:
    with pytest.raises(ValueError, match="Invalid miner UID"):
        dispatcher.get_record("bad uid!")


def test_valid_uid_formats(dispatcher: ChallengeDispatcher) -> None:
    for uid in ("1", "miner_1", "node-2", "UID.123"):
        record = dispatcher.get_record(uid)
        assert record.uid == uid


# ── record_result ─────────────────────────────────────────────────────────────

def test_record_result_increments_total(dispatcher: ChallengeDispatcher) -> None:
    dispatcher.record_result("m1", passed=True)
    dispatcher.record_result("m1", passed=False)
    record = dispatcher.get_record("m1")
    assert record.total_challenges == 2
    assert record.passed_challenges == 1


def test_record_result_updates_last_challenged_at(dispatcher: ChallengeDispatcher) -> None:
    import time
    before = time.time()
    dispatcher.record_result("m2", passed=True)
    after = time.time()
    record = dispatcher.get_record("m2")
    assert before <= record.last_challenged_at <= after


# ── all_success_rates / slashable_miners ─────────────────────────────────────

def test_all_success_rates(dispatcher: ChallengeDispatcher) -> None:
    for _ in range(4):
        dispatcher.record_result("good", passed=True)
    for _ in range(4):
        dispatcher.record_result("bad", passed=False)
    rates = dispatcher.all_success_rates()
    assert rates["good"] == pytest.approx(1.0)
    assert rates["bad"] == pytest.approx(0.0)


def test_slashable_miners(dispatcher: ChallengeDispatcher) -> None:
    for _ in range(MIN_CHALLENGES_BEFORE_SLASH):
        dispatcher.record_result("slashable", passed=False)
    for _ in range(MIN_CHALLENGES_BEFORE_SLASH):
        dispatcher.record_result("safe", passed=True)
    slashable = dispatcher.slashable_miners()
    assert "slashable" in slashable
    assert "safe" not in slashable


# ── build_challenge without Rust ──────────────────────────────────────────────

def test_build_challenge_returns_none_without_rust(dispatcher: ChallengeDispatcher) -> None:
    result = dispatcher.build_challenge(TEST_CID)
    # Without Rust, returns None; with Rust, returns a challenge object
    assert result is None or hasattr(result, "nonce_hex")


def test_verify_response_returns_false_without_rust(dispatcher: ChallengeDispatcher) -> None:
    class FakeChallenge:
        nonce_hex = "abc"
        expires_at = 9999999999.0
    result = dispatcher.verify_response(FakeChallenge(), "hash", "proof", [0.1, 0.2])
    assert result is False
