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


class FloatInSignedSchemaError(TypeError):
    """Raised when a ``float`` value is encountered in the signed schema.

    Floats are forbidden because their byte-level representation differs
    across language runtimes (Python's ``repr`` produces ``"1.0"`` while
    ECMAScript's ``JSON.stringify`` produces ``"1"`` for integral floats),
    which would silently break the "same bytes, same hash, same signature"
    contract that the transfer bundle format depends on.

    Callers must quantize to ``int`` (when the value is integral) or move
    the value into an unsigned metadata envelope outside the signed body.

    Design choice: rejection (this class) over normalization, because
    normalization would require a canonical float representation that no
    existing JSON canonicalization spec (RFC 8785 JCS, OLPC Canonical JSON)
    agrees on across runtimes — and silent normalization is exactly the
    failure mode that defeated the reachability firing vector in PR #136.

    Refs: cognicore-dev/cognicore-env#135 (item 3, option 2).
    """


def _reject_floats(obj: Any, path: str = "$") -> None:
    """Walk *obj* and raise on the first ``float`` encountered.

    Boolean is a subclass of ``int`` in Python, but not of ``float``, so
    booleans pass through cleanly. Integers and strings are fine.

    The path argument is used only for the error message; it tracks a
    JSONPath-style location so callers can identify *which* field needs
    to be quantized.
    """
    if isinstance(obj, bool):
        return
    if isinstance(obj, float):
        raise FloatInSignedSchemaError(
            f"float value at {path} is not allowed in the signed schema; "
            f"quantize to int (if integral) or move to unsigned metadata. "
            f"Reason: cross-language byte-level representation of floats "
            f"breaks the deterministic Ed25519 signature contract. "
            f"See FloatInSignedSchemaError.__doc__ for the design rationale."
        )
    if isinstance(obj, dict):
        for k, v in obj.items():
            _reject_floats(v, f"{path}.{k}")
        return
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _reject_floats(v, f"{path}[{i}]")
        return

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

    Raises ``FloatInSignedSchemaError`` if any ``float`` value is present
    at any depth in *obj*. See that class's docstring for the rationale
    and the cross-language rejection contract.

    Refs: cognicore-dev/cognicore-env#135 (item 3, option 2).
    """
    _reject_floats(obj)
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
