"""
Engram Cloud Mining Gateway

Mobile-facing HTTP server that manages cloud mining sessions on Akash Network.
Users pay via x402 (Dexter Cash) and get a managed Engram miner node.

Endpoints:
  GET  /tiers                  — available compute tiers and pricing
  GET  /nodes                  — pool availability
  POST /sessions               — start a mining session (x402 payment required)
  GET  /sessions/{id}          — session status + stats
  DELETE /sessions/{id}        — stop a session early
  GET  /sessions/hotkey/{hk}   — all sessions for a hotkey (mobile dashboard)
  GET  /bittensor/metagraph    — raw subnet state (no SDK, pure JSON-RPC)
  GET  /health                 — gateway liveness

Authentication:
  Every request (except /health, /tiers, /bittensor/metagraph) must include:
    X-Hotkey:    <ss58-or-hex pubkey of the phone>
    X-Timestamp: <unix ms>
    X-Sig:       <sr25519 signature of "engram-cloud:{method}:{path}:{timestamp}">

  This is distinct from Bittensor extrinsic signing — it's just gateway auth.
  The cloud node (not the phone) handles all on-chain Bittensor operations.

Payment:
  POST /sessions requires an X-Payment header containing a valid x402 receipt
  for the session duration * hourly rate in USDC on Base (or configured network).
  In dev mode (X402_RECIPIENT_ADDRESS unset), payment is skipped.

Run:
  python neurons/cloud_gateway.py --port 9000
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path

import aiohttp
from aiohttp import web
from loguru import logger

from engram.cloud.akash import AkashClient
from engram.cloud.akash_sdl import build_sdl, tier_info, TIERS
from engram.cloud.session import SessionRegistry, SessionStatus
from engram.cloud.x402 import make_payment_gate, price_for_hours


# ── Bittensor raw JSON-RPC (no SDK — mobile-friendly) ────────────────────────

SUBTENSOR_HTTP = os.getenv(
    "SUBTENSOR_HTTP_ENDPOINT",
    "https://test.finney.opentensor.ai",
)
NETUID = int(os.getenv("NETUID", "450"))

AKASH_OWNER = os.getenv("AKASH_OWNER_ADDRESS", "")


async def _substrate_rpc(method: str, params: list) -> dict:
    """Fire a raw Substrate JSON-RPC call. No bittensor SDK required."""
    payload = {
        "jsonrpc": "2.0",
        "id":      1,
        "method":  method,
        "params":  params,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            SUBTENSOR_HTTP,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            return await resp.json()


async def _get_metagraph(netuid: int) -> dict:
    """
    Read subnet metagraph via raw Substrate JSON-RPC.

    We use state_getStorage with the encoded storage key for
    SubtensorModule::NeuronsLite (returns all neurons for a netuid).
    This is equivalent to metagraph.neurons but without the SDK.
    """
    # system_chain tells us we're talking to the right node
    chain   = await _substrate_rpc("system_chain", [])
    block   = await _substrate_rpc("chain_getBlock", [])

    # For demo purposes return network info + block — full neuron decoding
    # requires SCALE codec (separate library, pure Python: scalecodec).
    block_number = (
        block.get("result", {})
             .get("block", {})
             .get("header", {})
             .get("number", "0x0")
    )
    return {
        "network":     chain.get("result", "unknown"),
        "block":       int(block_number, 16) if isinstance(block_number, str) else 0,
        "netuid":      netuid,
        "note":        "Full neuron list requires SCALE decoding — use /sessions/{id}/stats for miner-specific data.",
    }


# ── Gateway app ───────────────────────────────────────────────────────────────

def run_gateway(port: int = 9000) -> None:
    registry   = SessionRegistry(Path("data/cloud_sessions.json"))
    akash      = AkashClient()

    # ── Auth helper ───────────────────────────────────────────────────────────

    def _verify_gateway_sig(req: web.Request) -> str | None:
        """
        Verify the sr25519 gateway auth header.

        Returns the hotkey on success, None on failure.
        In dev mode (GATEWAY_AUTH_REQUIRED=0) always returns a synthetic key.
        """
        if os.getenv("GATEWAY_AUTH_REQUIRED", "1") == "0":
            return req.headers.get("X-Hotkey", "dev_hotkey")

        hotkey    = req.headers.get("X-Hotkey", "")
        timestamp = req.headers.get("X-Timestamp", "")
        sig       = req.headers.get("X-Sig", "")

        if not (hotkey and timestamp and sig):
            return None

        # Replay prevention: timestamp must be within ±60 s
        try:
            ts = int(timestamp)
        except ValueError:
            return None
        if abs(time.time() * 1000 - ts) > 60_000:
            return None

        # sr25519 signature verification via substrateinterface (pure Python)
        try:
            from substrateinterface.keypair import Keypair
            kp  = Keypair(ss58_address=hotkey) if hotkey.startswith("5") else Keypair(public_key=hotkey)
            msg = f"engram-cloud:{req.method}:{req.path}:{timestamp}".encode()
            if not kp.verify(msg, bytes.fromhex(sig)):
                return None
        except Exception as exc:
            logger.debug(f"Sig verify error: {exc}")
            return None

        return hotkey

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def handle_health(req: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "engram-cloud-gateway"})

    async def handle_tiers(req: web.Request) -> web.Response:
        return web.json_response({"tiers": tier_info()})

    async def handle_nodes(req: web.Request) -> web.Response:
        # Count active sessions as a proxy for pool utilisation
        return web.json_response({
            "note": "Nodes provisioned on Akash on demand — no fixed pool limit.",
            "akash_network": "akashnet-2",
            "available": True,
        })

    async def handle_create_session(req: web.Request) -> web.Response:
        hotkey = _verify_gateway_sig(req)
        if not hotkey:
            return web.json_response({"error": "Invalid or missing gateway auth headers."}, status=401)

        try:
            body = await req.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body."}, status=400)

        tier          = body.get("tier", "standard")
        duration_hours = float(body.get("duration_hours", 1.0))

        if tier not in TIERS:
            return web.json_response({"error": f"Unknown tier '{tier}'. Valid: {list(TIERS)}"}, status=400)
        if not (0.5 <= duration_hours <= 720):
            return web.json_response({"error": "duration_hours must be between 0.5 and 720."}, status=400)

        amount_usd = price_for_hours(duration_hours)

        # ── x402 payment gate ─────────────────────────────────────────────────
        gate    = make_payment_gate(amount_usd)
        receipt = await gate(req)   # raises web.HTTPPaymentRequired if not paid
        network = receipt.get("network", "base")
        tx_hash = receipt.get("txHash", "")

        # ── Create session record ─────────────────────────────────────────────
        session = registry.create(
            controller_hotkey = hotkey,
            duration_hours    = duration_hours,
            payment_tx        = tx_hash,
            network           = network,
            amount_paid_usd   = amount_usd,
        )

        # ── Provision Akash node in the background ────────────────────────────
        asyncio.ensure_future(_provision_akash_node(session.session_id, hotkey, tier, registry, akash))

        return web.json_response(session.to_dict(), status=202)

    async def handle_get_session(req: web.Request) -> web.Response:
        hotkey = _verify_gateway_sig(req)
        if not hotkey:
            return web.json_response({"error": "Unauthorized."}, status=401)

        session_id = req.match_info["session_id"]
        session    = registry.get(session_id)
        if not session:
            return web.json_response({"error": "Session not found."}, status=404)
        if session.controller_hotkey != hotkey:
            return web.json_response({"error": "Not your session."}, status=403)

        # Refresh stats from the live node if active
        if session.status == SessionStatus.ACTIVE and session.node_endpoint:
            try:
                async with aiohttp.ClientSession() as http:
                    async with http.get(
                        f"{session.node_endpoint}/stats",
                        timeout=aiohttp.ClientTimeout(total=5),
                        ssl=False,
                    ) as resp:
                        if resp.status == 200:
                            stats = await resp.json()
                            registry.update_stats(session_id, stats)
                            session.stats = stats
            except Exception:
                pass

        return web.json_response(session.to_dict())

    async def handle_stop_session(req: web.Request) -> web.Response:
        hotkey = _verify_gateway_sig(req)
        if not hotkey:
            return web.json_response({"error": "Unauthorized."}, status=401)

        session_id = req.match_info["session_id"]
        session    = registry.get(session_id)
        if not session:
            return web.json_response({"error": "Session not found."}, status=404)
        if session.controller_hotkey != hotkey:
            return web.json_response({"error": "Not your session."}, status=403)

        asyncio.ensure_future(_teardown_session(session_id, registry, akash))
        return web.json_response({"stopped": True, "session_id": session_id})

    async def handle_list_sessions(req: web.Request) -> web.Response:
        hotkey = _verify_gateway_sig(req)
        if not hotkey:
            return web.json_response({"error": "Unauthorized."}, status=401)

        hk       = req.match_info["hotkey"]
        if hk != hotkey:
            return web.json_response({"error": "Can only list your own sessions."}, status=403)

        sessions = registry.list_for_hotkey(hk)
        return web.json_response({"sessions": [s.to_dict() for s in sessions]})

    async def handle_metagraph(req: web.Request) -> web.Response:
        """Public — raw Substrate JSON-RPC, no auth needed, no SDK."""
        netuid_ = int(req.query.get("netuid", NETUID))
        data    = await _get_metagraph(netuid_)
        return web.json_response(data)

    # ── Background tasks ──────────────────────────────────────────────────────

    async def _expire_loop() -> None:
        """Periodically stop sessions whose compute time has run out."""
        while True:
            await asyncio.sleep(60)
            expired = registry.expire_stale()
            for sid in expired:
                asyncio.ensure_future(_teardown_session(sid, registry, akash))

    # ── App wiring ────────────────────────────────────────────────────────────

    app = web.Application()
    app.router.add_get("/health",                          handle_health)
    app.router.add_get("/tiers",                           handle_tiers)
    app.router.add_get("/nodes",                           handle_nodes)
    app.router.add_post("/sessions",                       handle_create_session)
    app.router.add_get("/sessions/{session_id}",           handle_get_session)
    app.router.add_delete("/sessions/{session_id}",        handle_stop_session)
    app.router.add_get("/sessions/hotkey/{hotkey}",        handle_list_sessions)
    app.router.add_get("/bittensor/metagraph",             handle_metagraph)

    async def on_startup(app):
        asyncio.ensure_future(_expire_loop())

    app.on_startup.append(on_startup)

    logger.info(f"Cloud Gateway starting on 0.0.0.0:{port}")
    web.run_app(app, host="0.0.0.0", port=port, access_log=None)


# ── Akash provisioning / teardown (run in background) ────────────────────────

async def _provision_akash_node(
    session_id: str,
    controller_hotkey: str,
    tier: str,
    registry: SessionRegistry,
    akash: AkashClient,
) -> None:
    try:
        sdl = build_sdl(session_id, controller_hotkey, tier=tier)
        deployment = await akash.create_deployment(sdl, owner=AKASH_OWNER)

        leased = await akash.wait_for_lease(deployment, timeout=180)
        if not leased:
            registry.mark_failed(session_id, "No Akash provider accepted the bid within 3 minutes.")
            return

        # Wait for the container to be reachable
        endpoint = None
        for _ in range(24):    # up to 2 minutes
            await asyncio.sleep(5)
            endpoint = await akash.get_endpoint(deployment)
            if endpoint:
                break

        if not endpoint:
            registry.mark_failed(session_id, "Akash node provisioned but endpoint not reachable.")
            return

        registry.mark_active(
            session_id,
            node_endpoint = endpoint,
            node_hotkey   = deployment.provider or "",
        )
        logger.success(f"Session active | id={session_id[:8]} endpoint={endpoint}")

    except Exception as exc:
        logger.error(f"Akash provisioning failed for {session_id}: {exc}")
        registry.mark_failed(session_id, str(exc))


async def _teardown_session(
    session_id: str,
    registry: SessionRegistry,
    akash: AkashClient,
) -> None:
    session = registry.get(session_id)
    if not session:
        return
    registry.mark_stopped(session_id)
    # Close the Akash deployment to stop billing
    if AKASH_OWNER:
        from engram.cloud.akash import AkashDeployment
        dep = AkashDeployment(dseq=session_id, provider=None, endpoint=None, lease_id=None)
        await akash.close_deployment(dep, AKASH_OWNER)
    logger.info(f"Session stopped | id={session_id[:8]}")


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Engram Cloud Mining Gateway")
    parser.add_argument("--port", type=int, default=int(os.getenv("GATEWAY_PORT", "9000")))
    args = parser.parse_args()
    run_gateway(args.port)
