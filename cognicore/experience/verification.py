import logging
from dataclasses import dataclass
from typing import List

from cognicore.experience.schema import (
    StructuredExperience,
    EvidenceRecord,
    VerificationStatus,
)
from cognicore.memory.base import MemoryBackend, MemoryState

logger = logging.getLogger('cognicore.experience')

@dataclass
class VerificationResult:
    """Result of an evidence verification or transferability check."""
    passed: bool
    status: str
    evidence: List[EvidenceRecord]
    reason: str
    blockers: List[str]

class VerificationGate:
    """
    The most critical component for experience validation.
    
    This gate is responsible for validating pre-collected evidence.
    Security Model: The gate validates evidence, it does NOT execute commands. 
    The runtime/agent is responsible for running tests and collecting evidence.
    """

    def verify(self, experience: StructuredExperience, evidence: List[EvidenceRecord]) -> VerificationResult:
        """
        Validates the provided evidence records.

        Args:
            experience: The experience being verified.
            evidence: The list of evidence records collected by the agent.

        Returns:
            A VerificationResult indicating success or failure with specific blockers.
        """
        if not evidence:
            return VerificationResult(
                passed=False,
                status=VerificationStatus.CANDIDATE.value,
                evidence=[],
                reason="No evidence provided",
                blockers=["No evidence provided"]
            )

        blockers = []
        for rec in evidence:
            if not rec.command:
                blockers.append(f"Missing command in evidence record: {rec}")
            if rec.exit_code != 0:
                blockers.append(f"Non-zero exit code ({rec.exit_code}) in evidence record: {rec}")
            if not rec.timestamp:
                blockers.append(f"Missing timestamp in evidence record: {rec}")

        if blockers:
            return VerificationResult(
                passed=False,
                status=VerificationStatus.CANDIDATE.value,
                evidence=evidence,
                reason="Evidence validation failed",
                blockers=blockers
            )

        return VerificationResult(
            passed=True,
            status=VerificationStatus.VERIFIED.value,
            evidence=evidence,
            reason="All evidence valid",
            blockers=[]
        )

    def promote(self, experience: StructuredExperience, evidence: List[EvidenceRecord], backend: MemoryBackend) -> StructuredExperience:
        """
        Promotes an experience to VERIFIED state if the evidence passes validation.

        After promotion, the full entry is re-stored so that the updated
        metadata (content_hash, verification_evidence) persists in the backend.

        Args:
            experience: The experience to promote.
            evidence: The evidence records to validate.
            backend: The memory backend to update upon success.

        Returns:
            The potentially updated experience.
        """
        result = self.verify(experience, evidence)
        if not result.passed:
            logger.warning(f"Verification failed for experience {experience.experience_id}. Blockers: {result.blockers}")
            return experience

        experience.verification_status = VerificationStatus.VERIFIED.value
        experience.verification_evidence = result.evidence
        experience.confidence = max(experience.confidence, 0.8)
        experience.content_hash = experience.compute_content_hash()

        # Update state and confidence via the update whitelist
        backend.update(
            experience.experience_id,
            state=MemoryState.VERIFIED.value,
            confidence=experience.confidence,
        )

        # Also delete and re-store to persist the updated metadata
        # (content_hash, verification_evidence payload)
        old_id = experience.experience_id
        try:
            backend.delete(old_id)
            new_entry = experience.to_memory_entry()
            new_entry.entry_id = old_id
            new_id = backend.store(new_entry)
            experience.experience_id = str(new_id)
        except Exception as e:
            logger.warning(f"Failed to re-store experience {old_id} after promotion: {e}")

        logger.info(f"Promoted experience {experience.experience_id} to VERIFIED.")
        
        return experience

    def check_transferable(
        self,
        experience: StructuredExperience,
        env_compatible: bool = True,
        provenance_intact: bool = True,
        no_conflict: bool = True,
        not_superseded: bool = True
    ) -> VerificationResult:
        """
        Checks if a verified experience is safe to transfer.

        Args:
            experience: The experience to check.
            env_compatible: Flag indicating environment compatibility.
            provenance_intact: Flag indicating if provenance is intact.
            no_conflict: Flag indicating no conflicts exist.
            not_superseded: Flag indicating the experience is not superseded.

        Returns:
            A VerificationResult indicating if it is transferable.
        """
        blockers = []
        
        valid_states = {
            VerificationStatus.VERIFIED.value,
            VerificationStatus.PROMOTED.value,
            VerificationStatus.TRANSFERABLE.value
        }
        
        if experience.verification_status not in valid_states:
            blockers.append(f"Experience status must be at least VERIFIED, found: {experience.verification_status}")

        if not env_compatible:
            blockers.append("Environment is not compatible")
        if not provenance_intact:
            blockers.append("Provenance is not intact")
        if not no_conflict:
            blockers.append("Conflict detected")
        if not not_superseded:
            blockers.append("Experience is superseded")

        if blockers:
            return VerificationResult(
                passed=False,
                status=experience.verification_status,
                evidence=experience.verification_evidence,
                reason="Transferability criteria not met",
                blockers=blockers
            )

        return VerificationResult(
            passed=True,
            status=VerificationStatus.TRANSFERABLE.value,
            evidence=experience.verification_evidence,
            reason="All transferable criteria met",
            blockers=[]
        )

    def promote_to_transferable(
        self,
        experience: StructuredExperience,
        backend: MemoryBackend,
        env_compatible: bool,
        provenance_intact: bool,
        no_conflict: bool,
        not_superseded: bool
    ) -> StructuredExperience:
        """
        Promotes an experience to TRANSFERABLE state if it passes transferability checks.

        Args:
            experience: The experience to promote.
            backend: The memory backend to update.
            env_compatible: Flag indicating environment compatibility.
            provenance_intact: Flag indicating if provenance is intact.
            no_conflict: Flag indicating no conflicts exist.
            not_superseded: Flag indicating the experience is not superseded.

        Returns:
            The potentially updated experience.
        """
        result = self.check_transferable(
            experience=experience,
            env_compatible=env_compatible,
            provenance_intact=provenance_intact,
            no_conflict=no_conflict,
            not_superseded=not_superseded
        )
        
        if result.passed:
            backend.update(experience.experience_id, state=MemoryState.TRANSFERABLE.value)
            experience.verification_status = VerificationStatus.TRANSFERABLE.value

        return experience
