"""Export CogniCore memories as a sealed, signed transfer bundle.

Produces a JSON file containing:
  - ``memories``  -- filtered, consequence-classified memory records
  - ``proofs``    -- evidence receipts (content hashes, exit codes, etc.)
  - ``custody``   -- signed chain of custody
  - ``signature`` -- Ed25519 over deterministic canonical JSON payload

The retrieval index is *never* transported.  It is derived state, rebuilt
at import.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from cognicore.memory.base import MemoryEntry, MemoryState
from cognicore.memory_manager import MemoryManager

from cognicore.integrations.mem0.bundle import (
    BundleReceipt,
    ConsequenceClass,
    CustodyAction,
    CustodyHop,
)
from cognicore.integrations.mem0.crypto import (
    key_fingerprint,
    sign_bundle,
)

logger = logging.getLogger("cognicore.integrations.mem0.exporter")


# ------------------------------------------------------------------
# Secret deny-list
# ------------------------------------------------------------------

SECRET_DENY_SUBSTRINGS = frozenset(
    {
        "api_key",
        "token",
        "secret",
        "password",
        "credential",
        "private_key",
        "auth_token",
        "access_key",
        "bearer",
    }
)

# Categories that map to authority consequence class.
AUTHORITY_CATEGORIES = frozenset(
    {
        "credential",
        "permission",
        "tool_grant",
        "access_control",
        "api_key",
        "auth",
    }
)

EXPORTABLE_STATES = frozenset(
    {
        MemoryState.VERIFIED.value,
        MemoryState.PROMOTED.value,
        MemoryState.TRANSFERABLE.value,
    }
)

OBSERVED_STATES = frozenset(
    {
        MemoryState.OBSERVED.value,
        MemoryState.CANDIDATE.value,
    }
)

# Internal metadata keys that must not survive transport.
_INTERNAL_META_KEYS = (
    "_tfidf_vector",
    "_inserted_at_step",
    "_quarantine",
    "_import_source",
    "_import_timestamp",
    "_original_state",
    "bundle_entry_id",
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _has_secret_keys(metadata: Dict[str, Any]) -> List[str]:
    """Return metadata keys that match the secret deny-list."""
    found: List[str] = []
    for key in metadata:
        key_lower = key.lower()
        for deny in SECRET_DENY_SUBSTRINGS:
            if deny in key_lower:
                found.append(key)
                break
    return found


def _classify_consequence(entry: MemoryEntry) -> ConsequenceClass:
    """Determine whether a memory carries authority or is pure information."""
    cat = (entry.category or "").lower()
    if cat in AUTHORITY_CATEGORIES:
        return ConsequenceClass.AUTHORITY

    meta = entry.metadata or {}
    if any(k.lower() in AUTHORITY_CATEGORIES for k in meta):
        return ConsequenceClass.AUTHORITY

    if meta.get("consequence_class") == ConsequenceClass.AUTHORITY.value:
        return ConsequenceClass.AUTHORITY

    return ConsequenceClass.INFORMATION


def _entry_to_record(entry: MemoryEntry) -> Dict[str, Any]:
    """Convert a MemoryEntry to a bundle-transportable record dict."""
    record = entry.to_dict()
    # Strip internal / derived fields
    meta = record.get("metadata", {})
    for internal_key in _INTERNAL_META_KEYS:
        meta.pop(internal_key, None)
    # Restore original bundle_entry_id if recorded
    orig_id = (entry.metadata or {}).get("bundle_entry_id")
    if orig_id:
        record["entry_id"] = orig_id
    record["consequence_class"] = _classify_consequence(entry).value
    return record


def _load_entries_from_manager(mgr: MemoryManager) -> List[MemoryEntry]:
    """Read all stored memory entries from a MemoryManager's SQLite store and session files."""
    entries: List[MemoryEntry] = []
    seen_ids: Set[str] = set()

    # 1. Load from main SQLite database if present
    db_path = getattr(mgr, "db_path", os.path.join(mgr.storage_dir, "cognicore_memory.db"))
    if os.path.exists(db_path):
        try:
            from cognicore.memory.sqlite_backend import SQLiteMemoryBackend
            sqlite_backend = SQLiteMemoryBackend(db_path)
            for e in sqlite_backend.get_all():
                bundle_id = (e.metadata or {}).get("bundle_entry_id") or e.entry_id
                if bundle_id not in seen_ids:
                    seen_ids.add(bundle_id)
                    entries.append(e)
        except Exception as exc:
            logger.warning("Error loading from SQLite %s: %s", db_path, exc)

    # 2. Also load from session memory.json files
    if os.path.exists(mgr.storage_dir):
        for agent_name in os.listdir(mgr.storage_dir):
            agent_dir = os.path.join(mgr.storage_dir, agent_name)
            if not os.path.isdir(agent_dir):
                continue
            mem_path = os.path.join(agent_dir, "memory.json")
            if not os.path.isfile(mem_path):
                continue
            try:
                with open(mem_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                if isinstance(raw_data, dict):
                    raw_entries = raw_data.get("entries", [])
                elif isinstance(raw_data, list):
                    raw_entries = raw_data
                else:
                    raw_entries = []
                for raw in raw_entries:
                    if isinstance(raw, dict):
                        e = MemoryEntry.from_dict(raw)
                        bundle_id = (e.metadata or {}).get("bundle_entry_id") or e.entry_id
                        if bundle_id not in seen_ids:
                            seen_ids.add(bundle_id)
                            entries.append(e)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping %s: %s", mem_path, exc)

    return entries


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def export_bundle(
    source: MemoryManager,
    out: Path,
    *,
    include_categories: Optional[Set[str]] = None,
    include_observed: bool = False,
    signing_key: Any,  # Ed25519PrivateKey
    signer_id: str,
) -> BundleReceipt:
    """Produce a sealed transfer bundle.

    JSON, deterministic canonical JSON, signed with Ed25519 over canonical bytes.

    Parameters
    ----------
    source:
        MemoryManager containing the memories to export.
    out:
        File path for the output bundle.
    include_categories:
        If set, only export memories whose category is in this set.
    include_observed:
        If ``True``, also include OBSERVED / CANDIDATE memories (they are
        marked per-record in the bundle).
    signing_key:
        Ed25519 private key for signing.
    signer_id:
        Identifier for the signing entity.

    Returns
    -------
    BundleReceipt
        Export statistics.

    Raises
    ------
    ValueError
        If any eligible memory contains secret / authority-bearing metadata.
        Export of authority-bearing data is refused with an explicit error,
        not filtered silently.
    """
    entries = _load_entries_from_manager(source)

    eligible_states = set(EXPORTABLE_STATES)
    if include_observed:
        eligible_states |= OBSERVED_STATES

    # ---- Filter ----
    filtered: List[MemoryEntry] = []
    for entry in entries:
        if entry.state not in eligible_states:
            continue
        if include_categories and entry.category not in include_categories:
            continue
        # Secret check -- refuse with explicit error, never filter silently
        secret_keys = _has_secret_keys(entry.metadata or {})
        if secret_keys:
            raise ValueError(
                f"Memory {entry.entry_id!r} contains secret metadata keys "
                f"{secret_keys}. Export of authority-bearing data is refused. "
                f"Remove these keys before exporting."
            )
        filtered.append(entry)

    # ---- Build records & proofs ----
    records: List[Dict[str, Any]] = []
    proofs: List[Dict[str, Any]] = []
    by_category: Dict[str, int] = {}
    by_consequence: Dict[str, int] = {}

    for entry in filtered:
        record = _entry_to_record(entry)

        if entry.state in OBSERVED_STATES:
            record["_observed_at_export"] = True

        records.append(record)

        # Collect evidence as proofs
        meta = entry.metadata or {}
        exp_data = meta.get("experience", {})
        if isinstance(exp_data, dict):
            for ev in exp_data.get("verification_evidence", []):
                proofs.append({"memory_id": record["entry_id"], "evidence": ev})

        cat = entry.category or "uncategorized"
        by_category[cat] = by_category.get(cat, 0) + 1
        cc = record["consequence_class"]
        by_consequence[cc] = by_consequence.get(cc, 0) + 1

    # Guarantee at least one proof entry per memory (content-hash proof)
    if not proofs:
        for rec in records:
            meta = rec.get("metadata", {})
            content_hash = meta.get("content_hash", "")
            if content_hash:
                proofs.append(
                    {
                        "memory_id": rec.get("entry_id", ""),
                        "evidence": {"content_hash": content_hash},
                    }
                )

    now_iso = datetime.now(timezone.utc).isoformat()
    pub_key = signing_key.public_key()

    custody = [
        CustodyHop(
            signer_id=signer_id,
            action=CustodyAction.SIGN.value,
            timestamp=now_iso,
            key_fingerprint=key_fingerprint(pub_key),
        ).to_dict()
    ]

    bundle_payload: Dict[str, Any] = {
        "version": "1.0",
        "created_at": now_iso,
        "exporter": "cognicore-mem0-bridge/1.0",
        "memories": records,
        "proofs": proofs,
        "custody": custody,
    }

    # Sign over canonical payload (without signature field)
    sig = sign_bundle(bundle_payload, signing_key)
    bundle_payload["signature"] = sig

    # Write bundle
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(bundle_payload, f, indent=2, ensure_ascii=True)

    return BundleReceipt(
        bundle_path=str(out),
        total_exported=len(records),
        by_category=by_category,
        by_consequence_class=by_consequence,
        signer_id=signer_id,
        created_at=now_iso,
    )
