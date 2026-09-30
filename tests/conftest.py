"""Repo test configuration.

Registers the ``--seam-mutation`` flag used by the verifier-defeat
vector (``tests/test_mem0_bridge.py::TestVerifierDefeatVector``).  The
flag is never set by normal runs or CI jobs; it is passed only to the
deliberate fault-injection subprocess that proves the suite goes red
when the reachability guarantee is defeated at the recall seam.
"""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--seam-mutation",
        action="store_true",
        default=False,
        help=(
            "Defeat reachability at the recall seam for this run "
            "(fault injection for the verifier-defeat vector; see "
            "tests/seam_mutation.py). Never use in normal CI."
        ),
    )


def pytest_configure(config):
    if config.getoption("--seam-mutation"):
        from tests.seam_mutation import apply_bright_recall_mutation

        apply_bright_recall_mutation()
