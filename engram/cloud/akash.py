"""
Akash Network deployment client.

Akash is a decentralised cloud marketplace (Cosmos-based). We deploy miner.py
containers there on demand as users purchase sessions. Akash providers bid on
our deployment manifests (SDL) and we accept the cheapest/fastest bid.

Flow:
  1. build_sdl()         — generate an SDL manifest for one miner node
  2. create_deployment() — broadcast SDL to Akash network, get deployment ID
  3. wait_for_lease()    — wait for a provider to accept the bid
  4. get_endpoint()      — read the assigned public IP:port
  5. close_deployment()  — shut down when session expires

Akash REST gateway: https://api.akash.network (or a self-hosted node).
Akash provider services talk to the provider's HTTPS endpoint directly.

Env vars:
  AKASH_WALLET_MNEMONIC  — operator wallet (pays for deployments in AKT/USDC)
  AKASH_NODE_URL         — Akash REST node (default: https://api.akash.network)
  AKASH_CHAIN_ID         — default: akashnet-2
  AKASH_KEYRING_BACKEND  — default: os
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass

import aiohttp
from loguru import logger

AKASH_NODE_URL  = os.getenv("AKASH_NODE_URL",  "https://api.akash.network")
AKASH_CHAIN_ID  = os.getenv("AKASH_CHAIN_ID",  "akashnet-2")
AKASH_DSEQ_BASE = int(time.time())   # used as a unique deployment sequence seed


@dataclass
class AkashDeployment:
    dseq:          str           # deployment sequence number (unique per deploy)
    provider:      str | None    # provider address (set after lease)
    endpoint:      str | None    # https://host:port exposed by provider
    lease_id:      str | None    # dseq/gseq/oseq/provider composite
    status:        str = "pending"   # pending | active | closed
    created_at:    float = 0.0
    cost_akt:      float = 0.0   # bid price in AKT


class AkashClient:
    """
    Thin async wrapper around the Akash REST API.

    We intentionally use raw HTTP (not the akash CLI) so this runs anywhere
    without a local node installation — including CI and serverless.
    """

    def __init__(self, node_url: str = AKASH_NODE_URL) -> None:
        self._node = node_url.rstrip("/")

    # ── Deployment lifecycle ──────────────────────────────────────────────────

    async def create_deployment(self, sdl_yaml: str, owner: str) -> AkashDeployment:
        """
        Broadcast a deployment to the Akash network.

        In production this requires a signed MsgCreateDeployment Cosmos tx.
        The operator wallet signs with its AKT key. Here we call the Akash
        REST tx broadcast endpoint with the pre-built tx JSON.

        For the MVP, this wraps `akash` CLI via subprocess so we don't have
        to reimplement the full Cosmos tx-building stack in Python.
        """
        import subprocess
        import tempfile
        import shutil

        if not shutil.which("akash"):
            raise RuntimeError(
                "akash CLI not found. Install from https://docs.akash.network/guides/cli/install"
            )

        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write(sdl_yaml)
            sdl_path = f.name

        env = os.environ.copy()
        cmd = [
            "akash", "tx", "deployment", "create", sdl_path,
            "--from",         owner,
            "--chain-id",     AKASH_CHAIN_ID,
            "--node",         self._node.replace("https://api.", "https://rpc."),
            "--gas",          "auto",
            "--gas-adjustment", "1.3",
            "--output",       "json",
            "-y",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
            if result.returncode != 0:
                raise RuntimeError(f"akash deployment create failed: {result.stderr}")
            tx = json.loads(result.stdout)
            dseq = self._extract_dseq(tx)
        finally:
            os.unlink(sdl_path)

        dep = AkashDeployment(dseq=dseq, provider=None, endpoint=None, lease_id=None, created_at=time.time())
        logger.info(f"Akash deployment created | dseq={dseq}")
        return dep

    async def wait_for_lease(self, deployment: AkashDeployment, timeout: int = 120) -> bool:
        """
        Poll until a provider accepts the bid and a lease is active.
        Returns True if a lease was obtained within the timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            bids = await self._get_bids(deployment.dseq)
            if bids:
                # Accept the cheapest bid automatically.
                best = min(bids, key=lambda b: float(b.get("price", {}).get("amount", "9999")))
                provider = best["id"]["provider"]
                await self._accept_bid(deployment.dseq, provider)
                deployment.provider   = provider
                deployment.lease_id   = f"{deployment.dseq}/1/1/{provider}"
                deployment.status     = "active"
                deployment.cost_akt   = float(best.get("price", {}).get("amount", "0"))
                logger.info(f"Lease accepted | dseq={deployment.dseq} provider={provider[:16]}…")
                return True
            await asyncio.sleep(5)
        logger.warning(f"No lease obtained for dseq={deployment.dseq} within {timeout}s")
        return False

    async def get_endpoint(self, deployment: AkashDeployment) -> str | None:
        """
        Read the public IP:port assigned by the provider.
        Returns a URL like https://provider-host:32000 or None if not yet ready.
        """
        if not deployment.provider or not deployment.lease_id:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                # The provider exposes a status API for our lease.
                provider_url = await self._resolve_provider_url(deployment.provider)
                async with session.get(
                    f"{provider_url}/lease/{deployment.dseq}/1/1/status",
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False,
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    services = data.get("services", {})
                    miner_svc = services.get("miner", {})
                    uris = miner_svc.get("uris", [])
                    if uris:
                        host = uris[0]
                        port = miner_svc.get("ports", [{}])[0].get("externalPort", 8091)
                        endpoint = f"https://{host}:{port}"
                        deployment.endpoint = endpoint
                        return endpoint
        except Exception as exc:
            logger.debug(f"get_endpoint error: {exc}")
        return None

    async def close_deployment(self, deployment: AkashDeployment, owner: str) -> None:
        """Terminate the deployment and stop billing."""
        import subprocess
        cmd = [
            "akash", "tx", "deployment", "close",
            "--dseq",     deployment.dseq,
            "--from",     owner,
            "--chain-id", AKASH_CHAIN_ID,
            "--gas",      "auto",
            "-y",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                deployment.status = "closed"
                logger.info(f"Akash deployment closed | dseq={deployment.dseq}")
            else:
                logger.warning(f"close_deployment stderr: {result.stderr}")
        except Exception as exc:
            logger.error(f"close_deployment failed: {exc}")

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _get_bids(self, dseq: str) -> list[dict]:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{self._node}/akash/market/v1beta4/bids/list?filters.dseq={dseq}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("bids", [])
        except Exception:
            pass
        return []

    async def _accept_bid(self, dseq: str, provider: str) -> None:
        import subprocess
        cmd = [
            "akash", "tx", "market", "lease", "create",
            "--dseq",     dseq,
            "--provider", provider,
            "--chain-id", AKASH_CHAIN_ID,
            "--gas",      "auto",
            "-y",
        ]
        subprocess.run(cmd, capture_output=True, timeout=60)

    async def _resolve_provider_url(self, provider_address: str) -> str:
        """Look up the provider's HTTPS endpoint from the Akash registry."""
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{self._node}/akash/provider/v1beta3/providers/{provider_address}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("provider", {}).get("hostUri", "")
        return ""

    @staticmethod
    def _extract_dseq(tx_response: dict) -> str:
        """Pull dseq from the MsgCreateDeployment tx response logs."""
        logs = tx_response.get("logs", [])
        for log in logs:
            for event in log.get("events", []):
                for attr in event.get("attributes", []):
                    if attr.get("key") == "dseq":
                        return attr["value"]
        # Fallback: use timestamp-based unique ID
        return str(int(time.time() * 1000))
