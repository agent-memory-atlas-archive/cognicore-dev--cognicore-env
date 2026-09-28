"""Tests for the CogniCore <-> mem0 verified memory bridge.

Acceptance criteria from the design review:

1. happy-path (section-8 conformance)
   Deterministic canonical JSON, valid signature, all sections populated.
   Imports clean, receipt counts match, lands 3/3 trusted (0 quarantined),
   reachability 100% verified through the index/recall path.

2. digest-mismatch
   One byte flipped in a memory record after signing.
   Import fails INTEGRITY_FAILED.

3. env-incompatible
   Memories stamped with a different environment fingerprint.
   Import succeeds but every record lands OBSERVED in structural quarantine.

4. revoked-but-unexpired
   Signature valid, custody chain contains a valid revocation of the
   signing key.  Import fails REVOKED.  This is the case that
   signature-only loaders pass -- ours must not.

5. empty-proofs
   Proofs section null/empty.  Parse-time INTEGRITY_FAILED, same code
   path as tampering.

6. authority-refused
   Bundle containing an authority-class record.  Refused with an explicit
   message naming the upgrade path.

7. no-tunnel
   Grep-level test: no public function parameter or env var can disable
   signature verification or quarantine.

8. round-trip
   Export -> import into a fresh store -> export again ->
   byte-comparable memory payloads (ids and custody chains will differ;
   content hashes must not).

9. promotion-on-evidence
   Fresh verification evidence promotes a quarantined record to trusted,
   moving it structurally into the trusted index and making it searchable.

10. promotion-refused
   Time elapsed and repeated recall do NOT promote.
   Promotion without fresh evidence raises ValueError.
"""

from __future__ import annotations

import gc
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from cognicore.experience.schema import EvidenceRecord
from cognicore.memory.base import MemoryEntry, MemoryState
from cognicore.memory_manager import MemoryManager

from cognicore.integrations.mem0.bundle import (
    ConsequenceClass,
    ImportReceipt,
    ImportVerdict,
)
from cognicore.integrations.mem0.crypto import (
    generate_keypair,
    key_fingerprint,
    sign_bundle,
)
from cognicore.integrations.mem0.exporter import export_bundle
from cognicore.integrations.mem0.importer import IntegrityFailed, import_bundle
from cognicore.integrations.mem0.quarantine import QuarantinePartition


@contextmanager
def _safe_tmpdir():
    """TemporaryDirectory that releases SQLite file locks before cleanup.

    On Windows, open SQLite connections hold file locks that prevent
    TemporaryDirectory from cleaning up.  This helper forces GC
    and retries removal with a brief delay.
    """
    tmpdir = tempfile.mkdtemp()
    try:
        yield tmpdir
    finally:
        gc.collect()
        try:
            shutil.rmtree(tmpdir)
        except PermissionError:
            gc.collect()
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass  # Best-effort on Windows


# ======================================================================
# Helpers
# ======================================================================



def _make_verified_entry(
    entry_id: str = "test-001",
    text: str = "Fix build by adding -std=c++17 flag",
    category: str = "build_command",
    state: str = MemoryState.VERIFIED.value,
    env: dict | None = None,
) -> MemoryEntry:
    """Create a MemoryEntry suitable for export."""
    if env is None:
        env = {
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            "os": platform.system().lower(),
        }
    return MemoryEntry(
        entry_id=entry_id,
        text=text,
        category=category,
        state=state,
        confidence=0.95,
        memory_type="experience",
        source_agent="test-agent",
        source_task="test-task",
        creation_reason="structured_experience",
        metadata={
            "experience": {
                "task": "fix build",
                "problem": "compilation error",
                "verification_evidence": [
                    {
                        "command": "make build",
                        "exit_code": 0,
                        "stdout_hash": "abc123",
                        "timestamp": "2026-09-20T10:00:00Z",
                    }
                ],
                "environment": env,
            },
            "content_hash": "sha256:" + hashlib.sha256(
                f"{entry_id}:{text}".encode("utf-8")
            ).hexdigest(),
        },
    )


