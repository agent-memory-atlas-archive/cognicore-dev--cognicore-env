"""
CogniCore Memory Integration Layer.

Stores conversation history, workflow events, and structured experiences
using the existing CogniCore ExperienceManager and SQLiteMemoryBackend.
"""

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

from content_studio.config import StudioConfig

logger = logging.getLogger("content_studio.memory")


class CogniCoreLayer:
    """CogniCore memory integration for the Content Studio.

    Handles:
    - Conversation storage (each turn as a MemoryEntry)
    - Workflow event tracking (each pipeline step)
    - Structured experience recording (on completion)
    - Experience retrieval (before new workflows)
    """

    def __init__(self, config: StudioConfig) -> None:
        from cognicore.memory.sqlite_backend import SQLiteMemoryBackend
        from cognicore.fabric.registry import get_fabric
        from cognicore.experience.manager import ExperienceManager

        self.config = config
        self.backend = SQLiteMemoryBackend(config.DB_PATH)
        self.fabric = get_fabric(self.backend)
        self.experience_manager = ExperienceManager(self.backend)
        logger.info(f"CogniCoreLayer initialized (db={config.DB_PATH})")

    # ------------------------------------------------------------------
    # Conversation storage
    # ------------------------------------------------------------------

    def store_conversation(self, project_id: str, role: str, content: str) -> None:
        """Store a single conversation turn as a MemoryEntry."""
        from cognicore.memory.base import MemoryEntry, MemoryScope

        entry = MemoryEntry(
            text=f"[{role}] {content}",
            category="content_studio_conversation",
            memory_type="episodic",
            confidence=1.0,
            scope=MemoryScope.GLOBAL,
            metadata={
                "project_id": project_id,
                "role": role,
                "timestamp": time.time(),
            },
        )
        self.backend.store(entry)

    # ------------------------------------------------------------------
    # Workflow event tracking
    # ------------------------------------------------------------------

    def store_workflow_event(
        self, project_id: str, step_name: str, status: str, data: dict
    ) -> None:
        """Store a pipeline step event."""
        from cognicore.memory.base import MemoryEntry, MemoryScope

        entry = MemoryEntry(
            text=f"Workflow step '{step_name}': {status}",
            category="content_studio_event",
            memory_type="episodic",
            confidence=1.0,
            scope=MemoryScope.GLOBAL,
            metadata={
                "project_id": project_id,
                "step_name": step_name,
                "status": status,
                "data": data,
                "timestamp": time.time(),
            },
        )
        self.backend.store(entry)

    # ------------------------------------------------------------------
    # Experience recording
    # ------------------------------------------------------------------

    def record_experience(self, project) -> Optional[str]:
        """Create a StructuredExperience from a completed project.

        Args:
            project: A Project instance (from content_studio.models).

        Returns:
            The experience_id if recorded, else None.
        """
        from cognicore.experience.schema import (
            StructuredExperience,
            Attempt,
            AttemptOutcome,
        )

        attempts = []
        for sr in getattr(project, "step_results", []):
            outcome = (
                AttemptOutcome.SUCCESS.value
                if sr.status in ("success", "mock")
                else AttemptOutcome.FAILURE.value
            )
            attempts.append(
                Attempt(
                    approach=sr.step_name,
                    outcome=outcome,
                    reason=sr.error or "OK",
                    evidence=f"duration_ms={sr.duration_ms:.0f}",
                )
            )

        state_val = project.state.value if hasattr(project.state, "value") else str(project.state)

        exp = StructuredExperience(
            task="content_studio_workflow",
            problem=f"Generate {project.output_type} from: {project.figma_input[:100]}",
            attempts=attempts,
            solution=(project.script or "")[:300],
            why_it_worked=(
                "Full pipeline completed successfully"
                if state_val in ("completed", "needs_review")
                else "Pipeline failed"
            ),
            verification_status=(
                "verified" if state_val == "completed" else "candidate"
            ),
            source_agent="content_studio",
            confidence=0.9 if state_val == "completed" else 0.4,
        )

        try:
            exp_id = self.experience_manager.record(exp)
            logger.info(f"Recorded experience {exp_id} for project {project.project_id}")
            project.cognicore_experience_id = str(exp_id)
            return str(exp_id)
        except Exception as e:
            logger.error(f"Failed to record experience: {e}")
            return None

    # ------------------------------------------------------------------
    # Experience retrieval
    # ------------------------------------------------------------------

    def retrieve_experiences(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieve relevant past experiences.

        Returns a list of dicts with task, solution, confidence, and
        verification_status for display in the dashboard.
        """
        try:
            result = self.experience_manager.retrieve(
                query=query,
                include_failures=True,
                require_verified=False,
                top_k=top_k,
            )
            out = []
            for exp in result.experiences:
                out.append({
                    "task": exp.task,
                    "solution": exp.solution,
                    "confidence": exp.confidence,
                    "verification_status": exp.verification_status,
                })
            for fail in result.failures:
                out.append({
                    "task": fail.task,
                    "solution": f"FAILURE: {fail.problem}",
                    "confidence": fail.confidence,
                    "verification_status": "failure_warning",
                })
            return out
        except Exception as e:
            logger.warning(f"Experience retrieval failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Conversation retrieval
    # ------------------------------------------------------------------

    def get_conversation(self, project_id: str) -> list:
        """Retrieve all conversation entries for a project."""
        try:
            entries = self.backend.get_by_category(
                "content_studio_conversation", top_k=100
            )
            return [
                e for e in entries
                if (getattr(e, "metadata", None) or {}).get("project_id") == project_id
            ]
        except Exception as e:
            logger.warning(f"Conversation retrieval failed: {e}")
            return []
