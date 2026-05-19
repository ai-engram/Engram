"""
Managed mining node pool.

Engram runs a pool of pre-configured cloud mining nodes. When a user starts
a session, we allocate a free node from the pool and bind it to their hotkey.
When the session ends, we release the node back to the pool.

Each node is a running miner.py instance on a cloud VM:
  - Pre-registered on Bittensor testnet (netuid 450)
  - Has its own node hotkey (not the user's hotkey)
  - Accepts only sessions signed by the allocated controller hotkey
  - Reports stats via its /stats endpoint

Node pool config lives in the CLOUD_NODE_POOL env var (JSON array) or
data/node_pool.json. Each entry:
  {
    "endpoint": "https://1.2.3.4:8091",
    "hotkey":   "5Grwva...",
    "region":   "us-east-1"
  }
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp
from loguru import logger


@dataclass
class MiningNode:
    endpoint:    str          # https://<ip>:<port>
    hotkey:      str          # node's Bittensor hotkey SS58
    region:      str = "global"
    allocated_to: str | None = None     # session_id currently using this node
    allocated_at: float | None = None


class NodePool:
    """
    Thread-safe pool of managed mining nodes.

    Allocation is greedy (first available); future versions could match by
    region or latency to the user's location.
    """

    _DEFAULT_PATH = Path(os.getenv("CLOUD_NODE_POOL_PATH", "data/node_pool.json"))

    def __init__(self, nodes: list[MiningNode] | None = None) -> None:
        self._lock  = threading.Lock()
        self._nodes = nodes or self._load_from_env_or_file()
        logger.info(f"Node pool ready | {len(self._nodes)} nodes loaded")

    # ── Allocation ────────────────────────────────────────────────────────────

    def allocate(self, session_id: str) -> MiningNode | None:
        """Allocate a free node to a session. Returns None if pool is full."""
        with self._lock:
            for node in self._nodes:
                if node.allocated_to is None:
                    node.allocated_to = session_id
                    node.allocated_at = time.time()
                    logger.info(f"Node allocated | session={session_id[:8]} endpoint={node.endpoint}")
                    return node
        logger.warning("Node pool exhausted — no free nodes available")
        return None

    def release(self, session_id: str) -> None:
        """Release the node allocated to a session back to the pool."""
        with self._lock:
            for node in self._nodes:
                if node.allocated_to == session_id:
                    node.allocated_to = None
                    node.allocated_at = None
                    logger.info(f"Node released | session={session_id[:8]} endpoint={node.endpoint}")
                    return

    def get_for_session(self, session_id: str) -> MiningNode | None:
        with self._lock:
            for node in self._nodes:
                if node.allocated_to == session_id:
                    return node
        return None

    def available_count(self) -> int:
        with self._lock:
            return sum(1 for n in self._nodes if n.allocated_to is None)

    def total_count(self) -> int:
        return len(self._nodes)

    # ── Node health polling ───────────────────────────────────────────────────

    async def fetch_stats(self, session_id: str) -> dict[str, Any]:
        """
        Poll the /stats endpoint on the node allocated to a session.
        Returns an empty dict if the node is unreachable.
        """
        node = self.get_for_session(session_id)
        if not node:
            return {}
        try:
            async with aiohttp.ClientSession() as http:
                async with http.get(
                    f"{node.endpoint}/stats",
                    timeout=aiohttp.ClientTimeout(total=5),
                    ssl=False,
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as exc:
            logger.debug(f"Stats fetch failed for {node.endpoint}: {exc}")
        return {}

    async def ping(self, node: MiningNode) -> bool:
        """Check if a node is reachable."""
        try:
            async with aiohttp.ClientSession() as http:
                async with http.get(
                    f"{node.endpoint}/health",
                    timeout=aiohttp.ClientTimeout(total=3),
                    ssl=False,
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    # ── Loader ────────────────────────────────────────────────────────────────

    @classmethod
    def _load_from_env_or_file(cls) -> list[MiningNode]:
        # Priority 1: CLOUD_NODE_POOL env var (JSON array)
        raw = os.getenv("CLOUD_NODE_POOL")
        if raw:
            try:
                return [MiningNode(**n) for n in json.loads(raw)]
            except Exception as exc:
                logger.warning(f"CLOUD_NODE_POOL parse error: {exc}")

        # Priority 2: data/node_pool.json file
        if cls._DEFAULT_PATH.exists():
            try:
                entries = json.loads(cls._DEFAULT_PATH.read_text())
                return [MiningNode(**n) for n in entries]
            except Exception as exc:
                logger.warning(f"node_pool.json load error: {exc}")

        # Fallback: empty pool (operator must configure nodes)
        logger.warning(
            "No mining nodes configured. "
            "Set CLOUD_NODE_POOL env var or create data/node_pool.json."
        )
        return []

    def to_public_list(self) -> list[dict]:
        """Safe subset of pool state for the /nodes endpoint."""
        with self._lock:
            return [
                {
                    "region":    n.region,
                    "available": n.allocated_to is None,
                    "endpoint":  n.endpoint,  # expose so mobile can ping directly
                }
                for n in self._nodes
            ]