def _setup_manager_with_entries(
    tmpdir: str,
    entries: list[MemoryEntry],
    agent_id: str = "test-agent",
) -> MemoryManager:
    """Create a MemoryManager with pre-populated entries."""
    mgr = MemoryManager(storage_dir=tmpdir)
    agent_dir = os.path.join(tmpdir, agent_id)
    os.makedirs(agent_dir, exist_ok=True)

    serialized = [e.to_dict() for e in entries]
    with open(os.path.join(agent_dir, "memory.json"), "w") as f:
        json.dump(serialized, f, indent=2, default=str)

    return mgr


def _export_and_get_bundle(
    tmpdir: str,
    entries: list[MemoryEntry] | None = None,
    signing_key=None,
    signer_id: str = "test-signer",
):
    """Export a bundle and return (path, bundle_dict, private_key, public_key)."""
    if signing_key is None:
        private_key, public_key = generate_keypair()
    else:
        private_key = signing_key
        public_key = signing_key.public_key()

    if entries is None:
        entries = [_make_verified_entry()]

    source_dir = os.path.join(tmpdir, "source")
    mgr = _setup_manager_with_entries(source_dir, entries)

    bundle_path = Path(tmpdir) / "bundle.json"
    export_bundle(
        source=mgr,
        out=bundle_path,
        signing_key=private_key,
        signer_id=signer_id,
    )

    with open(bundle_path) as f:
        bundle_dict = json.load(f)

    return bundle_path, bundle_dict, private_key, public_key


# ======================================================================
# 1. Happy-path conformance
# ======================================================================


class TestHappyPath:
    """section-8 conformance: canonical JSON, valid signature, clean import."""

    def test_export_structure(self):
        with _safe_tmpdir() as tmpdir:
            entries = [
                _make_verified_entry("mem-001", "Use cmake", "build_command"),
                _make_verified_entry("mem-002", "Avoid rm -rf /", "pitfall"),
                _make_verified_entry("mem-003", "Use pytest -x", "success"),
            ]
            path, bundle, _, _ = _export_and_get_bundle(tmpdir, entries)

            assert "memories" in bundle
            assert "proofs" in bundle
            assert "custody" in bundle
            assert "signature" in bundle
            assert len(bundle["memories"]) == 3
            assert len(bundle["proofs"]) >= 1

            for mem in bundle["memories"]:
                assert "consequence_class" in mem

    def test_import_clean_and_reachability(self):
        with _safe_tmpdir() as tmpdir:
            entries = [
                _make_verified_entry("mem-001", "Use cmake", "build_command"),
                _make_verified_entry("mem-002", "Avoid rm -rf /", "pitfall"),
                _make_verified_entry("mem-003", "Use pytest -x", "success"),
            ]
            path, _, _, pub = _export_and_get_bundle(tmpdir, entries)

            target_dir = os.path.join(tmpdir, "target")
            target_mgr = MemoryManager(storage_dir=target_dir)

            receipt = import_bundle(
                path=path,
                target=target_mgr,
                signer_keys={"test-signer": pub},
            )

            assert receipt.verdict == ImportVerdict.OK
            assert receipt.total_imported == 3
            # Valid verified memories land trusted (not quarantined)
            assert receipt.trusted == 3
            assert receipt.quarantined == 0
            assert receipt.authority_refused == 0

            # Verify structural partition on disk
            import_dirs = [
                d
                for d in os.listdir(target_dir)
                if d.startswith("mem0_import_")
            ]
            assert len(import_dirs) == 1
            session_dir = os.path.join(target_dir, import_dirs[0])

            # Use target_mgr.db_path since the importer wrote to the
            # target's main SQLite store, not the session dir's default DB
            partition = QuarantinePartition(session_dir, db_path=target_mgr.db_path)
            assert partition.trusted_count == 3
            assert partition.quarantine_count == 0

            # Reachability 100% verified through the index/recall path,
            # not just get_by_id()
            for entry in entries:
                search_results = partition.search_trusted(entry.text, top_k=10)
                # SQLite uses auto-increment integer IDs; original entry_id
                # is preserved as bundle_entry_id in metadata
                found_bundle_ids = set()
                for r in search_results:
                    meta = r.entry.metadata or {}
                    found_bundle_ids.add(meta.get("bundle_entry_id", r.entry.entry_id))
                    found_bundle_ids.add(r.entry.entry_id)
                assert entry.entry_id in found_bundle_ids, (
                    f"Entry {entry.entry_id} not retrievable via search "
                    f"query {entry.text!r} in trusted index"
                )


