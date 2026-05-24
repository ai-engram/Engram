"""Tests for Shamir Secret Sharing (engram/sdk/shamir.py)."""

import pytest
from engram.sdk.shamir import KeyShare, split_secret, reconstruct_secret


SECRET_32 = bytes(range(32))  # 32-byte test secret


# ── Basic correctness ─────────────────────────────────────────────────────────

def test_split_and_reconstruct_all_shares():
    shares = split_secret(SECRET_32, threshold=2, total=3)
    assert len(shares) == 3
    reconstructed = reconstruct_secret(shares)
    assert reconstructed == SECRET_32


def test_reconstruct_with_exactly_threshold_shares():
    shares = split_secret(SECRET_32, threshold=2, total=5)
    result = reconstruct_secret(shares[:2])
    assert result == SECRET_32


def test_reconstruct_with_different_share_subsets():
    shares = split_secret(SECRET_32, threshold=3, total=5)
    assert reconstruct_secret(shares[:3]) == SECRET_32
    assert reconstruct_secret(shares[1:4]) == SECRET_32
    assert reconstruct_secret(shares[2:5]) == SECRET_32


def test_shares_have_correct_metadata():
    shares = split_secret(SECRET_32, threshold=2, total=3)
    for i, share in enumerate(shares, start=1):
        assert share.index == i
        assert share.threshold == 2
        assert share.total == 3
        assert len(share.data) == len(SECRET_32)


# ── Insufficient shares ───────────────────────────────────────────────────────

def test_insufficient_shares_raises():
    shares = split_secret(SECRET_32, threshold=3, total=5)
    with pytest.raises(ValueError, match="Need 3 shares"):
        reconstruct_secret(shares[:2])


def test_single_share_raises():
    shares = split_secret(SECRET_32, threshold=2, total=3)
    with pytest.raises(ValueError, match="Need 2 shares"):
        reconstruct_secret(shares[:1])


def test_empty_shares_raises():
    with pytest.raises(ValueError, match="No shares provided"):
        reconstruct_secret([])


# ── Wrong share (tampered data) ───────────────────────────────────────────────

def test_tampered_share_produces_wrong_secret():
    shares = split_secret(SECRET_32, threshold=2, total=3)
    # Flip a byte in one share — reconstruction should NOT raise but will return garbage
    bad_data = bytearray(shares[0].data)
    bad_data[0] ^= 0xFF
    tampered = KeyShare(
        index=shares[0].index,
        data=bytes(bad_data),
        threshold=shares[0].threshold,
        total=shares[0].total,
    )
    result = reconstruct_secret([tampered, shares[1]])
    assert result != SECRET_32


def test_wrong_index_produces_wrong_secret():
    shares = split_secret(SECRET_32, threshold=2, total=3)
    # Give share[0] the wrong index
    wrong_index = KeyShare(
        index=99,
        data=shares[0].data,
        threshold=shares[0].threshold,
        total=shares[0].total,
    )
    result = reconstruct_secret([wrong_index, shares[1]])
    assert result != SECRET_32


# ── Duplicate index detection ─────────────────────────────────────────────────

def test_duplicate_indices_raises():
    shares = split_secret(SECRET_32, threshold=2, total=3)
    duplicate = KeyShare(index=shares[0].index, data=shares[0].data,
                         threshold=2, total=3)
    with pytest.raises(ValueError, match="Duplicate share indices"):
        reconstruct_secret([shares[0], duplicate])


# ── Backward compatibility (no threshold — password-based encryption) ─────────

def test_namespace_encryption_still_works_without_shares():
    """NamespaceEncryption (password-based) must be unaffected by Shamir additions."""
    from engram.sdk.encryption import NamespaceEncryption
    enc = NamespaceEncryption("my-namespace", "secret-passphrase")
    blob = enc.encrypt_payload("hello world", {"key": "value"})
    text, meta = enc.decrypt_payload(blob)
    assert text == "hello world"
    assert meta == {"key": "value"}


def test_hybrid_encryption_still_works_without_shares():
    """HybridEncryption must be unaffected by Shamir additions."""
    from engram.sdk.encryption import HybridEncryption, generate_keypair
    priv, pub = generate_keypair()
    enc = HybridEncryption(private_key=priv)
    blob = enc.encrypt_payload("top secret", {"tag": "test"})
    text, meta = enc.decrypt_payload(blob)
    assert text == "top secret"
    assert meta == {"tag": "test"}


# ── Hex serialization ─────────────────────────────────────────────────────────

def test_hex_round_trip():
    shares = split_secret(SECRET_32, threshold=2, total=3)
    hexed = [s.to_hex() for s in shares]
    restored = [
        KeyShare.from_hex(shares[i].index, hexed[i], shares[i].threshold, shares[i].total)
        for i in range(3)
    ]
    assert reconstruct_secret(restored) == SECRET_32


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_single_byte_secret():
    secret = b"\xAB"
    shares = split_secret(secret, threshold=2, total=3)
    assert reconstruct_secret(shares[:2]) == secret


def test_max_threshold_equals_total():
    shares = split_secret(SECRET_32, threshold=5, total=5)
    assert reconstruct_secret(shares) == SECRET_32
    with pytest.raises(ValueError, match="Need 5 shares"):
        reconstruct_secret(shares[:4])


def test_invalid_params():
    with pytest.raises(ValueError, match="threshold must be >= 2"):
        split_secret(SECRET_32, threshold=1, total=3)
    with pytest.raises(ValueError, match="threshold cannot exceed total"):
        split_secret(SECRET_32, threshold=4, total=3)
    with pytest.raises(ValueError, match="secret must be non-empty"):
        split_secret(b"", threshold=2, total=3)
