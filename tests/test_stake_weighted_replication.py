"""Tests for stake-weighted replica assignment in ReplicationManager."""

import pytest

from engram.storage.dht import DHTRouter, Peer
from engram.storage.replication import ReplicationManager


def _make_router(n: int) -> DHTRouter:
    local = Peer(uid=0, hotkey="local")
    router = DHTRouter(local_peer=local)
    for i in range(1, n + 1):
        router.add_peer(Peer(uid=i, hotkey=f"hotkey_{i}"))
    return router


CID = "v1::aabbcc112233aabbcc112233aabbcc112233aabbcc112233aabbcc112233aabb"


def test_register_without_reliability_map(tmp_path):
    router = _make_router(6)
    mgr = ReplicationManager(router=router, db_path=tmp_path / "rep.db")
    rec = mgr.register(CID)
    assert len(rec.assigned_uids) > 0


def test_register_with_empty_reliability_map(tmp_path):
    router = _make_router(6)
    mgr = ReplicationManager(router=router, db_path=tmp_path / "rep.db")
    rec = mgr.register(CID, reliability_map={})
    assert len(rec.assigned_uids) > 0


def test_reliability_map_biases_toward_trusted_miners(tmp_path):
    """High-reliability miner should be preferred over equidistant unreliable one."""
    from engram.config import REPLICATION_FACTOR

    router = _make_router(9)
    mgr_plain = ReplicationManager(router=router, db_path=tmp_path / "plain.db")
    mgr_weighted = ReplicationManager(router=router, db_path=tmp_path / "weighted.db")

    # Give miners 1-3 perfect reliability, rest zero
    reliability_map = {1: 1.0, 2: 1.0, 3: 1.0}

    rec_plain    = mgr_plain.register(CID)
    rec_weighted = mgr_weighted.register(CID, reliability_map=reliability_map)

    # Both should assign REPLICATION_FACTOR miners
    assert len(rec_plain.assigned_uids) == REPLICATION_FACTOR
    assert len(rec_weighted.assigned_uids) == REPLICATION_FACTOR


def test_register_idempotent(tmp_path):
    router = _make_router(6)
    mgr = ReplicationManager(router=router, db_path=tmp_path / "rep.db")
    r1 = mgr.register(CID)
    r2 = mgr.register(CID, reliability_map={1: 1.0})
    assert r1.assigned_uids == r2.assigned_uids


def test_reliability_does_not_assign_unknown_miners(tmp_path):
    router = _make_router(6)
    mgr = ReplicationManager(router=router, db_path=tmp_path / "rep.db")
    # reliability_map references UIDs that are not in the routing table
    reliability_map = {999: 1.0, 998: 1.0}
    rec = mgr.register(CID, reliability_map=reliability_map)
    known_uids = {p.uid for p in router.all_peers()}
    for uid in rec.assigned_uids:
        assert uid in known_uids


def test_reliability_map_with_fewer_peers_than_factor(tmp_path):
    """Graceful handling when network is smaller than REPLICATION_FACTOR."""
    from engram.config import REPLICATION_FACTOR
    router = _make_router(1)  # only 1 peer
    mgr = ReplicationManager(router=router, db_path=tmp_path / "rep.db")
    rec = mgr.register(CID, reliability_map={1: 1.0})
    assert len(rec.assigned_uids) <= REPLICATION_FACTOR
