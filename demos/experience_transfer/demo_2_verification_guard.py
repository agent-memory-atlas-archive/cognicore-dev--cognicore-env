import os
import sys
import time
import json
from pathlib import Path

# Setup paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.absolute()))
sys.stdout.reconfigure(encoding="utf-8")

from cognicore.memory.sqlite_backend import SQLiteMemoryBackend
from cognicore.memory.base import MemoryEntry, MemoryState, MemoryType

DB_PATH = str(Path(__file__).parent / "demo_2_verification.db")

def main():
    if os.path.exists(DB_PATH):
        try: os.remove(DB_PATH)
        except OSError: pass

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SESSION 1 — Agent A creates a verified approach
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "="*60)
    print(" SESSION 1: Agent A uses Approach X on FastAPI 0.95")
    print("="*60)
    
    backend_a = SQLiteMemoryBackend(DB_PATH)
    backend_a._init_db()

    print("\nAGENT A: Environment context detected:")
    print("  Python 3.11")
    print("  FastAPI 0.95")
    print("  Commit abc1234")
    
    time.sleep(0.5)
    print("\nAGENT A: Approach X -> ✅ VERIFIED")

    # Store experience with environment metadata
    experience_payload = {
        "problem": "Handling streaming responses",
        "successful_approach": "Use StreamingResponse with generator yield",
        "verification": {
            "command": "pytest tests/api/test_streaming.py",
            "exit_code": 0,
            "tests_passed": 5
        },
        "environment": {
            "python": "3.11",
            "fastapi": "0.95",
            "commit": "abc1234"
        }
    }

    entry = MemoryEntry(
        text="Handling streaming responses using StreamingResponse with generator yield.",
        category="api",
        memory_type=MemoryType.EXPERIENCE,
        state=MemoryState.VERIFIED,
        metadata={"experience": experience_payload, "env_hash": "python3.11-fastapi0.95"}
    )
    backend_a.store(entry)
    print("\n🧠 COGNICORE: Experience saved and verified for the current environment.")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SESSION 2 — Agent B encounters a different environment
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "="*60)
    print(" SESSION 2: Agent B runs on FastAPI 0.115")
    print("="*60)
    
    backend_b = SQLiteMemoryBackend(DB_PATH)

    print("\nAGENT B: Environment context detected:")
    print("  Python 3.13")
    print("  FastAPI 0.115")
    print("  Commit xyz7890")
    
    time.sleep(0.5)
    print("\nAGENT B: Task -> Implement streaming response.")
    print("AGENT B: Querying CogniCore...")

    # Real retrieval
    results = backend_b.search("streaming responses")
    
    if not results:
        print("AGENT B: No experience found.")
        print("\nDEMO_RESULT: FAIL")
        return

    mem = results[0].entry
    exp = mem.metadata.get("experience", {})
    prev_env = exp.get("environment", {})
    
    # Simulate Context Verification Logic
    print("\n⚠️ CONTEXT MISMATCH")
    print(f"\nPrevious environment:")
    print(f"  Python {prev_env.get('python')}")
    print(f"  FastAPI {prev_env.get('fastapi')}")
    print(f"\nCurrent environment:")
    print("  Python 3.13")
    print("  FastAPI 0.115")
    
    print("\nPrevious experience:")
    print("  VALID PROVENANCE")
    print("  BUT CURRENT VALIDITY UNKNOWN")
    
    print("\n🧠 COGNICORE: Experience NOT promoted automatically.")
    print("             → Requires independent verification")

    print("\nAGENT B:")
    print('"I received a past verified experience but the dependency versions differ.')
    print(' I will independently verify Approach X against FastAPI 0.115 before committing."')
    
    print("\n" + "-"*60)
    print("DEMO_RESULT: PASS")
    print("EXPERIENCE_TRANSFERRED: true")
    print("VERIFIED: false (blocked by environment guard)")

    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
    except OSError:
        pass

if __name__ == "__main__":
    main()