# ======================================================================
# 2. Digest-mismatch
# ======================================================================


class TestDigestMismatch:
    """One byte flipped after signing -> INTEGRITY_FAILED."""

    def test_tampered_text(self):
        with _safe_tmpdir() as tmpdir:
            path, bundle, _, pub = _export_and_get_bundle(tmpdir)

            bundle["memories"][0]["text"] = "TAMPERED TEXT"

            tampered = Path(tmpdir) / "tampered.json"
            with open(tampered, "w") as f:
                json.dump(bundle, f)

            target_mgr = MemoryManager(
                storage_dir=os.path.join(tmpdir, "target")
            )

            with pytest.raises(IntegrityFailed) as exc_info:
                import_bundle(
                    path=tampered,
                    target=target_mgr,
                    signer_keys={"test-signer": pub},
                )

            assert exc_info.value.verdict == ImportVerdict.INTEGRITY_FAILED


# ======================================================================
# 3. Env-incompatible
# ======================================================================


class TestEnvIncompatible:
    """Different env fingerprint -> structural quarantine, none trusted."""

    def test_foreign_os(self):
        with _safe_tmpdir() as tmpdir:
            foreign_os = (
                "linux"
                if platform.system().lower() != "linux"
                else "darwin"
            )
            entries = [
                _make_verified_entry(
                    "mem-env-001",
                    "Linux-specific fix",
                    "build_command",
                    env={"python_version": "3.10", "os": foreign_os},
                ),
            ]
            path, _, _, pub = _export_and_get_bundle(tmpdir, entries)

            target_dir = os.path.join(tmpdir, "target")
            target_mgr = MemoryManager(storage_dir=target_dir)

            receipt = import_bundle(
                path=path,
                target=target_mgr,
                signer_keys={"test-signer": pub},
            )

            assert receipt.verdict == ImportVerdict.OK
            assert receipt.total_imported == 1
            assert receipt.env_incompatible == 1
            assert receipt.quarantined == 1
            assert receipt.trusted == 0

            # Structural partition verification
            import_dirs = [
                d
                for d in os.listdir(target_dir)
                if d.startswith("mem0_import_")
            ]
            assert len(import_dirs) == 1
            session_dir = os.path.join(target_dir, import_dirs[0])

            partition = QuarantinePartition(session_dir)
            assert partition.quarantine_count == 1
            assert partition.trusted_count == 0

            # Quarantined record is invisible to trusted reads
            assert partition.get_trusted_by_id("mem-env-001") is None
            assert len(partition.search_trusted("Linux-specific fix")) == 0

            # Present in quarantine region
            q_entry = partition.get_quarantined_by_id("mem-env-001")
            assert q_entry is not None
            assert q_entry.state == MemoryState.OBSERVED.value
            assert "incompatible" in (q_entry.invalidated_reason or "").lower()


# ======================================================================
# 4. Revoked-but-unexpired
# ======================================================================


class TestRevokedButUnexpired:
    """Valid signature + custody revocation -> REVOKED."""

    def test_revoked_signer(self):
        with _safe_tmpdir() as tmpdir:
            path, bundle, priv, pub = _export_and_get_bundle(tmpdir)

            # Add a revocation hop for the same signer
            bundle["custody"].append(
                {
                    "signer_id": "test-signer",
                    "action": "revoke",
                    "timestamp": "2026-09-24T12:00:00Z",
                    "key_fingerprint": key_fingerprint(pub),
                    "note": "Key compromised",
                }
            )

            # Re-sign so the signature IS valid
            payload = {
                k: v for k, v in bundle.items() if k != "signature"
            }
            bundle["signature"] = sign_bundle(payload, priv)

            revoked_path = Path(tmpdir) / "revoked.json"
            with open(revoked_path, "w") as f:
                json.dump(bundle, f)

            target_mgr = MemoryManager(
                storage_dir=os.path.join(tmpdir, "target")
            )

            receipt = import_bundle(
                path=revoked_path,
                target=target_mgr,
                signer_keys={"test-signer": pub},
            )

            assert receipt.verdict == ImportVerdict.REVOKED
            assert "revoked" in receipt.message.lower()


