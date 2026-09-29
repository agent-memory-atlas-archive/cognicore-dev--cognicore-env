"""
Demo 6: Structured Validated Experience — The Killer Scenario.

This demo shows the complete lifecycle:

  AGENT A discovers a JWT auth bug:
    Attempt 1 → change JWT expiry        → FAIL (wasn't root cause)
    Attempt 2 → change retry logic        → FAIL (race condition)
    Attempt 3 → fix refresh-token lifecycle → PASS (47 tests pass) → VERIFIED

  AGENT B starts fresh, same project, similar bug:
    CogniCore retrieves:
      ❌  Don't increase JWT expiry — Failed because ...
      ❌  Don't modify retry logic — Failed because ...
      ✅  Fix refresh-token lifecycle — Verified by 47 tests

  ENVIRONMENT CHANGE:
    Major dependency upgrade (pyjwt 2.x → 3.x)
    → Experience no longer automatically trusted
    → Re-validation required

No LLM calls. No hardcoded results. Uses real SQLiteMemoryBackend.
"""
import os
import sys
import tempfile

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from cognicore.experience import (
    ExperienceManager,
    StructuredExperience,
    Attempt,
    AttemptOutcome,
    EvidenceRecord,
    EnvironmentContext,
    RepositoryContext,
    VerificationStatus,
)
from cognicore.memory.sqlite_backend import SQLiteMemoryBackend


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

BLUE = "\033[94m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
CYAN = "\033[96m"


def section(title: str) -> None:
    print(f"\n{'═' * 70}")
    print(f"  {BOLD}{title}{RESET}")
    print(f"{'═' * 70}\n")


def step(msg: str) -> None:
    print(f"  {DIM}→{RESET} {msg}")


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {msg}")


def info(msg: str) -> None:
    print(f"  {CYAN}ℹ{RESET} {msg}")


