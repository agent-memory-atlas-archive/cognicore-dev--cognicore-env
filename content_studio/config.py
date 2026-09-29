"""
Content Studio Configuration.

Loads all API keys from environment variables, validates credentials at startup,
and provides mock-mode detection when keys are absent.
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("content_studio.config")

# ---------------------------------------------------------------------------
# Supported languages for Sarvam AI localization
# ---------------------------------------------------------------------------
SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "mr": "Marathi",
    "bn": "Bengali",
    "gu": "Gujarati",
    "pa": "Punjabi",
}


@dataclass
class StudioConfig:
    """Central configuration for the Content Studio.

    All API keys are read from environment variables at construction time.
    Set ``MOCK_MODE=true`` to run the entire pipeline without paid APIs.
    """

    # --- API Keys (never hardcoded) ---
    FIGMA_ACCESS_TOKEN: str = ""
    GROQ_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""
    SARVAM_API_KEY: str = ""
    CANVA_API_KEY: str = ""
    CANVA_CLIENT_ID: str = ""
    CANVA_CLIENT_SECRET: str = ""
    CANVA_REDIRECT_URI: str = "http://127.0.0.1:8501/api/auth/canva/callback"
    CANVA_ACCESS_TOKEN: str = ""

    # --- LLM provider ---
    LLM_PROVIDER: str = "groq"  # "groq" | "openai" | "sarvam"
    LLM_MODEL: str = "qwen/qwen3.8-27b"
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"

    # --- Modes ---
    MOCK_MODE: bool = False
    DRY_RUN: bool = False

    # --- Paths ---
    DB_PATH: str = ""
    OUTPUT_DIR: str = ""

    # --- Server ---
    HOST: str = "127.0.0.1"
    PORT: int = 8501

    def __post_init__(self) -> None:
        base = Path(__file__).parent.parent
        if not self.DB_PATH:
            self.DB_PATH = str(base / "cognicore_content_studio.db")
        if not self.OUTPUT_DIR:
            self.OUTPUT_DIR = str(base / "content_studio" / "output")

    # ------------------------------------------------------------------
    # Connector status helpers
    # ------------------------------------------------------------------

    @property
    def figma_available(self) -> bool:
        return bool(self.FIGMA_ACCESS_TOKEN) and not self.MOCK_MODE

    @property
    def llm_available(self) -> bool:
        return bool(self.GROQ_API_KEY) and not self.MOCK_MODE

    @property
    def elevenlabs_available(self) -> bool:
        return bool(self.ELEVENLABS_API_KEY) and not self.MOCK_MODE

    @property
    def sarvam_available(self) -> bool:
        return bool(self.SARVAM_API_KEY) and not self.MOCK_MODE

    @property
    def canva_available(self) -> bool:
        return bool(self.CANVA_ACCESS_TOKEN) and not self.MOCK_MODE

    def connector_status(self) -> dict:
        """Return a dict showing live/mock status of each connector."""
        canva_st = "live" if self.canva_available else (
            "ready to connect (OAuth configured)" if bool(self.CANVA_CLIENT_ID) else "mock (requires OAuth app approval)"
        )
        return {
            "figma": "live" if self.figma_available else "mock",
            "llm": "live" if self.llm_available else "mock",
            "elevenlabs": "live" if self.elevenlabs_available else "mock",
            "sarvam": "live" if self.sarvam_available else "mock",
            "canva": canva_st,
            "cognicore": "live (built-in)",
        }



def load_config() -> StudioConfig:
    """Load configuration from environment variables.

    Reads from ``os.environ`` and optionally from a ``.env`` file if
    ``python-dotenv`` is installed.  Returns a fully-populated
    ``StudioConfig`` with clear log messages about what is available.
    """
    # Try loading .env file
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass

    mock_mode = os.environ.get("MOCK_MODE", "").lower() in ("true", "1", "yes")

    config = StudioConfig(
        FIGMA_ACCESS_TOKEN=os.environ.get("FIGMA_ACCESS_TOKEN", ""),
        GROQ_API_KEY=os.environ.get("GROQ_API_KEY", ""),
        ELEVENLABS_API_KEY=os.environ.get("ELEVENLABS_API_KEY", ""),
        SARVAM_API_KEY=os.environ.get("SARVAM_API_KEY", ""),
        CANVA_API_KEY=os.environ.get("CANVA_API_KEY", ""),
        CANVA_CLIENT_ID=os.environ.get("CANVA_CLIENT_ID", ""),
        CANVA_CLIENT_SECRET=os.environ.get("CANVA_CLIENT_SECRET", ""),
        CANVA_REDIRECT_URI=os.environ.get("CANVA_REDIRECT_URI", "http://127.0.0.1:8501/api/auth/canva/callback"),
        CANVA_ACCESS_TOKEN=os.environ.get("CANVA_ACCESS_TOKEN", ""),
        LLM_PROVIDER=os.environ.get("LLM_PROVIDER", "groq"),
        LLM_MODEL=os.environ.get("LLM_MODEL", "qwen/qwen3.8-27b"),
        LLM_BASE_URL=os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
        MOCK_MODE=mock_mode,
        DRY_RUN=os.environ.get("DRY_RUN", "").lower() in ("true", "1", "yes"),
        DB_PATH=os.environ.get("STUDIO_DB_PATH", ""),
        OUTPUT_DIR=os.environ.get("STUDIO_OUTPUT_DIR", ""),
        HOST=os.environ.get("STUDIO_HOST", "127.0.0.1"),
        PORT=int(os.environ.get("STUDIO_PORT", "8501")),
    )

    # Auto-detect mock mode if no API keys are set
    has_any_key = any([
        config.FIGMA_ACCESS_TOKEN,
        config.GROQ_API_KEY,
        config.ELEVENLABS_API_KEY,
        config.SARVAM_API_KEY,
    ])
    if not has_any_key and not mock_mode:
        config.MOCK_MODE = True
        logger.warning(
            "No API keys found in environment — auto-enabling MOCK_MODE. "
            "Set API keys in .env or environment to use live connectors."
        )

    # Log connector status
    status = config.connector_status()
    logger.info("Content Studio configuration loaded:")
    for name, state in status.items():
        logger.info(f"  {name:<14}: {state}")

    return config