# ======================================================================
# 5. Empty-proofs
# ======================================================================


class TestEmptyProofs:
    """Null/empty proofs -> INTEGRITY_FAILED (same path as tampering)."""

    def test_empty_list(self):
        with _safe_tmpdir() as tmpdir:
            path, bundle, priv, pub = _export_and_get_bundle(tmpdir)

            bundle["proofs"] = []
            payload = {
                k: v for k, v in bundle.items() if k != "signature"
            }
            bundle["signature"] = sign_bundle(payload, priv)

            empty_path = Path(tmpdir) / "empty_proofs.json"
            with open(empty_path, "w") as f:
                json.dump(bundle, f)

            target_mgr = MemoryManager(
                storage_dir=os.path.join(tmpdir, "target")
            )

            with pytest.raises(IntegrityFailed) as exc_info:
                import_bundle(
                    path=empty_path,
                    target=target_mgr,
                    signer_keys={"test-signer": pub},
                )

            assert exc_info.value.verdict == ImportVerdict.INTEGRITY_FAILED

    def test_null_proofs(self):
        with _safe_tmpdir() as tmpdir:
            path, bundle, priv, pub = _export_and_get_bundle(tmpdir)

            bundle["proofs"] = None
            payload = {
                k: v for k, v in bundle.items() if k != "signature"
            }
            bundle["signature"] = sign_bundle(payload, priv)

            null_path = Path(tmpdir) / "null_proofs.json"
            with open(null_path, "w") as f:
                json.dump(bundle, f)

            target_mgr = MemoryManager(
                storage_dir=os.path.join(tmpdir, "target")
            )

            with pytest.raises(IntegrityFailed):
                import_bundle(
                    path=null_path,
                    target=target_mgr,
                    signer_keys={"test-signer": pub},
                )


# ======================================================================
# 6. Authority-refused
# ======================================================================


class TestAuthorityRefused:
    """Authority-class record refused with upgrade path message."""

    def test_credential_refused(self):
        with _safe_tmpdir() as tmpdir:
            entries = [
                MemoryEntry(
                    entry_id="auth-001",
                    text="API key for service X",
                    category="credential",
                    state=MemoryState.VERIFIED.value,
                    confidence=1.0,
                    memory_type="experience",
                    source_agent="test-agent",
                    metadata={
                        "experience": {
                            "task": "store credential",
                            "verification_evidence": [
                                {
                                    "command": "test",
                                    "exit_code": 0,
                                    "stdout_hash": "x",
                                }
                            ],
                            "environment": {},
                        },
                        "content_hash": "sha256:" + hashlib.sha256(
                            b"auth-001:API key for service X"
                        ).hexdigest(),
                    },
                ),
            ]
            path, bundle, _, pub = _export_and_get_bundle(tmpdir, entries)

            assert (
                bundle["memories"][0]["consequence_class"] == "authority"
            )

            target_mgr = MemoryManager(
                storage_dir=os.path.join(tmpdir, "target")
            )

            receipt = import_bundle(
                path=path,
                target=target_mgr,
                signer_keys={"test-signer": pub},
            )

            assert receipt.verdict == ImportVerdict.AUTHORITY_REFUSED
            assert receipt.authority_refused == 1
            # Must mention the upgrade path
            msg = receipt.message.lower()
            assert "provisioning" in msg or "access control" in msg


# ======================================================================
# 7. No-tunnel (structural fail-closed)
# ======================================================================