# ─────────────────────────────────────────────────────────────────────
# Demo
# ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{BOLD}{'═' * 70}{RESET}")
    print(f"{BOLD}  CogniCore — Structured Validated Experience Memory{RESET}")
    print(f"{BOLD}  \"Agents don't share conversations. They share experience.\"{RESET}")
    print(f"{BOLD}{'═' * 70}{RESET}")

    # Set up two separate backends (two separate agents)
    tmpdir = tempfile.mkdtemp()
    try:
        db_a = os.path.join(tmpdir, "agent_a.db")
        db_b = os.path.join(tmpdir, "agent_b.db")
        backend_a = SQLiteMemoryBackend(db_a)
        backend_b = SQLiteMemoryBackend(db_b)

        manager_a = ExperienceManager(backend_a)
        manager_b = ExperienceManager(backend_b)

        # ═══════════════════════════════════════════════════════════════
        # SCENE 1: Agent A discovers the bug
        # ═══════════════════════════════════════════════════════════════

        section("SCENE 1 — Agent A: Discovering the JWT Auth Bug")

        experience = StructuredExperience(
            task="Fix JWT authentication failures",
            problem="Intermittent JWT auth failures in auth-service after deploy",
            attempts=[
                Attempt(
                    approach="Increase JWT expiration window from 15m to 60m",
                    outcome=AttemptOutcome.FAILURE.value,
                    reason="Timeout wasn't the root cause — tokens were being invalidated mid-session",
                    evidence="pytest tests/auth -> 3/47 failures (test_refresh, test_rotation, test_concurrent)",
                ),
                Attempt(
                    approach="Add retry logic to auth_middleware.py",
                    outcome=AttemptOutcome.FAILURE.value,
                    reason="Race condition: shared state between retries caused token collision",
                    evidence="pytest tests/auth -> 5/47 failures + race condition in logs",
                ),
                Attempt(
                    approach="Fix refresh-token lifecycle in token_manager.py",
                    outcome=AttemptOutcome.SUCCESS.value,
                    reason="Root cause: stale refresh tokens not invalidated on rotation",
                    evidence="pytest tests/auth -> 47/47 passed",
                ),
            ],
            solution="Fix refresh-token lifecycle in token_manager.py — invalidate old tokens on rotation",
            why_it_worked="The real issue was token rotation not cleaning up old refresh tokens",
            verification_method="pytest",
            verification_version="1",
            source_agent="claude-3.5-sonnet",
            source_session="session-jwt-fix-001",
            repository=RepositoryContext(
                repo_id="acme/auth-service",
                commit="a1b2c3d",
                branch="fix/jwt-auth",
                affected_files=["src/auth_middleware.py", "src/token_manager.py", "tests/auth/test_refresh.py"],
            ),
            environment=EnvironmentContext(
                python_version="3.11.4",
                os="linux",
                framework="FastAPI",
                framework_version="0.95.0",
                dependencies={
                    "pyjwt": "2.8.0",
                    "fastapi": "0.95.0",
                    "python-multipart": "0.0.6",
                    "uvicorn": "0.23.0",
                },
            ),
            confidence=0.5,
        )

        step("Agent A records 3 approaches (2 failed, 1 succeeded)")
        exp_id = manager_a.record(experience)
        ok(f"Experience recorded: {exp_id}")
        ok(f"Content hash: {experience.content_hash[:16]}...")
        info(f"2 failure entries stored separately as OBSERVED")

        # Verify with real evidence
        step("Agent A provides verification evidence")
        evidence = [
            EvidenceRecord(
                command="pytest tests/auth -v",
                exit_code=0,
                stdout_hash="e3b0c44298fc1c149afbf4c8996fb924",
                timestamp="2025-01-15T14:30:00+00:00",
                commit="a1b2c3d",
            ),
            EvidenceRecord(
                command="python -m mypy src/token_manager.py --strict",
                exit_code=0,
                stdout_hash="d41d8cd98f00b204e9800998ecf8427e",
                timestamp="2025-01-15T14:31:00+00:00",
                commit="a1b2c3d",
            ),
        ]
        result = manager_a.verify(exp_id, evidence)
        exp_id = getattr(result, '_promoted_id', exp_id)

        if result.passed:
            ok(f"Verification PASSED — promoted to VERIFIED")
            ok(f"Evidence: {len(evidence)} commands, all exit_code=0")
        else:
            fail(f"Verification failed: {result.blockers}")
            return

        # ═══════════════════════════════════════════════════════════════
        # SCENE 2: Agent B gets a similar bug — no conversation shared
        # ═══════════════════════════════════════════════════════════════

        section("SCENE 2 — Agent B: New Session, Similar Bug")

        step("Agent B has ZERO conversation history from Agent A")
        step("Agent B is working on the same project with a similar bug")

        # Transfer verified experiences from A to B
        step("CogniCore transfers verified experience + failure warnings")
        transfer = manager_a.transfer(
            source_backend=backend_a,
            target_backend=backend_b,
            query="JWT authentication failure auth-service",
            current_env=EnvironmentContext(
                python_version="3.11.4",
                framework="FastAPI",
                framework_version="0.95.0",
                dependencies={"pyjwt": "2.8.0", "fastapi": "0.95.0"},
            ),
        )

        print()
        info(f"Total candidates examined: {transfer.total_candidates}")
        ok(f"Experiences transferred: {len(transfer.transferred)}")
        ok(f"Failure warnings surfaced: {len(transfer.failures_surfaced)}")
        if transfer.blocked:
            warn(f"Blocked: {transfer.blocked}")

        # What Agent B now sees
        print(f"\n  {BOLD}What Agent B receives from CogniCore:{RESET}\n")

        for fail_exp in transfer.failures_surfaced:
            fail(f"{RED}Don't try:{RESET} {fail_exp.problem[:80]}")

        for exp in transfer.transferred:
            ok(f"{GREEN}Verified solution:{RESET} {exp.solution[:80]}")
            info(f"  Why it worked: {exp.why_it_worked[:80]}")
            info(f"  Verified by: {exp.verification_method} ({len(exp.verification_evidence)} evidence records)")
            info(f"  Source: {exp.source_agent} (session {exp.source_session})")

        # ═══════════════════════════════════════════════════════════════
        # SCENE 3: Environment changes — experience needs revalidation
        # ═══════════════════════════════════════════════════════════════

        section("SCENE 3 — Environment Change: PyJWT 2.x → 3.x")

        step("Major dependency upgrade detected")
        new_env = EnvironmentContext(
            python_version="3.12.0",
            os="linux",
            framework="FastAPI",
            framework_version="0.115.0",
            dependencies={
                "pyjwt": "3.0.0",        # MAJOR version change
                "fastapi": "0.115.0",
                "python-multipart": "0.0.12",
                "uvicorn": "0.30.0",
            },
        )

        # Revalidate the transferred experience
        for exp in transfer.transferred:
            reval = manager_b.revalidate(exp.experience_id, new_env)

            if not reval.valid:
                warn(f"Experience {exp.experience_id} is NO LONGER VALID")
                if reval.staleness and reval.staleness.stale:
                    for reason in reval.staleness.reasons:
                        warn(f"  {reason}")
                    if reval.staleness.compatibility:
                        for blocker in reval.staleness.compatibility.blockers:
                            fail(f"  BLOCKER: {blocker}")
                        for warning in reval.staleness.compatibility.warnings:
                            warn(f"  WARNING: {warning}")
                    info(f"Compatibility score: {reval.staleness.compatibility.score:.2f}")
                    info(f"Status: Re-validation required before trusting this experience")
                else:
                    fail(f"  Reason: {reval.reason}")
            else:
                ok(f"Experience {exp.experience_id} is still valid")

        # ═══════════════════════════════════════════════════════════════
        # SCENE 4: Provenance verification
        # ═══════════════════════════════════════════════════════════════

        section("SCENE 4 — Provenance & Integrity Check")

        step("Verifying content hash integrity")
        for exp in transfer.transferred:
            intact = exp.verify_hash()
            if intact:
                ok(f"Hash verified: {exp.content_hash[:16]}... → provenance intact")
            else:
                fail(f"Hash MISMATCH: experience may have been tampered with")

        # Demonstrate tampering detection
        step("Simulating a tampered experience")
        tampered = StructuredExperience(
            task=experience.task,
            problem=experience.problem,
            attempts=experience.attempts,
            solution="TAMPERED: just delete the auth code",  # tampered!
            why_it_worked=experience.why_it_worked,
            content_hash=experience.content_hash,  # old hash
        )
        if not tampered.verify_hash():
            ok(f"Tampering DETECTED — hash mismatch")
            info(f"Original hash: {experience.content_hash[:16]}...")
            info(f"Tampered hash: {tampered.compute_content_hash()[:16]}...")
        else:
            fail("Tampering NOT detected — this should not happen")

        # ═══════════════════════════════════════════════════════════════
        # Summary
        # ═══════════════════════════════════════════════════════════════

        section("SUMMARY")

        print(f"  {BOLD}Core principle:{RESET}")
        print(f"  {CYAN}\"Agent said it worked\" ≠ \"Verified experience\"{RESET}\n")
        print(f"  {BOLD}What CogniCore provides:{RESET}")
        print(f"  • Structured experience with attempt history")
        print(f"  • Evidence-based verification (gate validates, doesn't execute)")
        print(f"  • First-class failure memory (warnings, not just solutions)")
        print(f"  • Environment compatibility checking before transfer")
        print(f"  • Deterministic content hash for tamper detection")
        print(f"  • Re-validation when environment changes")
        print(f"  • Supersession & conflict resolution")
        print()
        print(f"  {DIM}Agents don't share conversations. They share experience.{RESET}")
        print()

    finally:
        # Close SQLite connections before cleanup (Windows file locks)
        try:
            backend_a.close()
        except Exception:
            pass
        try:
            backend_b.close()
        except Exception:
            pass
        import shutil
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
