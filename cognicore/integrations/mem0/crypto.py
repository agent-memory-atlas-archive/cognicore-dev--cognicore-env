"""Ed25519 signing and deterministic canonical JSON for transfer bundles.

Uses the ``cryptography`` library for Ed25519 key operations.
Deterministic canonical JSON is implemented via ``json.dumps`` with
deterministic key sorting and compact separators.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Dict, Tuple

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    Ed25519PrivateKey = None  # type: ignore[assignment,misc]
    Ed25519PublicKey = None  # type: ignore[assignment,misc]
    InvalidSignature = Exception  # type: ignore[assignment,misc]


def _require_crypto() -> None:
    """Raise ImportError when the cryptography package is missing."""
    if not CRYPTO_AVAILABLE:
        raise ImportError(
            "The 'cryptography' package is required for bundle signing. "
            "Install it with: pip install cryptography"
        )


# ------------------------------------------------------------------
# Deterministic Canonical JSON
# ------------------------------------------------------------------


def canonicalize(obj: Any) -> bytes:
    """Deterministic canonical JSON serialization.

    Serializes *obj* with sorted keys and compact separators (',', ':'),
    encoded as UTF-8 bytes suitable for deterministic Ed25519 signing.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


# ------------------------------------------------------------------
# Ed25519 signing / verification
# ------------------------------------------------------------------


def sign_bundle(bundle_dict: Dict[str, Any], private_key: Ed25519PrivateKey) -> str:
    """Sign the deterministic canonical JSON of *bundle_dict*.

    Returns a base64-encoded Ed25519 signature.
    """
    _require_crypto()
    canonical_bytes = canonicalize(bundle_dict)
    signature = private_key.sign(canonical_bytes)
    return base64.b64encode(signature).decode("ascii")


def verify_signature(
    bundle_dict: Dict[str, Any],
    signature_b64: str,
    public_key: Ed25519PublicKey,
) -> bool:
    """Verify an Ed25519 signature over deterministic canonical JSON bytes.

    Returns ``True`` if valid, ``False`` on failure.
    """
    _require_crypto()
    canonical_bytes = canonicalize(bundle_dict)
    signature = base64.b64decode(signature_b64)
    try:
        public_key.verify(signature, canonical_bytes)
        return True
    except InvalidSignature:
        return False


# ------------------------------------------------------------------
# Key utilities
# ------------------------------------------------------------------


def key_fingerprint(public_key: Ed25519PublicKey) -> str:
    """Compute SHA-256 fingerprint of a public key (hex string)."""
    _require_crypto()
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()


def generate_keypair() -> Tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Generate an Ed25519 keypair.  Intended for **testing only**."""
    _require_crypto()
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key
