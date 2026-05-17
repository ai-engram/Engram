"""
x402 Payment Protocol — Dexter Cash integration.

x402 is a standard for monetising HTTP endpoints:
  1. Client requests a resource (no payment).
  2. Server returns HTTP 402 with a `WWW-Authenticate: x402 …` header
     describing the required payment (network, token, amount, recipient).
  3. Client signs and broadcasts the on-chain payment, gets a receipt.
  4. Client resends the original request with `X-Payment: <receipt>` header.
  5. Server verifies the receipt via the Dexter facilitator and grants access.

References:
  https://docs.dexter.cash/docs/
  https://github.com/coinbase/x402
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Any

import aiohttp
from loguru import logger


# ── Config ────────────────────────────────────────────────────────────────────

# Address on the supported network that receives compute payments.
PAYMENT_RECIPIENT = os.getenv("X402_RECIPIENT_ADDRESS", "")

# Dexter facilitator endpoint — verifies on-chain payment proofs.
FACILITATOR_URL = os.getenv(
    "X402_FACILITATOR_URL",
    "https://facilitator.dexter.cash",
)

# Default payment network (Base is cheapest for USDC micropayments).
DEFAULT_NETWORK = os.getenv("X402_NETWORK", "base")

# Compute pricing: USD per hour of mining.
PRICE_PER_HOUR_USD = float(os.getenv("CLOUD_PRICE_PER_HOUR_USD", "0.10"))


# ── Payment requirement builder ───────────────────────────────────────────────

def payment_required_headers(
    amount_usd: float,
    resource: str = "/sessions",
    network: str = DEFAULT_NETWORK,
) -> dict[str, str]:
    """
    Return the headers for an HTTP 402 Payment Required response.

    The client reads these, builds an on-chain payment, and resends the
    request with an X-Payment header containing the signed receipt.
    """
    # x402 standard: amount in smallest token unit (USDC = 6 decimals)
    amount_micro = int(amount_usd * 1_000_000)

    payload = {
        "scheme":    "exact",
        "network":   network,
        "amount":    str(amount_micro),
        "token":     "USDC",
        "recipient": PAYMENT_RECIPIENT,
        "resource":  resource,
        "version":   "1",
    }

    # x402 WWW-Authenticate value — space-separated key=value pairs
    auth_value = "x402 " + " ".join(f'{k}="{v}"' for k, v in payload.items())

    return {
        "WWW-Authenticate": auth_value,
        "X-Payment-Network": network,
        "X-Payment-Amount-USD": str(amount_usd),
    }


def price_for_hours(hours: float) -> float:
    """Compute the USD price for a given number of mining hours."""
    return round(hours * PRICE_PER_HOUR_USD, 6)


# ── Payment verification ──────────────────────────────────────────────────────

class PaymentVerificationError(Exception):
    pass


async def verify_payment(
    x_payment_header: str,
    expected_amount_usd: float,
    network: str = DEFAULT_NETWORK,
) -> dict[str, Any]:
    """
    Verify an x402 payment proof via the Dexter facilitator.

    Returns the decoded receipt on success.
    Raises PaymentVerificationError on failure.
    """
    if not x_payment_header:
        raise PaymentVerificationError("Missing X-Payment header.")

    if not PAYMENT_RECIPIENT:
        # Dev mode — skip on-chain verification, accept any non-empty proof.
        logger.warning("X402_RECIPIENT_ADDRESS not set — running in dev mode, skipping payment verification.")
        return _dev_mode_receipt(x_payment_header, expected_amount_usd, network)

    # Decode the payment proof (base64-encoded JSON receipt from the client).
    try:
        receipt_bytes = base64.b64decode(x_payment_header)
        receipt = json.loads(receipt_bytes)
    except Exception as exc:
        raise PaymentVerificationError(f"Invalid X-Payment encoding: {exc}")

    # Verify via the Dexter facilitator.
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{FACILITATOR_URL}/verify",
                json={
                    "receipt":             receipt,
                    "expected_recipient":  PAYMENT_RECIPIENT,
                    "expected_amount_usd": expected_amount_usd,
                    "network":             network,
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise PaymentVerificationError(f"Facilitator rejected payment: {body}")
                result = await resp.json()
        except aiohttp.ClientError as exc:
            raise PaymentVerificationError(f"Facilitator unreachable: {exc}")

    if not result.get("valid"):
        raise PaymentVerificationError(result.get("reason", "Payment invalid."))

    logger.info(
        f"Payment verified | tx={receipt.get('txHash', 'unknown')[:16]}… "
        f"amount=${expected_amount_usd:.4f} network={network}"
    )
    return receipt


def _dev_mode_receipt(header: str, amount_usd: float, network: str) -> dict:
    """Synthetic receipt for local development (no real payment required)."""
    return {
        "txHash":    hashlib.sha256(header.encode()).hexdigest(),
        "amount":    str(int(amount_usd * 1_000_000)),
        "network":   network,
        "timestamp": int(time.time()),
        "devMode":   True,
    }


# ── aiohttp middleware helper ─────────────────────────────────────────────────

def make_payment_gate(amount_usd: float, network: str = DEFAULT_NETWORK):
    """
    Decorator / helper for aiohttp handlers that require x402 payment.

    Usage:
        gate = make_payment_gate(0.10)
        receipt = await gate(request)   # raises 402 response if not paid
    """
    async def check(request: "aiohttp.web.Request") -> dict:
        from aiohttp import web

        x_payment = request.headers.get("X-Payment", "")
        if not x_payment:
            raise web.HTTPPaymentRequired(
                headers=payment_required_headers(amount_usd, str(request.rel_url), network),
                text=json.dumps({
                    "error":      "Payment required",
                    "amount_usd": amount_usd,
                    "network":    network,
                    "recipient":  PAYMENT_RECIPIENT,
                    "protocol":   "x402",
                    "docs":       "https://docs.dexter.cash/docs/",
                }),
                content_type="application/json",
            )

        try:
            return await verify_payment(x_payment, amount_usd, network)
        except PaymentVerificationError as exc:
            raise web.HTTPPaymentRequired(
                headers=payment_required_headers(amount_usd, str(request.rel_url), network),
                text=json.dumps({"error": str(exc)}),
                content_type="application/json",
            )

    return check
