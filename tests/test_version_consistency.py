"""The version must be the same everywhere it is written down.

PyPI takes it from pyproject.toml, users see cognicore.__version__, and the
MCP registry reads server.json. 0.10.4 shipped with __version__ still saying
0.10.3, so they are checked together here.
"""
import json
import re
from pathlib import Path

import cognicore

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE).group(1)


def test_package_version_matches_pyproject():
    assert cognicore.__version__ == _pyproject_version()


def test_mcp_registry_version_matches_pyproject():
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert server["version"] == _pyproject_version()
