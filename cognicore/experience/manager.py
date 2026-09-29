"""
CogniCore Experience Manager — Orchestrator.

Top-level API that composes all experience components:
  VerificationGate, EnvironmentChecker, ConflictResolver,
  ExperienceRetriever, RevalidationEngine.

Provides the complete lifecycle:
  record → verify → retrieve → transfer → revalidate → supersede
"""
import logging
from dataclasses import dataclass
from typing import List, Optional

from cognicore.experience.schema import (
    StructuredExperience,
    EvidenceRecord,
    EnvironmentContext,
    RepositoryContext,
    VerificationStatus,
)
from cognicore.experience.verification import VerificationGate, VerificationResult
from cognicore.experience.compatibility import EnvironmentChecker, CompatibilityResult
from cognicore.experience.conflicts import ConflictResolver, ConflictRecord
from cognicore.experience.retrieval import ExperienceRetriever, RetrievalResult
from cognicore.experience.revalidation import (
    RevalidationEngine,
    RevalidationResult,
)
from cognicore.memory.base import MemoryBackend, MemoryEntry, MemoryType

logger = logging.getLogger("cognicore.experience")


@dataclass
class TransferResult:
    """Result of an experience transfer operation."""
    transferred: List[StructuredExperience]
    failures_surfaced: List[StructuredExperience]
    blocked: List[str]
    compatibility: List[CompatibilityResult]
    total_candidates: int


