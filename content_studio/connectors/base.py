import logging
import time
import random
from typing import Callable, Any
from content_studio.config import StudioConfig

class ConnectorBase:
    """Base class for all AI Content Studio connectors."""

    def __init__(self, config: StudioConfig, force_mock: bool = False):
        """Initialize the connector with a StudioConfig."""
        self.config = config
        self.force_mock = force_mock
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    def is_mock(self) -> bool:
        """Return True if running in mock mode."""
        return self.force_mock or getattr(self.config, 'MOCK_MODE', False)

    def retry_with_backoff(self, fn: Callable, max_retries: int = 3) -> Any:
        """Execute a function with exponential backoff on failure (1s, 2s, 4s)."""
        delays = [1, 2, 4]
        for attempt in range(max_retries):
            try:
                return fn()
            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    self.logger.error("Max retries reached. Raising exception.")
                    raise
                time.sleep(delays[attempt] if attempt < len(delays) else 4)

    def _label(self, text: str) -> str:
        """Prepend [MOCK] or [LIVE] to the given text."""
        prefix = "[MOCK]" if self.is_mock else "[LIVE]"
        return f"{prefix} {text}"
