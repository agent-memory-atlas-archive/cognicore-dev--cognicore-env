"""Data types for the CogniCore <-> mem0 transfer bundle format."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class ConsequenceClass(str, Enum):
    """Classification of a memory record's consequence when acted upon.

    AUTHORITY  -- credentials, tool grants, permissions.  Always refused at import.
    INFORMATION -- context, observations, memories.  Accepted into quarantine.
    """

    AUTHORITY = "authority"
    INFORMATION = "information"


class ImportVerdict(str, Enum):
    """Outcome of an import_bundle operation."""

    OK = "ok"
    INTEGRITY_FAILED = "integrity_failed"
    REVOKED = "revoked"
    AUTHORITY_REFUSED = "authority_refused"


class CustodyAction(str, Enum):
    """Actions in a custody chain hop."""

    SIGN = "sign"
    ROTATE = "rotate"
    REVOKE = "revoke"


@dataclass
class CustodyHop:
    """A single hop in the chain of custody."""

    signer_id: str
    action: str  # CustodyAction value
    timestamp: str
    key_fingerprint: str
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "signer_id": self.signer_id,
            "action": self.action,
            "timestamp": self.timestamp,
            "key_fingerprint": self.key_fingerprint,
        }
        if self.note:
            d["note"] = self.note
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> CustodyHop:
        return cls(
            signer_id=d["signer_id"],
            action=d["action"],
            timestamp=d["timestamp"],
            key_fingerprint=d["key_fingerprint"],
            note=d.get("note", ""),
        )


@dataclass
class BundleReceipt:
    """Receipt from :func:`export_bundle`."""

    bundle_path: str
    total_exported: int
    by_category: Dict[str, int] = field(default_factory=dict)
    by_consequence_class: Dict[str, int] = field(default_factory=dict)
    signer_id: str = ""
    created_at: str = ""
    secrets_denied: int = 0


@dataclass
class ImportReceipt:
    """Receipt from :func:`import_bundle`."""

    verdict: ImportVerdict
    total_imported: int = 0
    quarantined: int = 0
    trusted: int = 0
    authority_refused: int = 0
    env_incompatible: int = 0
    message: str = ""


@dataclass
class SyncReceipt:
    """Receipt from :func:`sync_to_mem0`."""

    total_synced: int = 0
    by_category: Dict[str, int] = field(default_factory=dict)
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