class TestNoTunnel:
    """No public parameter or env var can disable sig verification or quarantine."""

    def test_no_bypass_patterns(self):
        import cognicore.integrations.mem0 as mem0_pkg

        pkg_dir = os.path.dirname(mem0_pkg.__file__)
        source_files = glob.glob(os.path.join(pkg_dir, "*.py"))

        bypass_patterns = [
            r"skip_verify",
            r"disable_signature",
            r"no_verify",
            r"allow_unsigned",
            r"skip_quarantine",
            r"disable_quarantine",
            r"trust_unsigned",
            r"SKIP_VERIFICATION",
            r"DISABLE_QUARANTINE",
            r"NO_SIGNATURE",
            r"os\.environ.*verify",
            r"os\.environ.*quarantine",
            r"os\.environ.*signature",
            r"os\.getenv.*verify",
            r"os\.getenv.*quarantine",
            r"os\.getenv.*signature",
            r"verify\s*[=:]\s*False",
            r"quarantine\s*[=:]\s*False",
            r"best.effort",
        ]

        for src_file in source_files:
            with open(src_file, "r") as f:
                content = f.read()

            for pattern in bypass_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                assert not matches, (
                    f"Bypass pattern {pattern!r} found in "
                    f"{os.path.basename(src_file)}: {matches}. "
                    f"Fail-closed verification must be structural, "
                    f"not a policy toggle."
                )


# ======================================================================
# 8. Round-trip
# ======================================================================


class TestRoundTrip:
    """Export -> import -> export: content hashes must survive."""

    def test_content_hashes_survive(self):
        with _safe_tmpdir() as tmpdir:
            entries = [
                _make_verified_entry(
                    "rt-001", "Use cmake -B build", "build_command"
                ),
                _make_verified_entry(
                    "rt-002", "Never skip tests", "pitfall"
                ),
            ]

            private_key, public_key = generate_keypair()

            # First export
            source_dir = os.path.join(tmpdir, "source1")
            mgr1 = _setup_manager_with_entries(source_dir, entries)

            bundle1_path = Path(tmpdir) / "bundle1.json"
            export_bundle(
                source=mgr1,
                out=bundle1_path,
                signing_key=private_key,
                signer_id="round-trip-signer",
            )

            # Import into fresh store -- verified memories land trusted directly
            target_dir = os.path.join(tmpdir, "target")
            target_mgr = MemoryManager(storage_dir=target_dir)

            receipt = import_bundle(
                path=bundle1_path,
                target=target_mgr,
                signer_keys={"round-trip-signer": public_key},
            )
            assert receipt.verdict == ImportVerdict.OK
            assert receipt.trusted == 2

            # Second export from target store
            bundle2_path = Path(tmpdir) / "bundle2.json"
            export_bundle(
                source=target_mgr,
                out=bundle2_path,
                signing_key=private_key,
                signer_id="round-trip-signer-2",
            )

            # Compare content hashes
            with open(bundle1_path) as f:
                b1 = json.load(f)
            with open(bundle2_path) as f:
                b2 = json.load(f)

            hashes1 = sorted(
                m.get("metadata", {}).get("content_hash", "")
                for m in b1["memories"]
            )
            hashes2 = sorted(
                m.get("metadata", {}).get("content_hash", "")
                for m in b2["memories"]
            )

            assert hashes1 == hashes2, (
                f"Content hashes differ after round-trip.\n"
                f"  Export 1: {hashes1}\n"
                f"  Export 2: {hashes2}"
            )


# ======================================================================
# 9. Promotion Tests (Invariant 4)
# ======================================================================


