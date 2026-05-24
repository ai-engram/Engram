"""
Shamir's Secret Sharing over GF(256).

Splits a byte string into N shares such that any K shares reconstruct
the original, but K-1 shares reveal nothing (information-theoretic security).

Each byte of the secret is independently shared using a random polynomial
of degree K-1 over GF(2^8) with AES irreducible polynomial 0x11b.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass


# ── GF(256) arithmetic ────────────────────────────────────────────────────────

def _gf_mul(a: int, b: int) -> int:
    result = 0
    while b:
        if b & 1:
            result ^= a
        b >>= 1
        a <<= 1
        if a & 0x100:
            a ^= 0x11b
    return result & 0xFF


def _gf_pow(base: int, exp: int) -> int:
    result = 1
    base &= 0xFF
    while exp > 0:
        if exp & 1:
            result = _gf_mul(result, base)
        base = _gf_mul(base, base)
        exp >>= 1
    return result


def _gf_inv(a: int) -> int:
    if a == 0:
        raise ValueError("No inverse for 0 in GF(256)")
    return _gf_pow(a, 254)


def _poly_eval(coeffs: list[int], x: int) -> int:
    """Evaluate polynomial at x via Horner's method in GF(256)."""
    result = 0
    for c in reversed(coeffs):
        result = _gf_mul(result, x) ^ c
    return result


def _lagrange_at_zero(xs: list[int], ys: list[int]) -> int:
    """Reconstruct f(0) from k (x, y) pairs using Lagrange interpolation in GF(256)."""
    result = 0
    k = len(xs)
    for i in range(k):
        numer = 1
        denom = 1
        for j in range(k):
            if i == j:
                continue
            numer = _gf_mul(numer, xs[j])
            denom = _gf_mul(denom, xs[i] ^ xs[j])
        result ^= _gf_mul(ys[i], _gf_mul(numer, _gf_inv(denom)))
    return result


# ── Public API ────────────────────────────────────────────────────────────────

@dataclass
class KeyShare:
    """A single share of a split secret."""
    index: int       # 1-based
    data: bytes      # len == len(secret)
    threshold: int   # k — minimum shares to reconstruct
    total: int       # n — total shares created

    def to_hex(self) -> str:
        return self.data.hex()

    @classmethod
    def from_hex(cls, index: int, hex_str: str, threshold: int, total: int) -> "KeyShare":
        return cls(index=index, data=bytes.fromhex(hex_str), threshold=threshold, total=total)


def split_secret(secret: bytes, threshold: int, total: int) -> list[KeyShare]:
    """
    Split a secret into `total` shares requiring `threshold` to reconstruct.

    Args:
        secret:    Bytes to split (e.g. a 32-byte AES key or X25519 private key).
        threshold: Minimum shares needed to reconstruct (k >= 2).
        total:     Total shares to create (n, max 255).

    Returns:
        List of `total` KeyShare objects indexed 1..n.
    """
    if not secret:
        raise ValueError("secret must be non-empty")
    if threshold < 2:
        raise ValueError("threshold must be >= 2")
    if threshold > total:
        raise ValueError("threshold cannot exceed total")
    if total > 255:
        raise ValueError("total shares cannot exceed 255")

    share_data: list[list[int]] = [[] for _ in range(total)]
    for byte_val in secret:
        coeffs = [byte_val] + [secrets.randbelow(256) for _ in range(threshold - 1)]
        for i in range(total):
            share_data[i].append(_poly_eval(coeffs, i + 1))

    return [
        KeyShare(index=i + 1, data=bytes(share_data[i]), threshold=threshold, total=total)
        for i in range(total)
    ]


def reconstruct_secret(shares: list[KeyShare]) -> bytes:
    """
    Reconstruct the secret from at least `threshold` shares.

    Args:
        shares: KeyShare list — must have at least threshold entries.

    Returns:
        Original secret bytes.

    Raises:
        ValueError: insufficient shares, mismatched lengths, or duplicate indices.
    """
    if not shares:
        raise ValueError("No shares provided")
    threshold = shares[0].threshold
    if len(shares) < threshold:
        raise ValueError(f"Need {threshold} shares; got {len(shares)}")
    secret_len = len(shares[0].data)
    if any(len(s.data) != secret_len for s in shares):
        raise ValueError("All shares must have the same byte length")
    indices = [s.index for s in shares]
    if len(set(indices)) != len(indices):
        raise ValueError("Duplicate share indices")

    xs = [s.index for s in shares[:threshold]]
    return bytes(
        _lagrange_at_zero(xs, [s.data[i] for s in shares[:threshold]])
        for i in range(secret_len)
    )
