"""
Content Studio Data Models.

Defines the core data structures for projects, scenes, timelines, and
workflow states used throughout the Content Studio pipeline.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class WorkflowState(str, Enum):
    """Pipeline execution state."""
    PENDING = "pending"
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"


class OutputType(str, Enum):
    """Desired output format."""
    PPTX = "pptx"
    VIDEO = "video"


@dataclass
class Scene:
    """A single scene in the content timeline.

    Each scene has narration text, a visual description, and timing data.
    After voice generation, ``audio_path`` and ``audio_duration_sec`` are populated.
    """
    scene_id: str = ""
    title: str = ""
    narration_text: str = ""
    visual_description: str = ""
    duration_sec: float = 5.0
    audio_path: Optional[str] = None
    audio_duration_sec: Optional[float] = None
    visual_ref: Optional[str] = None
    bullet_points: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.scene_id:
            self.scene_id = f"scene_{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "title": self.title,
            "narration_text": self.narration_text,
            "visual_description": self.visual_description,
            "duration_sec": self.duration_sec,
            "audio_path": self.audio_path,
            "audio_duration_sec": self.audio_duration_sec,
            "visual_ref": self.visual_ref,
            "bullet_points": self.bullet_points,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        return cls(
            scene_id=d.get("scene_id", ""),
            title=d.get("title", ""),
            narration_text=d.get("narration_text", ""),
            visual_description=d.get("visual_description", ""),
            duration_sec=float(d.get("duration_sec", 5.0)),
            audio_path=d.get("audio_path"),
            audio_duration_sec=d.get("audio_duration_sec"),
            visual_ref=d.get("visual_ref"),
            bullet_points=d.get("bullet_points", []),
        )


@dataclass
class Timeline:
    """Synchronized scene timeline with audio alignment metadata."""
    scenes: List[Scene] = field(default_factory=list)
    total_duration_sec: float = 0.0
    sync_status: str = "unsynced"  # "synced" | "partial" | "unsynced"

    def to_dict(self) -> dict:
        return {
            "scenes": [s.to_dict() for s in self.scenes],
            "total_duration_sec": self.total_duration_sec,
            "sync_status": self.sync_status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Timeline":
        return cls(
            scenes=[Scene.from_dict(s) for s in d.get("scenes", [])],
            total_duration_sec=float(d.get("total_duration_sec", 0.0)),
            sync_status=d.get("sync_status", "unsynced"),
        )


@dataclass
class StepResult:
    """Result of a single pipeline step."""
    step_name: str
    status: str  # "success" | "failed" | "skipped" | "mock"
    is_mock: bool = False
    duration_ms: float = 0.0
    provider_request_id: str = ""
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class Project:
    """A Content Studio project representing a single content creation workflow.

    Tracks the full lifecycle from input through generation, localization,
    voice synthesis, synchronization, and export.
    """
    project_id: str = ""
    name: str = ""
    figma_input: str = ""            # URL or description
    language: str = "en"             # ISO 639-1 code
    output_type: str = "pptx"        # "pptx" | "video"
    state: WorkflowState = WorkflowState.PENDING
    created_at: str = ""
    updated_at: str = ""

    # --- Generated content ---
    design_context: Optional[Dict[str, Any]] = None
    script: Optional[str] = None
    scenes: List[Scene] = field(default_factory=list)
    timeline: Optional[Timeline] = None

    # --- Tracking ---
    step_results: List[StepResult] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)  # name → path
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    # --- CogniCore ---
    cognicore_experience_id: Optional[str] = None
    prior_experiences: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.project_id:
            self.project_id = f"proj_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "figma_input": self.figma_input,
            "language": self.language,
            "output_type": self.output_type,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "design_context": self.design_context,
            "script": self.script,
            "scenes": [s.to_dict() for s in self.scenes],
            "timeline": self.timeline.to_dict() if self.timeline else None,
            "step_results": [
                {
                    "step_name": sr.step_name,
                    "status": sr.status,
                    "is_mock": sr.is_mock,
                    "duration_ms": sr.duration_ms,
                    "provider_request_id": sr.provider_request_id,
                    "error": sr.error,
                    "timestamp": sr.timestamp,
                }
                for sr in self.step_results
            ],
            "artifacts": self.artifacts,
            "metadata": self.metadata,
            "error": self.error,
            "cognicore_experience_id": self.cognicore_experience_id,
            "prior_experiences": self.prior_experiences,
        }
