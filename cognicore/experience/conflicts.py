import logging
from dataclasses import dataclass
from typing import List

from cognicore.experience.schema import (
    StructuredExperience,
    VerificationStatus,
    AttemptOutcome,
)
from cognicore.memory.base import MemoryBackend, MemoryState, MemoryType

logger = logging.getLogger('cognicore.experience')


@dataclass
class ConflictRecord:
    """Represents a conflict between two structured experiences."""
    experience_a_id: str
    experience_b_id: str
    conflict_type: str
    description: str
    severity: str


class ConflictResolver:
    """Resolves conflicts between structured experiences."""

    def detect_conflicts(self, experience: StructuredExperience, backend: MemoryBackend) -> List[ConflictRecord]:
        """
        Detect conflicts between the given experience and existing experiences in the backend.

        Args:
            experience: The new experience to check for conflicts.
            backend: The memory backend to search.

        Returns:
            A list of detected ConflictRecords.
        """
        conflicts: List[ConflictRecord] = []
        if not experience.task:
            return conflicts

        search_results = backend.search(experience.task, top_k=20)
        if not search_results:
            return conflicts

        for result in search_results:
            entry = result.entry
            if entry.memory_type != MemoryType.EXPERIENCE.value:
                continue

            if getattr(entry, "invalidated_by", None) is not None or entry.state == MemoryState.ARCHIVED.value:
                continue

            if entry.entry_id == experience.experience_id:
                continue

            try:
                candidate = StructuredExperience.from_memory_entry(entry)
            except Exception as e:
                logger.warning(f"Failed to deserialize candidate experience {entry.entry_id}: {e}")
                continue

            if candidate.experience_id == experience.experience_id:
                continue

            # a. Contradictory outcome
            has_contradiction = False
            for att_a in experience.attempts:
                for att_b in candidate.attempts:
                    if (att_a.approach == att_b.approach and 
                        att_a.outcome != AttemptOutcome.UNKNOWN.value and 
                        att_b.outcome != AttemptOutcome.UNKNOWN.value and 
                        att_a.outcome != att_b.outcome):
                        has_contradiction = True
                        break
                if has_contradiction:
                    break

            if has_contradiction:
                conflicts.append(ConflictRecord(
                    experience_a_id=experience.experience_id,
                    experience_b_id=candidate.experience_id,
                    conflict_type='contradictory_outcome',
                    description=f"Contradictory outcomes for same approach between {experience.experience_id} and {candidate.experience_id}",
                    severity='high'
                ))
                continue

            # b. Same task different solution
            if experience.task == candidate.task and experience.solution != candidate.solution:
                is_exp_verified = experience.verification_status in (
                    VerificationStatus.VERIFIED.value,
                    VerificationStatus.TRANSFERABLE.value,
                    VerificationStatus.PROMOTED.value
                )
                is_cand_verified = candidate.verification_status in (
                    VerificationStatus.VERIFIED.value,
                    VerificationStatus.TRANSFERABLE.value,
                    VerificationStatus.PROMOTED.value
                )

                if is_exp_verified and is_cand_verified:
                    conflicts.append(ConflictRecord(
                        experience_a_id=experience.experience_id,
                        experience_b_id=candidate.experience_id,
                        conflict_type='same_task_different_solution',
                        description=f"Same task but different verified solutions between {experience.experience_id} and {candidate.experience_id}",
                        severity='medium'
                    ))
                    continue

                # c. Supersession candidate
                conflicts.append(ConflictRecord(
                    experience_a_id=experience.experience_id,
                    experience_b_id=candidate.experience_id,
                    conflict_type='supersession_candidate',
                    description=f"Different solutions for same task between {experience.experience_id} and {candidate.experience_id}, possible supersession",
                    severity='low'
                ))

        return conflicts

    def supersede(self, old_exp: StructuredExperience, new_exp: StructuredExperience, backend: MemoryBackend, reason: str) -> None:
        """
        Supersede an old experience with a new one.

        Args:
            old_exp: The old experience to be superseded.
            new_exp: The new experience that supersedes the old one.
            backend: The memory backend to update.
            reason: The reason for supersession.
        """
        backend.update(old_exp.experience_id, invalidated_by=new_exp.experience_id, invalidated_reason=reason)
        backend.update(new_exp.experience_id, supersedes=old_exp.experience_id)
        logger.info(f"Experience {new_exp.experience_id} supersedes {old_exp.experience_id} (Reason: {reason})")

    def resolve_conflict(self, conflict: ConflictRecord, winner_id: str, loser_id: str, backend: MemoryBackend, reason: str = '') -> None:
        """
        Resolve a conflict by superseding the loser with the winner.

        Args:
            conflict: The conflict record being resolved.
            winner_id: The ID of the winning experience.
            loser_id: The ID of the losing experience.
            backend: The memory backend to update.
            reason: Optional reason for the resolution.
        """
        backend.update(loser_id, invalidated_by=winner_id, invalidated_reason=reason)
        backend.update(winner_id, supersedes=loser_id)
        logger.info(f"Resolved conflict {conflict.conflict_type}: {winner_id} won over {loser_id} (Reason: {reason})")