class TestPromotion:
    """Invariant 4: Promotion only via verification event.
    Never time, never repetition, never volume.
    """

    def test_fresh_evidence_promotes_quarantined_to_trusted(self):
        """Fresh verification evidence promotes a quarantined record to trusted."""
        with _safe_tmpdir() as tmpdir:
            partition = QuarantinePartition(tmpdir)
            entry = _make_verified_entry(
                "quarantine-001", "Quarantined fix for compiler issue", "build_command"
            )
            partition.store_quarantined(entry)

            assert partition.quarantine_count == 1
            assert partition.trusted_count == 0
            assert partition.get_quarantined_by_id("quarantine-001") is not None
            assert partition.get_trusted_by_id("quarantine-001") is None
            # Quarantined entry is completely invisible to trusted reads
            assert len(partition.search_trusted("compiler issue")) == 0

            # Fresh verification evidence
            fresh_evidence = [
                EvidenceRecord(
                    command="gcc -c main.c",
                    exit_code=0,
                    stdout_hash="abc12345",
                    timestamp="2026-09-25T12:00:00Z",
                )
            ]

            promoted = partition.promote(
                "quarantine-001",
                evidence=fresh_evidence,
                new_state=MemoryState.VERIFIED.value,
            )
            assert promoted is True

            # Structurally moved: removed from quarantine, stored in trusted
            assert partition.quarantine_count == 0
            assert partition.trusted_count == 1
            assert partition.get_quarantined_by_id("quarantine-001") is None

            trusted_entry = partition.get_trusted_by_id("quarantine-001")
            assert trusted_entry is not None
            assert trusted_entry.state == MemoryState.VERIFIED.value

            # Now reachable and searchable in trusted index
            results = partition.search_trusted("compiler issue")
            assert len(results) > 0
            # SQLite assigns auto-increment integer IDs; original entry_id
            # is preserved as bundle_entry_id in metadata
            result_meta = results[0].entry.metadata or {}
            result_bundle_id = result_meta.get("bundle_entry_id", results[0].entry.entry_id)
            assert result_bundle_id == "quarantine-001"

    def test_time_elapsed_and_repeated_recall_does_not_promote(self):
        """Time elapsed and repeated recall do NOT promote quarantined records."""
        with _safe_tmpdir() as tmpdir:
            partition = QuarantinePartition(tmpdir)
            entry = _make_verified_entry(
                "quarantine-002", "Stays quarantined memory", "pitfall"
            )
            partition.store_quarantined(entry)

            # 1. Repeated recall attempts (search, get_by_id, get_quarantined)
            for _ in range(50):
                partition.search_trusted("Stays quarantined")
                partition.get_trusted_by_id("quarantine-002")
                partition.get_quarantined_by_id("quarantine-002")
                partition.get_quarantined()

            # Record remains quarantined, not trusted
            assert partition.quarantine_count == 1
            assert partition.trusted_count == 0
            assert partition.get_trusted_by_id("quarantine-002") is None

            # 2. Time elapsed simulation (manipulate timestamps into past)
            q_entry = partition.get_quarantined_by_id("quarantine-002")
            assert q_entry is not None
            q_entry.timestamp -= 86400 * 365  # 1 year in past
            q_entry.last_accessed = q_entry.timestamp
            partition.quarantine.save()

            # Re-instantiate partition from disk
            reloaded = QuarantinePartition(tmpdir)
            assert reloaded.quarantine_count == 1
            assert reloaded.trusted_count == 0
            assert reloaded.get_trusted_by_id("quarantine-002") is None

            # 3. Promotion without evidence raises ValueError
            with pytest.raises(ValueError) as exc_info:
                reloaded.promote("quarantine-002", evidence=[])

            assert "fresh verification evidence" in str(exc_info.value)
            assert reloaded.quarantine_count == 1
            assert reloaded.trusted_count == 0


# ======================================================================
# 15. Verifier-defeat vector (the check is the tested thing)
# ======================================================================
# External review (2026-09-27, tested at 708f7cbd): neutering the
# reachability assertion -- `if dark:` -> `if False and dark:`, one
# line -- left this suite at 12/12 green.  The verdict class existed;
# no test proved the verdict class fires.  These two tests close that
# hole, and are deliberately written so the fault (the mutation) is a
# parameter and the trigger (which check runs it) is an argument:
# point the same vector at the import-time assertion here, and at the
# periodic reachability sweep when it lands, by changing the target.
# ======================================================================


