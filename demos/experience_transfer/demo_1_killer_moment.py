import os
import sys
import time
import json
from pathlib import Path

# Setup paths to ensure we can import cognicore
sys.path.insert(0, str(Path(__file__).parent.parent.parent.absolute()))
sys.stdout.reconfigure(encoding="utf-8")

from cognicore.memory.sqlite_backend import SQLiteMemoryBackend
from cognicore.memory.base import MemoryEntry, MemoryState, MemoryType

DB_PATH = str(Path(__file__).parent / "demo_1_killer.db")

def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SESSION 1 — Agent A solves the problem
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "="*60)
    print(" SESSION 1: Agent A (Claude) fixes an authentication bug")
    print("="*60)
    
    # Simulate Agent A process with real DB
    backend_a = SQLiteMemoryBackend(DB_PATH)
    backend_a._init_db()

    print("\nAGENT A: Task -> Fix intermittent JWT authentication failures")
    print("\nAttempt 1: Increase JWT expiration")
    time.sleep(0.5)
    print("❌ FAILED: tests/auth timeout")

    print("\nAttempt 2: Modify retry logic")
    time.sleep(0.5)
    print("❌ FAILED: race condition in auth_middleware.py")

    print("\nAttempt 3: Fix refresh-token lifecycle")
    time.sleep(0.5)
    print("✅ SUCCESS")
    print("VERIFICATION: pytest tests/auth -> 18 passed")

    # CogniCore records the experience directly to persistent storage
    experience_payload = {
        "problem": "Intermittent JWT authentication failure",
        "attempts": [
            {"approach": "Increasing JWT expiration", "result": "Failed", "reason": "tests/auth timeout"},
            {"approach": "Modifying retry logic", "result": "Failed", "reason": "race condition in auth_middleware.py"}
        ],
        "successful_approach": "Refresh-token lifecycle fix",
        "verification": {
            "command": "pytest tests/auth",
            "exit_code": 0,
            "tests_passed": 18
        },
        "repository": {
            "repo_id": "my-project",
            "commit": "abc1234"
        }
    }

    entry = MemoryEntry(
        text="JWT Authentication fix: Avoid modifying expiration or retry logic; properly fix refresh-token lifecycle.",
        category="authentication",
        memory_type=MemoryType.EXPERIENCE,
        state=MemoryState.VERIFIED,
        metadata={"experience": experience_payload}
    )
    backend_a.store(entry)
    print("\n🧠 COGNICORE: Verified experience promoted and saved to persistent SQLite.")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SESSION 2 — Agent B inherits the experience
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "="*60)
    print(" SESSION 2: Agent B (Gemini) encounters the same problem")
    print("="*60)
    
    # Completely independent process/session simulation (new backend instance)
    backend_b = SQLiteMemoryBackend(DB_PATH)

    print("\nNEW SESSION: No previous conversation available.")
    print("\nAGENT B: Task -> Investigate JWT authentication failure.")
    time.sleep(0.5)
    
    print("\nAGENT B: Let me query CogniCore for related past experiences...")
    
    # Real retrieval against the persistent SQLite database
    results = backend_b.search("JWT authentication failure", top_k=1)
    
    if not results:
        print("AGENT B: No experience found. Starting from scratch.")
        print("\nDEMO_RESULT: FAIL")
        return

    mem = results[0].entry
    exp = mem.metadata.get("experience", {})
    
    print("\n🧠 CogniCore retrieved 1 relevant experience")
    for attempt in exp.get("attempts", []):
        print(f"  ❌ {attempt['approach']}")
        print(f"     Failed because: {attempt['reason']}")
    print(f"  ✅ {exp.get('successful_approach')}")
    print(f"     Verified: {exp.get('verification', {}).get('tests_passed')} tests passed")
    
    print("\nAGENT B:")
    print('"I found a verified previous experience for this repository.')
    print(' I\'ll inspect the refresh-token lifecycle first rather than')
    print(' repeating the two failed approaches."')
    
    print("\n" + "-"*60)
    print("DEMO_RESULT: PASS")
    print("EXPERIENCE_TRANSFERRED: true")
    print("VERIFIED: true")

    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
    except OSError:
        pass

if __name__ == "__main__":
    main()
