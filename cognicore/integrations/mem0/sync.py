"""Push verified CogniCore memories into a live mem0 client.

Category mapping (bidirectional)::

    CogniCore category        | mem0 mapping
    --------------------------|---------------------------------------------
    build_command             | procedure (custom metadata: kind=command)
    failure / pitfall         | memory with kind=warning, inferred=False
    success / workaround      | memory with kind=solution
    environment_fingerprint   | memory metadata block
    evidence receipt          | mem0 metadata dict (never merged into text)

Two rules:
  (a) nothing syncs into mem0 unless it is VERIFIED / PROMOTED / TRANSFERABLE;
  (b) when mem0 later exports back, import_bundle treats everything as
      unverified information -- round-trips never inherit trust.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Set

from cognicore.memory.base import MemoryEntry, MemoryState
from cognicore.memory_manager import MemoryManager
from cognicore.integrations.mem0.bundle import SyncReceipt

logger = logging.getLogger("cognicore.integrations.mem0.sync")


# ------------------------------------------------------------------
# Category mapping
# ------------------------------------------------------------------

CATEGORY_MAP: Dict[str, Dict[str, Any]] = {
    "build_command": {"mem0_type": "procedure", "metadata": {"kind": "command"}},
    "failure": {
        "mem0_type": "memory",
        "metadata": {"kind": "warning", "inferred": False},
    },
    "pitfall": {
        "mem0_type": "memory",
        "metadata": {"kind": "warning", "inferred": False},
    },
    "success": {"mem0_type": "memory", "metadata": {"kind": "solution"}},
    "workaround": {"mem0_type": "memory", "metadata": {"kind": "solution"}},
    "environment_fingerprint": {
        "mem0_type": "memory",
        "metadata": {"kind": "environment"},
    },
}

SYNCABLE_STATES = frozenset(
    {
        MemoryState.VERIFIED.value,
        MemoryState.PROMOTED.value,
        MemoryState.TRANSFERABLE.value,
    }
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _map_to_mem0(entry: MemoryEntry) -> Dict[str, Any]:
    """Map a CogniCore memory entry to mem0 ``add()`` format."""
    cat = (entry.category or "").lower()
    mapping = CATEGORY_MAP.get(
        cat, {"mem0_type": "memory", "metadata": {}}
    )

    text = entry.text or ""

    # Build metadata -- evidence receipts go into metadata, never text
    mem0_metadata: Dict[str, Any] = dict(mapping.get("metadata", {}))
    mem0_metadata["cognicore_category"] = entry.category
    mem0_metadata["cognicore_entry_id"] = entry.entry_id
    mem0_metadata["cognicore_state"] = entry.state
    mem0_metadata["cognicore_confidence"] = entry.confidence

    exp_data = (entry.metadata or {}).get("experience", {})
    if isinstance(exp_data, dict):
        evidence = exp_data.get("verification_evidence", [])
        if evidence:
            mem0_metadata["cognicore_evidence"] = evidence

        env = exp_data.get("environment", {})
        if env:
            mem0_metadata["cognicore_environment"] = env

    return {"text": text, "metadata": mem0_metadata}


def _load_entries_from_manager(mgr: MemoryManager) -> List[MemoryEntry]:
    """Read all stored memory entries from a MemoryManager."""
    entries: List[MemoryEntry] = []
    if not os.path.exists(mgr.storage_dir):
        return entries

    for agent_name in os.listdir(mgr.storage_dir):
        agent_dir = os.path.join(mgr.storage_dir, agent_name)
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
                    entries.append(MemoryEntry.from_dict(raw))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping %s: %s", mem_path, exc)

    return entries


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def sync_to_mem0(
    target_mem0_client: Any,
    source: MemoryManager,
    categories: Optional[Set[str]] = None,
) -> SyncReceipt:
    """Push CogniCore verified memories into a live mem0 client.

    Only memories with state VERIFIED / PROMOTED / TRANSFERABLE are synced.

    Parameters
    ----------
    target_mem0_client:
        A mem0 client instance with an ``.add()`` method.
    source:
        MemoryManager to read memories from.
    categories:
        If set, only sync memories whose category is in this set.

    Returns
    -------
    SyncReceipt
        Sync statistics.
    """
    entries = _load_entries_from_manager(source)

    total_synced = 0
    skipped = 0
    errors: List[str] = []
    by_category: Dict[str, int] = {}

    for entry in entries:
        if entry.state not in SYNCABLE_STATES:
            skipped += 1
            continue

        if categories and entry.category not in categories:
            skipped += 1
            continue

        mem0_data = _map_to_mem0(entry)

        try:
            target_mem0_client.add(
                mem0_data["text"],
                metadata=mem0_data["metadata"],
            )
            total_synced += 1
            cat = entry.category or "uncategorized"
            by_category[cat] = by_category.get(cat, 0) + 1
        except Exception as exc:
            errors.append(f"Failed to sync {entry.entry_id}: {exc}")
            logger.error("mem0 sync error for %s: %s", entry.entry_id, exc)

    return SyncReceipt(
        total_synced=total_synced,
        by_category=by_category,
        skipped=skipped,
        errors=errors,
    )
