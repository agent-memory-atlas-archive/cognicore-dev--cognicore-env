"""Old module paths from before the restructure must keep importing.

Each one must resolve to the same module object as its new path, so
``isinstance`` checks and ``mock.patch("old.path.X")`` keep working.
"""
import importlib

import pytest

from cognicore._compat import MOVED_MODULES


@pytest.mark.parametrize("old, new", sorted(MOVED_MODULES.items()))
def test_old_path_is_new_module(old, new):
    try:
        new_mod = importlib.import_module(new)
    except ImportError as e:
        pytest.skip(f"{new} needs an optional dependency: {e}")
    assert importlib.import_module(old) is new_mod
