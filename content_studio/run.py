"""
Content Studio — Entry Point.

Start the Content Studio server:
    python -m content_studio.run
"""

import logging
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    """Launch the Content Studio server."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy loggers
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from content_studio.config import load_config
    from content_studio.app import create_app

    config = load_config()
    app = create_app(config)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print()
    print("=" * 62)
    print("  AI Content Studio - CogniCore-Powered")
    print("=" * 62)
    print(f"  Dashboard : http://{config.HOST}:{config.PORT}")
    print(f"  API Docs  : http://{config.HOST}:{config.PORT}/docs")
    print(f"  Mock Mode : {'ON' if config.MOCK_MODE else 'OFF'}")
    print(f"  Database  : {config.DB_PATH}")
    print()
    status = config.connector_status()
    for name, state in status.items():
        icon = "[+]" if "live" in state else "[-]"
        print(f"  {icon} {name:<14}: {state}")
    print()
    print("=" * 62)
    print()

    try:
        import uvicorn
        uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
    except ImportError:
        print("ERROR: uvicorn is required. Install with: pip install uvicorn")
        sys.exit(1)


if __name__ == "__main__":
    main()
