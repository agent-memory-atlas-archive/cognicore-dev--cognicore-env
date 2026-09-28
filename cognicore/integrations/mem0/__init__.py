"""
CogniCore <-> mem0 verified memory bridge.

Provides sealed bundle export/import with fail-closed Ed25519 verification
and a sync path to push verified memories into a live mem0 client.

Category mapping (bidirectional)::

    CogniCore category        | mem0 mapping
    --------------------------|---------------------------------------------
    build_command             | procedure (custom metadata: kind=command)
    failure / pitfall         | memory with kind=warning, inferred=False
    success / workaround      | memory with kind=solution
    environment_fingerprint   | memory metadata block
    evidence receipt          | mem0 metadata dict (never merged into text)

Two invariants:

    (a) Nothing syncs into mem0 unless VERIFIED / PROMOTED / TRANSFERABLE.
    (b) Round-trips never inherit trust -- re-imported bundles enter quarantine.

Public API::

    export_bundle(source, out, ...) -> BundleReceipt
    import_bundle(path, target, ...) -> ImportReceipt
    sync_to_mem0(target_mem0_client, ...) -> SyncReceipt
    QuarantinePartition(storage_dir) -> structural quarantine partition
"""

from cognicore.integrations.mem0.bundle import (
    BundleReceipt,
    ConsequenceClass,
    ImportReceipt,
    ImportVerdict,
    SyncReceipt,
)
from cognicore.integrations.mem0.exporter import export_bundle
from cognicore.integrations.mem0.importer import import_bundle
from cognicore.integrations.mem0.quarantine import QuarantinePartition
from cognicore.integrations.mem0.sync import sync_to_mem0

__all__ = [
    "export_bundle",
    "import_bundle",
    "sync_to_mem0",
    "QuarantinePartition",
    "BundleReceipt",
    "ImportReceipt",
    "SyncReceipt",
    "ConsequenceClass",
    "ImportVerdict",
]
