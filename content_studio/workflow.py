"""
Content Studio Workflow State Machine.

Manages project lifecycle transitions:
    PENDING → RUNNING → COMPLETED
                     ↘ FAILED
                     ↘ NEEDS_REVIEW
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from content_studio.models import Project, WorkflowState, StepResult

logger = logging.getLogger("content_studio.workflow")

# Valid state transitions
TRANSITIONS = {
    WorkflowState.PENDING: {WorkflowState.RUNNING},
    WorkflowState.RUNNING: {
        WorkflowState.COMPLETED,
        WorkflowState.FAILED,
        WorkflowState.NEEDS_REVIEW,
    },
    WorkflowState.FAILED: {WorkflowState.RUNNING},       # retry
    WorkflowState.NEEDS_REVIEW: {WorkflowState.RUNNING},  # re-run after review
    WorkflowState.COMPLETED: set(),                        # terminal
}


class WorkflowError(Exception):
    """Raised when a workflow transition is invalid."""


def transition(project: Project, new_state: WorkflowState, reason: str = "") -> None:
    """Transition a project to a new workflow state.

    Args:
        project: The project to transition.
        new_state: The target state.
        reason: Optional human-readable reason for the transition.

    Raises:
        WorkflowError: If the transition is not allowed.
    """
    allowed = TRANSITIONS.get(project.state, set())
    if new_state not in allowed:
        raise WorkflowError(
            f"Cannot transition from {project.state.value} to {new_state.value}. "
            f"Allowed: {[s.value for s in allowed]}"
        )
    old_state = project.state
    project.state = new_state
    project.updated_at = datetime.now(timezone.utc).isoformat()
    if new_state == WorkflowState.FAILED and reason:
        project.error = reason
    logger.info(
        f"Project {project.project_id}: {old_state.value} → {new_state.value}"
        + (f" ({reason})" if reason else "")
    )


def record_step(
    project: Project,
    step_name: str,
    status: str,
    is_mock: bool = False,
    duration_ms: float = 0.0,
    provider_request_id: str = "",
    error: Optional[str] = None,
    data: Optional[dict] = None,
) -> StepResult:
    """Record the result of a pipeline step on the project.

    Args:
        project: The project to record the step on.
        step_name: Name of the pipeline step (e.g., "figma_extract").
        status: Outcome ("success", "failed", "skipped", "mock").
        is_mock: Whether mock adapter was used.
        duration_ms: How long the step took.
        provider_request_id: External provider request ID for tracing.
        error: Error message if the step failed.
        data: Optional result data to attach.

    Returns:
        The recorded StepResult.
    """
    result = StepResult(
        step_name=step_name,
        status=status,
        is_mock=is_mock,
        duration_ms=duration_ms,
        provider_request_id=provider_request_id,
        error=error,
        data=data,
    )
    project.step_results.append(result)
    project.updated_at = datetime.now(timezone.utc).isoformat()
    logger.info(
        f"  Step '{step_name}': {status}"
        + (" [MOCK]" if is_mock else "")
        + (f" — {error}" if error else "")
    )
    return result


def should_flag_for_review(project: Project) -> bool:
    """Check whether the project should be flagged for human review.

    Returns True when mock adapters were used, timeline sync is partial,
    or any step encountered a non-fatal issue.
    """
    has_mock = any(sr.is_mock for sr in project.step_results)
    partial_sync = (
        project.timeline is not None
        and project.timeline.sync_status == "partial"
    )
    return has_mock or partial_sync
