"""Structural quarantine partition for imported memories.

Quarantined records are physically separated from trusted records.
The trusted partition is backed by SQLiteMemoryBackend (the main CogniCore store),
storing records directly in the ``memory_entries`` SQLite table so the rest of
CogniCore can recall them.

The quarantine partition is a separate file backend (quarantine.json with
TFIDFMemoryBackend), physically partitioned and invisible to normal CogniCore queries.

Trusted reads **cannot** see quarantined records without going through
:meth:`promote`, which requires a verification event (fresh evidence).

Persistence layout::

    <storage_dir>/
        cognicore_memory.db -- main SQLite database (trusted partition)
        quarantine.json     -- quarantined records (invisible to normal reads)
        memory.json         -- session memory entries (session compatibility)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

from cognicore.memory.base import MemoryEntry, MemoryState, SearchResult
from cognicore.memory.sqlite_backend import SQLiteMemoryBackend
from cognicore.memory.tfidf_backend import TFIDFMemoryBackend
from cognicore.experience.schema import EvidenceRecord

logger = logging.getLogger("cognicore.integrations.mem0.quarantine")


class QuarantinePartition:
    """Physically partitioned store with trusted (main SQLite store) and quarantine (JSON) regions.

    The trusted partition is backed by ``SQLiteMemoryBackend`` (the main CogniCore store),
    storing records directly in the ``memory_entries`` SQLite table so the rest of
    CogniCore can recall them.

    The quarantine partition is a separate file backend (``quarantine.json`` with
    ``TFIDFMemoryBackend``), physically partitioned and invisible to normal CogniCore queries.

    Promotion requires a verification event -- fresh evidence attached.
    No code path from quarantine to trusted exists without it.
    """

    def __init__(
        self,
        storage_dir: str,
        db_path: Optional[str] = None,
    ):
        self.storage_dir = storage_dir
        self.db_path = db_path or os.path.join(storage_dir, "cognicore_memory.db")
        self._quarantine_path = os.path.join(storage_dir, "quarantine.json")
        self._session_memory_path = os.path.join(storage_dir, "memory.json")

        os.makedirs(storage_dir, exist_ok=True)

        # Trusted region: main SQLiteMemoryBackend (table memory_entries)
        self.trusted = SQLiteMemoryBackend(db_path=self.db_path)

        # Quarantine region: separate file backend with independent TF-IDF index
        self.quarantine = TFIDFMemoryBackend(
            persistence_path=self._quarantine_path,
        )

    # ----------------------------------------------------------------
    # Write operations
    # ----------------------------------------------------------------

    def store_trusted(self, entry: MemoryEntry) -> str:
        """Store an entry in the trusted partition (main SQLite store)."""
        if not entry.metadata:
            entry.metadata = {}
        if entry.entry_id and "bundle_entry_id" not in entry.metadata:
            entry.metadata["bundle_entry_id"] = entry.entry_id

        # Write directly to SQLite main store (memory_entries table)
        sqlite_id = self.trusted.store(entry)

        # Sync session memory.json for session-level compatibility
        self._sync_session_json(entry)

        return sqlite_id

    def store_quarantined(self, entry: MemoryEntry) -> str:
        """Store an entry in the quarantine partition (separate file backend).

        The entry's state is forced to ``observed`` regardless of its
        original state. It is stored ONLY in quarantine.json; the main
        SQLite store cannot see it.
        """
        entry.state = MemoryState.OBSERVED.value
        return self.quarantine.store(entry)

    def _sync_session_json(self, entry: MemoryEntry) -> None:
        """Keep session memory.json in sync for session-based loaders."""
        entries: List[Dict[str, Any]] = []
        if os.path.exists(self._session_memory_path):
            try:
                with open(self._session_memory_path, "r", encoding="utf-8") as f:
                    entries = json.load(f)
            except Exception:
                entries = []
        entry_dict = entry.to_dict()
        updated = False
        for i, existing in enumerate(entries):
            if isinstance(existing, dict) and (
                existing.get("entry_id") == entry.entry_id
                or existing.get("metadata", {}).get("bundle_entry_id")
                == entry.metadata.get("bundle_entry_id")
            ):
                entries[i] = entry_dict
                updated = True
                break
        if not updated:
            entries.append(entry_dict)
        with open(self._session_memory_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, default=str)

    # ----------------------------------------------------------------
    # Trusted reads (the default query path -- main SQLite store)
    # ----------------------------------------------------------------

    def search_trusted(
        self, query: str, top_k: int = 5,
    ) -> List[SearchResult]:
        """Search only the trusted partition (main SQLite store). Quarantine is invisible."""
        return self.trusted.search(query, top_k=top_k)

    def get_trusted_by_id(self, entry_id: str) -> Optional[MemoryEntry]:
        """Get a trusted entry by ID from the main SQLite store."""
        entry = self.trusted.get_by_id(entry_id)
        if entry is not None:
            return entry
        # Check by bundle_entry_id in metadata
        for e in self.trusted.get_all():
            if (e.metadata and e.metadata.get("bundle_entry_id") == entry_id) or e.entry_id == entry_id:
                return e
        return None

    # ----------------------------------------------------------------
    # Quarantine-only reads (explicit opt-in -- quarantine.json)
    # ----------------------------------------------------------------

    def get_quarantined(self, limit: int = 1000) -> List[MemoryEntry]:
        """List all quarantined records."""
        return self.quarantine.entries[:limit]

    def get_quarantined_by_id(
        self, entry_id: str,
    ) -> Optional[MemoryEntry]:
        """Get a quarantined entry by ID."""
        return self.quarantine.get_by_id(entry_id)

    # ----------------------------------------------------------------
    # Promotion (the ONLY path from quarantine -> trusted SQLite store)
    # ----------------------------------------------------------------

    def promote(
        self,
        entry_id: str,
        evidence: List[Union[EvidenceRecord, Dict[str, Any]]],
        *,
        new_state: str = MemoryState.VERIFIED.value,
    ) -> bool:
        """Promote a quarantined record to trusted (main SQLite store) via a verification event.

        This is the **only** code path from quarantine to trusted.  It
        requires fresh evidence; time, repetition, and recall volume are
        not promotion criteria.
        """
        if not evidence:
            raise ValueError(
                "Promotion requires fresh verification evidence. "
                "Time, repetition, and recall volume are not "
                "promotion criteria."
            )

        entry = self.quarantine.get_by_id(entry_id)
        if entry is None:
            return False

        # Update state and attach evidence
        entry.state = new_state
        if not entry.metadata:
            entry.metadata = {}
        existing = entry.metadata.get("promotion_evidence", [])
        for ev in evidence:
            if hasattr(ev, "to_dict"):
                existing.append(ev.to_dict())
            elif isinstance(ev, dict):
                existing.append(ev)
            else:
                existing.append(str(ev))
        entry.metadata["promotion_evidence"] = existing

        # Move: delete from quarantine.json, store in trusted SQLite store
        self.quarantine.delete(entry_id)
        self.store_trusted(entry)

        logger.info(
            "Promoted %s to trusted SQLite store (state=%s) with %d evidence records",
            entry_id,
            new_state,
            len(evidence),
        )
        return True

    # ----------------------------------------------------------------
    # Stats
    # ----------------------------------------------------------------

    @property
    def trusted_count(self) -> int:
        return self.trusted.count()

    @property
    def quarantine_count(self) -> int:
        return self.quarantine.count()

    # ----------------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying SQLite connection held by the trusted backend.

        Must be called before deleting the storage directory on Windows,
        where open SQLite connections hold file locks.
        """
        conn = getattr(self.trusted, "_conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self.trusted._conn = None
        # Also force-close any connection via _get_conn pattern
        import gc
        gc.collect()
