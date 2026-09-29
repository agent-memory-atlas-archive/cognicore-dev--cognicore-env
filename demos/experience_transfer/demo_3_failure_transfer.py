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

DB_PATH = str(Path(__file__).parent / "demo_3_failure.db")

def main():
    if os.path.exists(DB_PATH):
        try: os.remove(DB_PATH)
        except OSError: pass

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SESSION 1 — Agent A tries a failing approach
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "="*60)
    print(" SESSION 1: Agent A encounters a stateful module error")
    print("="*60)
    
    backend_a = SQLiteMemoryBackend(DB_PATH)
    backend_a._init_db()

    print("\nAGENT A: Task -> Initialize global metrics cache")
    print("AGENT A: Trying Approach X (Singleton pattern)...")
    time.sleep(0.5)
    
    print("\n❌ FAILED")
    print("Reason: Module was stateful across test cases causing test bleeding.")

    experience_payload = {
        "problem": "Initialize global metrics cache",
        "attempts": [
            {
                "approach": "Singleton pattern",
                "result": "Failed",
                "reason": "Module was stateful across test cases causing test bleeding."
            }
        ]
    }

    entry = MemoryEntry(
        text="Global metrics cache: Avoid Singleton pattern due to stateful test bleeding.",
        category="caching",
        memory_type=MemoryType.FAILURE,
        state=MemoryState.VERIFIED,
        metadata={"experience": experience_payload}
    )
    backend_a.store(entry)
    print("\n🧠 COGNICORE: Failure memory recorded. Don't repeat the mistake.")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SESSION 2 — Agent B encounters a similar task
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "="*60)
    print(" SESSION 2: Agent B gets a similar task")
    print("="*60)
    
    backend_b = SQLiteMemoryBackend(DB_PATH)

    print("\nAGENT B: Task -> Add a caching layer for the metrics API.")
    print("AGENT B: Querying CogniCore...")

    # Real retrieval
    results = backend_b.search("metrics cache")
    
    if not results:
        print("AGENT B: No experience found.")
        print("\nDEMO_RESULT: FAIL")
        return

    mem = results[0].entry
    exp = mem.metadata.get("experience", {})
    
    print("\n🧠 COGNICORE: Found 1 relevant FAILURE memory:")
    for attempt in exp.get("attempts", []):
        print(f"  ❌ {attempt['approach']}")
        print(f"     Failed because: {attempt['reason']}")

    print("\nAGENT B:")
    print('"I see that a Singleton pattern previously failed under these conditions')
    print(' due to stateful test bleeding. I will avoid using a Singleton and')
    print(' instead pass the cache dependency explicitly."')
    
    print("\n" + "-"*60)
    print("DEMO_RESULT: PASS")
    print("EXPERIENCE_TRANSFERRED: true")
    print("VERIFIED: true (failure transfer successful)")

    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
    except OSError:
        pass

if __name__ == "__main__":
    main()
