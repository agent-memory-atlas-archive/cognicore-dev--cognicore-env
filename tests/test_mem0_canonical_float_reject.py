"""Tests for the float-rejection rule in the signed canonical schema.

Implements the cross-language rejection contract agreed in #135 item 3
(option 2 — exclusion, not normalization).

The same fixture files under ``tests/fixtures/canonical_float_reject/``
are consumed by the Rust and TypeScript SDKs to assert symmetric
rejection. Python side: this file.

Refs: cognicore-dev/cognicore-env#135
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cognicore.integrations.mem0.crypto import (
    FloatInSignedSchemaError,
    canonicalize,
    generate_keypair,
    sign_bundle,
    verify_signature,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "canonical_float_reject"


# ------------------------------------------------------------------
# Pure-rejection tests (no signing, no Ed25519)
# ------------------------------------------------------------------


class TestCanonicalizeRejectsFloat:
    """The core rejection rule. Every float, anywhere, must raise."""

    def test_top_level_float_rejected(self):
        with pytest.raises(FloatInSignedSchemaError) as exc:
            canonicalize({"confidence": 0.85})
        assert "confidence" in str(exc.value)
        assert "$.confidence" in str(exc.value)

    def test_integral_float_rejected(self):
        """The bug that motivated the rule: 1.0 in Python vs 1 in JS."""
        with pytest.raises(FloatInSignedSchemaError):
            canonicalize({"score": 1.0})

    def test_nested_float_in_dict_rejected(self):
        with pytest.raises(FloatInSignedSchemaError) as exc:
            canonicalize({
                "outer": {
                    "inner": {
                        "deep": 3.14,
                    },
                },
            })
        assert "$.outer.inner.deep" in str(exc.value)

    def test_float_in_list_rejected(self):
        with pytest.raises(FloatInSignedSchemaError) as exc:
            canonicalize({"scores": [1, 2, 3.5, 4]})
        assert "$.scores[2]" in str(exc.value)

    def test_float_in_tuple_rejected(self):
        with pytest.raises(FloatInSignedSchemaError):
            canonicalize({"coords": (1.0, 2.0)})

    def test_negative_float_rejected(self):
        with pytest.raises(FloatInSignedSchemaError):
            canonicalize({"delta": -0.5})

    def test_zero_float_rejected(self):
        """``0.0`` is a float, not an int. Must still be rejected."""
        with pytest.raises(FloatInSignedSchemaError):
            canonicalize({"weight": 0.0})

    def test_nan_and_inf_rejected(self):
        for v in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises(FloatInSignedSchemaError):
                canonicalize({"v": v})

    def test_no_floats_passes_clean(self):
        """Sanity: a clean int/str/bool/None dict canonicalizes normally."""
        out = canonicalize({
            "a": 1,
            "b": "string",
            "c": True,
            "d": None,
            "e": [1, 2, 3],
            "f": {"g": 0},
        })
        assert isinstance(out, bytes)
        # Sorted-key canonical form: a,b,c,d,e,f order
        assert out == (
            b'{"a":1,"b":"string","c":true,"d":null,"e":[1,2,3],"f":{"g":0}}'
        )

    def test_bool_is_not_mistaken_for_float(self):
        """bool subclasses int (not float) and must pass through cleanly."""
        # Should not raise
        canonicalize({"flag": True, "other": False})

    def test_int_is_not_rejected(self):
        """Large ints are fine on the Python side. (Cross-language int
        range is a separate concern tracked in alethech issue #X.)"""
        canonicalize({"big": 2**53 + 1})

    def test_error_is_typeerror_subclass(self):
        """``FloatInSignedSchemaError`` must subclass TypeError so callers
        that already catch TypeError for JSON serialization issues keep
        working without code changes."""
        with pytest.raises(TypeError):
            canonicalize({"x": 1.5})


# ------------------------------------------------------------------
# Integration: rejection flows through sign_bundle
# ------------------------------------------------------------------


class TestSignBundleRejectsFloat:
    """sign_bundle calls canonicalize, so it must propagate the rejection."""

    def test_sign_bundle_rejects_float_payload(self):
        priv, _ = generate_keypair()
        with pytest.raises(FloatInSignedSchemaError):
            sign_bundle({"confidence": 0.9}, priv)

    def test_verify_signature_does_not_silently_pass_on_float_payload(self):
        """If a caller bypasses canonicalize and hand-crafts a signature
        over a float-bearing payload, verification must still reject.

        We simulate this by attempting canonicalize on the float payload
        and asserting it raises BEFORE any signature check would have
        run. This guards against future refactors that move the
        _reject_floats call out of canonicalize.
        """
        priv, pub = generate_keypair()
        bad_payload = {"score": 1.0}

        # Cannot even canonicalize, so cannot sign.
        with pytest.raises(FloatInSignedSchemaError):
            canonicalize(bad_payload)

        # Therefore verify_signature on the same payload must also raise,
        # not return False. (Returning False would be a silent downgrade.)
        with pytest.raises(FloatInSignedSchemaError):
            verify_signature(bad_payload, "dummy==", pub)


# ------------------------------------------------------------------
# Cross-language fixture parity
# ------------------------------------------------------------------


class TestCrossLanguageFixtures:
    """Shared fixtures with the Rust and TypeScript SDKs.

    Each fixture file is a JSON document that *should* be rejected by the
    float rule. The Rust and TS sides have mirror tests that load the same
    files and assert rejection. If a runtime fails to reject, the cross-
    language signature contract is broken.

    Fixtures live under tests/fixtures/canonical_float_reject/.
    """

    @pytest.fixture(autouse=True)
    def _ensure_fixtures_exist(self):
        if not FIXTURE_DIR.exists():
            pytest.skip(
                f"fixture directory {FIXTURE_DIR} not yet populated; "
                f"run scripts/gen_canonical_float_fixtures.py"
            )

    def _load_fixture(self, name: str) -> dict:
        path = FIXTURE_DIR / name
        with path.open() as f:
            return json.load(f)

    def test_fixture_integral_float_rejected(self):
        """The motivating bug: integral float 1.0 vs int 1."""
        obj = self._load_fixture("integral_float.json")
        with pytest.raises(FloatInSignedSchemaError):
            canonicalize(obj)

    def test_fixture_confidence_field_rejected(self):
        obj = self._load_fixture("confidence_field.json")
        with pytest.raises(FloatInSignedSchemaError):
            canonicalize(obj)

    def test_fixture_nested_float_rejected(self):
        obj = self._load_fixture("nested_float.json")
        with pytest.raises(FloatInSignedSchemaError):
            canonicalize(obj)

    def test_fixture_list_of_floats_rejected(self):
        obj = self._load_fixture("list_of_floats.json")
        with pytest.raises(FloatInSignedSchemaError):
            canonicalize(obj)

    def test_fixture_clean_int_payload_canonicalizes(self):
        """Negative case: a clean int-only fixture must NOT be rejected.
        This guards against an over-eager walker that rejects ints too."""
        obj = self._load_fixture("clean_int.json")
        # Should not raise.
        out = canonicalize(obj)
        assert isinstance(out, bytes)
        assert b"." not in out  # no float decimal points


# ------------------------------------------------------------------
# Regression guard
# ------------------------------------------------------------------


class TestRegressionGuard:
    """If someone removes _reject_floats from canonicalize, this fires.

    The mechanism: assert that the canonical bytes of an int-only payload
    differ from the canonical bytes that Python *would* produce for the
    float version of the same payload. If floats were allowed, the two
    would have different byte lengths (int -> "1", float -> "1.0").
    """

    def test_int_and_float_payloads_differ_in_canonical_bytes(self):
        int_payload = {"score": 1}
        float_payload = {"score": 1.0}

        int_bytes = canonicalize(int_payload)
        assert int_bytes == b'{"score":1}'

        # The float version must raise, not produce b'{"score":1.0}'.
        with pytest.raises(FloatInSignedSchemaError):
            canonicalize(float_payload)

        # The bytes the float version would have produced (if it didn't
        # raise) are NOT what we want to sign. This is the silent failure
        # mode that motivated the rule.
        would_be_float_bytes = json.dumps(
            float_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        assert would_be_float_bytes == b'{"score":1.0}'
        assert int_bytes != would_be_float_bytes
