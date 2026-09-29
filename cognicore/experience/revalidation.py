import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from cognicore.experience.schema import (
    StructuredExperience,
    EvidenceRecord,
    EnvironmentContext,
    VerificationStatus,
)
from cognicore.experience.verification import VerificationGate, VerificationResult
from cognicore.experience.compatibility import EnvironmentChecker, CompatibilityResult
from cognicore.memory.base import MemoryBackend, MemoryState

logger = logging.getLogger('cognicore.experience')

@dataclass
class StalenessResult:
    """Result of an experience staleness check."""
    stale: bool
    reasons: List[str]
    compatibility: Optional[CompatibilityResult]
    age_days: float


@dataclass
class RevalidationResult:
    """Result of an experience re-validation process."""
    valid: bool
    new_status: str
    staleness: Optional[StalenessResult]
    verification: Optional[VerificationResult]
    reason: str


class RevalidationEngine:
    """
    Engine for checking staleness and re-validating experiences.
    
    Determines if an experience is stale based on age and environment changes.
    Can re-validate stale experiences against new evidence.
    """

    def __init__(
        self,
        gate: Optional[VerificationGate] = None,
        checker: Optional[EnvironmentChecker] = None,
        max_age_days: float = 90.0,
    ) -> None:
        """
        Initialize the RevalidationEngine.

        Args:
            gate: Gate to verify new evidence. Defaults to VerificationGate.
            checker: Checker to evaluate environment compatibility. Defaults to EnvironmentChecker.
            max_age_days: Maximum age of an experience in days before it is considered stale.
        """
        self.gate = gate if gate is not None else VerificationGate()
        self.checker = checker if checker is not None else EnvironmentChecker()
        self.max_age_days = max_age_days

    def check_staleness(self, experience: StructuredExperience, current_env: EnvironmentContext) -> StalenessResult:
        """
        Check if an experience is stale relative to the current environment and its age.

        Args:
            experience: The experience to check.
            current_env: The current environment context.

        Returns:
            A StalenessResult indicating if the experience is stale and why.
        """
        age_days = 0.0
        if experience.created_at:
            try:
                # Try to parse the ISO string
                created_dt = datetime.fromisoformat(experience.created_at)
                now_dt = datetime.now(timezone.utc)
                age_days = (now_dt - created_dt).total_seconds() / (24 * 3600)
            except (ValueError, TypeError):
                logger.warning(f"Failed to parse created_at for experience {experience.experience_id}: {experience.created_at}")

        reasons: List[str] = []

        if age_days > self.max_age_days:
            reasons.append(f"Experience is older than {self.max_age_days} days")

        comp_result = self.checker.check(experience.environment, current_env)
        
        if not comp_result.compatible:
            reasons.extend(comp_result.blockers)
            
        if comp_result.warnings and age_days > 30.0:
            reasons.append("Environment has minor changes and experience is aging")

        return StalenessResult(
            stale=len(reasons) > 0,
            reasons=reasons,
            compatibility=comp_result,
            age_days=age_days
        )

    def revalidate(
        self,
        experience: StructuredExperience,
        current_env: EnvironmentContext,
        new_evidence: List[EvidenceRecord],
        backend: MemoryBackend,
    ) -> RevalidationResult:
        """
        Re-validate an experience, potentially updating its status and environment.

        Args:
            experience: The experience to re-validate.
            current_env: The current environment context.
            new_evidence: Any newly gathered evidence to support re-validation.
            backend: The memory backend to update state in.

        Returns:
            A RevalidationResult indicating the new validation state.
        """
        staleness = self.check_staleness(experience, current_env)

        if not staleness.stale:
            return RevalidationResult(
                valid=True,
                new_status=experience.verification_status,
                staleness=staleness,
                verification=None,
                reason="Experience is not stale",
            )

        if staleness.stale and new_evidence:
            verification_result = self.gate.verify(experience, new_evidence)
            
            if verification_result.passed:
                # Verification passed, update experience and backend
                experience.environment = current_env
                experience.verification_status = VerificationStatus.VERIFIED.value
                experience.verification_evidence = new_evidence
                experience.content_hash = experience.compute_content_hash()
                
                backend.update(
                    experience.experience_id,
                    state=MemoryState.VERIFIED.value,
                    metadata={"experience": experience._to_payload_dict(), "content_hash": experience.content_hash}
                )
                
                return RevalidationResult(
                    valid=True,
                    new_status=VerificationStatus.VERIFIED.value,
                    staleness=staleness,
                    verification=verification_result,
                    reason="Re-validation passed with new evidence",
                )
            else:
                # Verification failed
                backend.update(
                    experience.experience_id,
                    state=MemoryState.ARCHIVED.value,
                    invalidated_reason=f"Failed re-validation: {', '.join(verification_result.blockers)}"
                )
                experience.verification_status = VerificationStatus.INVALID.value
                
                return RevalidationResult(
                    valid=False,
                    new_status=VerificationStatus.INVALID.value,
                    staleness=staleness,
                    verification=verification_result,
                    reason=f"Failed re-validation: {', '.join(verification_result.blockers)}",
                )

        # Stale but no new evidence provided
        return RevalidationResult(
            valid=False,
            new_status=experience.verification_status,
            staleness=staleness,
            verification=None,
            reason="Re-validation required but no new evidence provided",
        )

    def invalidate(self, experience: StructuredExperience, backend: MemoryBackend, reason: str) -> None:
        """
        Forcefully invalidate an experience.

        Args:
            experience: The experience to invalidate.
            backend: The memory backend.
            reason: Reason for invalidation.
        """
        backend.update(
            experience.experience_id,
            state=MemoryState.ARCHIVED.value,
            invalidated_reason=reason
        )
        experience.verification_status = VerificationStatus.INVALID.value
        logger.info(f"Invalidated experience {experience.experience_id}: {reason}")