class ExperienceManager:
    """Orchestrates the full Structured Validated Experience lifecycle.

    Usage::

        manager = ExperienceManager(backend)

        # Record
        exp_id = manager.record(experience)

        # Verify with real evidence
        result = manager.verify(exp_id, evidence_list)

        # Retrieve for a new task
        results = manager.retrieve("JWT auth bug", current_env=my_env)

        # Transfer between agents
        transfer = manager.transfer(
            source_backend, target_backend,
            query="auth bug", current_env=target_env
        )

        # Re-validate after env change
        reval = manager.revalidate(exp_id, new_env, new_evidence)
    """

    def __init__(
        self,
        backend: MemoryBackend,
        gate: Optional[VerificationGate] = None,
        checker: Optional[EnvironmentChecker] = None,
        max_age_days: float = 90.0,
    ) -> None:
        self.backend = backend
        self.gate = gate or VerificationGate()
        self.checker = checker or EnvironmentChecker()
        self.conflicts = ConflictResolver()
        self.retriever = ExperienceRetriever(checker=self.checker)
        self.revalidator = RevalidationEngine(
            gate=self.gate, checker=self.checker, max_age_days=max_age_days
        )

    # ------------------------------------------------------------------
    # Record
    # ------------------------------------------------------------------

    def record(self, experience: StructuredExperience) -> str:
        """Store a candidate experience and its failure entries.

        The experience is stored as ``state=candidate``. Individual failed
        attempts are stored as separate ``memory_type=failure`` entries
        with ``state=observed``.

        Args:
            experience: The structured experience to record.

        Returns:
            The experience_id of the stored experience.
        """
        # Store the main experience entry
        entry = experience.to_memory_entry()
        stored_id = self.backend.store(entry)
        # The backend may assign a new integer ID
        experience.experience_id = str(stored_id)
        logger.info(f"Recorded experience {experience.experience_id}: {experience.task}")

        # Store individual failure entries
        failure_entries = experience.to_failure_entries()
        for f_entry in failure_entries:
            self.backend.store(f_entry)
            logger.debug(
                f"Recorded failure for experience {experience.experience_id}: "
                f"{f_entry.metadata.get('approach', '')}"
            )

        return experience.experience_id

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    def verify(
        self,
        experience_id: str,
        evidence: List[EvidenceRecord],
    ) -> VerificationResult:
        """Verify an experience with evidence and promote if valid.

        Args:
            experience_id: The ID of the experience to verify.
            evidence: Pre-collected evidence records.

        Returns:
            VerificationResult indicating success or failure.
        """
        entry = self.backend.get_by_id(experience_id)
        if entry is None:
            return VerificationResult(
                passed=False,
                status=VerificationStatus.CANDIDATE.value,
                evidence=[],
                reason=f"Experience {experience_id} not found",
                blockers=[f"Experience {experience_id} not found"],
            )

        experience = StructuredExperience.from_memory_entry(entry)
        updated_exp = self.gate.promote(experience, evidence, self.backend)

        # Return the verification result, with the potentially-updated experience_id
        result = self.gate.verify(updated_exp, evidence)
        # Attach the new experience_id so callers can track it
        result._promoted_id = updated_exp.experience_id
        return result

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        current_env: Optional[EnvironmentContext] = None,
        current_repo: Optional[RepositoryContext] = None,
        include_failures: bool = True,
        require_verified: bool = True,
        top_k: int = 5,
    ) -> RetrievalResult:
        """Retrieve relevant experiences for a query.

        Default retrieval strongly prefers VERIFIED, CURRENT, and
        CONTEXT-COMPATIBLE experiences. Useful failure experiences
        are also returned when ``include_failures=True``.

        Args:
            query: The search query.
            current_env: Current environment for compatibility filtering.
            current_repo: Current repository for compatibility filtering.
            include_failures: Whether to include failure experiences.
            require_verified: Only return verified+ experiences.
            top_k: Max number of experiences to return.

        Returns:
            RetrievalResult with experiences, failures, and metadata.
        """
        return self.retriever.retrieve(
            query=query,
            backend=self.backend,
            current_env=current_env,
            current_repo=current_repo,
            include_failures=include_failures,
            require_verified=require_verified,
            top_k=top_k,
        )

    # ------------------------------------------------------------------
    # Transfer
    # ------------------------------------------------------------------

    def transfer(
        self,
        source_backend: MemoryBackend,
        target_backend: MemoryBackend,
        query: str,
        current_env: Optional[EnvironmentContext] = None,
        current_repo: Optional[RepositoryContext] = None,
        include_failures: bool = True,
        top_k: int = 5,
    ) -> TransferResult:
        """Transfer verified experiences from source to target backend.

        Pipeline:
        1. Retrieve from source (verified + compatible only)
        2. Check provenance integrity
        3. Check for conflicts in target
        4. Store in target backend

        Only structured experience is transferred — never the full
        conversation.

        Args:
            source_backend: Backend to retrieve from.
            target_backend: Backend to store into.
            query: Search query for relevant experiences.
            current_env: Target environment for compatibility.
            current_repo: Target repository for compatibility.
            include_failures: Transfer failure warnings too.
            top_k: Max experiences to transfer.

        Returns:
            TransferResult with transferred experiences and metadata.
        """
        if source_backend is target_backend:
            raise ValueError("source_backend and target_backend must be different instances")

        # Retrieve from source
        source_retriever = ExperienceRetriever(checker=self.checker)
        results = source_retriever.retrieve(
            query=query,
            backend=source_backend,
            current_env=current_env,
            current_repo=current_repo,
            include_failures=include_failures,
            require_verified=True,
            top_k=top_k,
        )

        transferred: List[StructuredExperience] = []
        blocked: List[str] = []

        for exp in results.experiences:
            # Check provenance
            if not exp.verify_hash():
                blocked.append(
                    f"{exp.experience_id}: provenance hash mismatch (possible tampering)"
                )
                continue

            # Check for conflicts in target
            target_conflicts = self.conflicts.detect_conflicts(exp, target_backend)
            high_conflicts = [c for c in target_conflicts if c.severity == "high"]
            if high_conflicts:
                blocked.append(
                    f"{exp.experience_id}: high-severity conflict with "
                    f"{high_conflicts[0].experience_b_id}"
                )
                continue

            # Store in target
            new_entry = exp.to_memory_entry()
            new_entry.creation_reason = "transferred"
            new_id = target_backend.store(new_entry)
            
            # Update the experience object with its new ID in the target backend
            exp.experience_id = str(new_id)
            transferred.append(exp)
            logger.info(
                f"Transferred experience {exp.experience_id} to target backend"
            )

        # Transfer failure warnings too
        failures_surfaced: List[StructuredExperience] = []
        if include_failures:
            for fail_exp in results.failures:
                fail_entry = MemoryEntry(
                    text=f"FAILURE WARNING: {fail_exp.problem}",
                    category=fail_exp.task,
                    memory_type=MemoryType.FAILURE.value,
                    creation_reason="transferred_failure",
                    source_agent=fail_exp.source_agent,
                    metadata=fail_exp._to_payload_dict() if hasattr(fail_exp, '_to_payload_dict') else {},
                )
                target_backend.store(fail_entry)
                failures_surfaced.append(fail_exp)

        return TransferResult(
            transferred=transferred,
            failures_surfaced=failures_surfaced,
            blocked=blocked,
            compatibility=results.compatibility_results,
            total_candidates=results.total_candidates,
        )

    # ------------------------------------------------------------------
    # Re-validate
    # ------------------------------------------------------------------

    def revalidate(
        self,
        experience_id: str,
        current_env: EnvironmentContext,
        new_evidence: Optional[List[EvidenceRecord]] = None,
    ) -> RevalidationResult:
        """Re-validate an experience against the current environment.

        Args:
            experience_id: The ID of the experience to re-validate.
            current_env: The current environment.
            new_evidence: Optional new evidence for re-verification.

        Returns:
            RevalidationResult with the new validation state.
        """
        entry = self.backend.get_by_id(experience_id)
        if entry is None:
            return RevalidationResult(
                valid=False,
                new_status=VerificationStatus.INVALID.value,
                staleness=None,
                verification=None,
                reason=f"Experience {experience_id} not found",
            )

        experience = StructuredExperience.from_memory_entry(entry)
        return self.revalidator.revalidate(
            experience=experience,
            current_env=current_env,
            new_evidence=new_evidence or [],
            backend=self.backend,
        )

    # ------------------------------------------------------------------
    # Supersession & Conflicts
    # ------------------------------------------------------------------

    def supersede(
        self,
        old_experience_id: str,
        new_experience_id: str,
        reason: str,
    ) -> None:
        """Supersede an old experience with a new one.

        The old experience remains available for audit but is not
        normally injected as current guidance.

        Args:
            old_experience_id: ID of the experience being superseded.
            new_experience_id: ID of the superseding experience.
            reason: Human-readable reason for supersession.
        """
        old_entry = self.backend.get_by_id(old_experience_id)
        new_entry = self.backend.get_by_id(new_experience_id)
        if old_entry is None or new_entry is None:
            logger.warning(
                f"Cannot supersede: old={old_experience_id} "
                f"new={new_experience_id} — entry not found"
            )
            return

        old_exp = StructuredExperience.from_memory_entry(old_entry)
        new_exp = StructuredExperience.from_memory_entry(new_entry)
        self.conflicts.supersede(old_exp, new_exp, self.backend, reason)

    def get_conflicts(
        self,
        experience_id: str,
    ) -> List[ConflictRecord]:
        """Detect conflicts for a given experience.

        Args:
            experience_id: ID of the experience to check.

        Returns:
            List of detected conflicts.
        """
        entry = self.backend.get_by_id(experience_id)
        if entry is None:
            return []

        experience = StructuredExperience.from_memory_entry(entry)
        return self.conflicts.detect_conflicts(experience, self.backend)