class TestReachabilityFires:
    """The missing direct test: a claim that imports clean but is
    unreachable must raise IntegrityFailed -- same verdict class as a
    tampered bundle.

    Darkness is simulated at the recall seam (index lag: bytes stored,
    index does not name them) because that is the runtime failure mode
    measured upstream: 990 notes on disk, 70 named by the always-loaded
    index, 276 in neither -- byte-identical, unreachable.
    """

    DARK_ID = "mem-002"

    def test_dark_claim_fails_import(self, monkeypatch):
        with _safe_tmpdir() as tmpdir:
            entries = [
                _make_verified_entry("mem-001", "Use cmake", "build_command"),
                _make_verified_entry("mem-002", "Avoid rm -rf /", "pitfall"),
            ]
            path, _, _, pub = _export_and_get_bundle(tmpdir, entries)

            target_dir = os.path.join(tmpdir, "target")
            target_mgr = MemoryManager(storage_dir=target_dir)

            # Export completed before patching; now drop mem-002 from BOTH
            # recall paths (search + category fallback) to model a stale index.
            from cognicore.memory.sqlite_backend import SQLiteMemoryBackend

            orig_search = SQLiteMemoryBackend.search
            orig_by_cat = SQLiteMemoryBackend.get_by_category

            def _drop_dark(results):
                kept = []
                for item in results:
                    entry = getattr(item, "entry", item)  # SearchResult or MemoryEntry
                    meta = getattr(entry, "metadata", None) or {}
                    if meta.get("bundle_entry_id") == self.DARK_ID:
                        continue
                    kept.append(item)
                return kept

            def _dark_search(self, query, *args, **kwargs):
                return _drop_dark(orig_search(self, query, *args, **kwargs))

            def _dark_by_cat(self, *args, **kwargs):
                return _drop_dark(orig_by_cat(self, *args, **kwargs))

            monkeypatch.setattr(SQLiteMemoryBackend, "search", _dark_search)
            monkeypatch.setattr(SQLiteMemoryBackend, "get_by_category", _dark_by_cat)

            with pytest.raises(IntegrityFailed) as exc_info:
                import_bundle(
                    path=path,
                    target=target_mgr,
                    signer_keys={"test-signer": pub},
                )
            assert "reachability" in str(exc_info.value)
            assert exc_info.value.verdict == ImportVerdict.INTEGRITY_FAILED


class TestVerifierDefeatVector:
    """Fault injection aimed at the CHECK, not the artifact.

    Vector: neuter the reachability assertion (`if dark:` ->
    `if False and dark:`).  Expected verdict: the suite goes red.
    If the suite stays green with the check defeated, the guarantee is
    unobservable -- a check nobody has watched fail is a promise, not
    a guarantee.
    """

    IMPORTER = os.path.join(
        "cognicore", "integrations", "mem0", "importer.py"
    )

    def _apply_mutation(self):
        """Apply the one-line neutering to the live source; returns the
        pristine bytes for restore."""
        with open(self.IMPORTER, "r", encoding="utf-8") as fh:
            pristine = fh.read()
        mutated = pristine.replace(
            "    if dark:", "    if False and dark:", 1
        )
        assert mutated != pristine, (
            "mutation site drifted: the 'if dark:' reachability check is "
            "not where this vector expects it. Update the vector to the "
            "new site -- a moved check and a deleted check are both "
            "findings."
        )
        with open(self.IMPORTER, "w", encoding="utf-8") as fh:
            fh.write(mutated)
        return pristine

    @pytest.mark.skipif(
        os.environ.get("PYTEST_XDIST_WORKER") is not None,
        reason="mutates importer.py on disk and runs a subprocess suite; "
        "unsafe under pytest-xdist parallel workers (run serially, or as a "
        "dedicated CI step)",
    )
    def test_reachability_check_defeat_makes_suite_red(self):
        import subprocess
        import sys

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pristine = self._apply_mutation()
        try:
            proc = subprocess.run(
                [
                    sys.executable, "-m", "pytest",
                    "tests/test_mem0_bridge.py", "-q", "--no-header",
                    "-k", "reachability or dark",
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=300,
            )
            assert proc.returncode != 0, (
                "VERIFIER DEFEAT UNDETECTED: the reachability assertion was "
                "neutered (if dark -> if False and dark) and the suite "
                "stayed green. The check is a promise, not a guarantee, "
                "until some test goes red here.\n\n"
                + proc.stdout[-2000:]
            )
        finally:
            with open(self.IMPORTER, "w", encoding="utf-8") as fh:
                fh.write(pristine)
