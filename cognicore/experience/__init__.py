"""CogniCore Structured Validated Experience Memory.

Provides first-class experience capture, verification, transfer,
and re-validation for AI agent systems.

Usage::

    from cognicore.experience import ExperienceManager, StructuredExperience
    from cognicore.memory import SQLiteMemoryBackend

    backend = SQLiteMemoryBackend("experiences.db")
    manager = ExperienceManager(backend)

    exp = StructuredExperience(task="Fix JWT auth", ...)
    manager.record(exp)
    manager.verify(exp.experience_id, evidence=[...])
"""
from cognicore.experience.schema import (
    StructuredExperience,
    Attempt,
    AttemptOutcome,
    EvidenceRecord,
    EnvironmentContext,
    RepositoryContext,
    VerificationStatus,
)
from cognicore.experience.verification import VerificationGate, VerificationResult
from cognicore.experience.compatibility import (
    EnvironmentChecker,
    CompatibilityResult,
)
from cognicore.experience.conflicts import ConflictResolver, ConflictRecord
from cognicore.experience.retrieval import ExperienceRetriever, RetrievalResult
from cognicore.experience.revalidation import (
    RevalidationEngine,
    RevalidationResult,
    StalenessResult,
)
from cognicore.experience.manager import ExperienceManager, TransferResult

__all__ = [
    # Schema
    "StructuredExperience",
    "Attempt",
    "AttemptOutcome",
    "EvidenceRecord",
    "EnvironmentContext",
    "RepositoryContext",
    "VerificationStatus",
    # Verification
    "VerificationGate",
    "VerificationResult",
    # Compatibility
    "EnvironmentChecker",
    "CompatibilityResult",
    # Conflicts
    "ConflictResolver",
    "ConflictRecord",
    # Retrieval
    "ExperienceRetriever",
    "RetrievalResult",
    # Revalidation
    "RevalidationEngine",
    "RevalidationResult",
    "StalenessResult",
    # Manager
    "ExperienceManager",
    "TransferResult",
]
