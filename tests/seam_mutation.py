"""Semantic mutation for the verifier-defeat vector (recall-seam defeat).

Applied only when the test run passes ``--seam-mutation`` (see
``tests/conftest.py``); never active in production, in normal test runs,
or in CI jobs that do not opt in.

What it does
------------
It defeats the reachability guarantee at the recall seam: every query
"finds" every stored entry, so ``reachable_ids`` always covers
``imported_ids``, ``dark`` is always empty, and the reachability verdict
in ``importer.py`` can never fire.  The check line itself is left
byte-identical -- only its input is lied to.

This is the runtime-patch equivalent of the source-level mutation::

    - dark = imported_ids - reachable_ids
    + dark = set()

reviewed externally (2026-09-27, tested at ``27c0b89``, "mutation B"),
and it is deliberately *semantic* rather than textual:

  - it survives reformatting of ``importer.py`` (black, renames, type
    hints cannot make it vacuous),
  - it never edits shared disk state -- the mutation lives only inside
    the subprocess that requested it, so it is safe under pytest-xdist,
  - it fails loudly if its target moves: the patch addresses
    ``QuarantinePartition.search_trusted`` by name, so a refactor that
    renames or removes the recall seam raises ``AttributeError`` and the
    vector reports "target moved" instead of passing vacuously.

A moved check and a deleted check are both findings.
"""

from __future__ import annotations

from cognicore.memory.base import SearchResult


def apply_bright_recall_mutation() -> None:
    """Make every recall query 'succeed': all stored entries are reachable.

    The lie is told above the backend layer (``SQLiteMemoryBackend.search``
    / ``get_by_category``), so tests that patch those to simulate index
    lag -- the firing test's own seam -- are unaffected by construction:
    this patch intercepts the recall call first and short-circuits it.
    """
    from cognicore.integrations.mem0 import quarantine as quarantine_module
    from cognicore.memory.tfidf_backend import TFIDFMemoryBackend

    # Target 1: the trusted recall path (primary -- the firing test's dark
    # claim is a verified/trusted entry).
    def _bright_search_trusted(self, query: str, top_k: int = 5):
        entries = self.trusted.get_all()
        return [
            SearchResult(entry=e, score=1.0, source="mutation:bright-recall")
            for e in entries
        ]

    # Target 2: the quarantine recall path (same lie, other partition).
    def _bright_quarantine_search(self, query: str, top_k: int = 5):
        return [
            SearchResult(entry=e, score=1.0, source="mutation:bright-recall")
            for e in self.entries
        ]

    # Fail loudly if the recall seam moves.
    assert hasattr(quarantine_module.QuarantinePartition, "search_trusted"), (
        "mutation target drifted: QuarantinePartition.search_trusted no "
        "longer exists. Update the seam-mutation vector to the new recall "
        "seam -- a moved check and a deleted check are both findings."
    )
    assert hasattr(TFIDFMemoryBackend, "search"), (
        "mutation target drifted: TFIDFMemoryBackend.search no longer "
        "exists. Update the seam-mutation vector to the new quarantine "
        "recall seam."
    )

    quarantine_module.QuarantinePartition.search_trusted = _bright_search_trusted
    TFIDFMemoryBackend.search = _bright_quarantine_search
