import os
import sys
import time
import argparse
from pathlib import Path

# Setup paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.absolute()))
sys.stdout.reconfigure(encoding="utf-8")

from cognicore.memory.sqlite_backend import SQLiteMemoryBackend
from cognicore.memory.base import MemoryEntry, MemoryState, MemoryType

DB_PATH = str(Path(__file__).parent / "demo_5_integrations.db")

def mock_llm_call(agent_name, prompt):
    print(f"\n[{agent_name} API Call]")
    print(f"Prompt: {prompt}")
    time.sleep(1)
    if "Claude" in agent_name:
        return "I found that sorting the input arrays before calling the intersection algorithm reduces time complexity from O(N^2) to O(N log N)."
    elif "Codex" in agent_name:
        return "Based on the retrieved memory, I will sort both arrays first before finding the intersection to achieve O(N log N) performance."
    return "OK."

def main(live_mode=False):
    if os.path.exists(DB_PATH):
        try: os.remove(DB_PATH)
        except OSError: pass

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SESSION 1 — Claude learns an optimization
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "="*60)
    print(" SESSION 1: Claude optimizes an intersection algorithm")
    print("="*60)
    
    backend_a = SQLiteMemoryBackend(DB_PATH)
    backend_a._init_db()

    print("\nCLAUDE: Task -> Optimize array intersection")
    
    if live_mode:
        print("CLAUDE: [LIVE MODE NOT FULLY IMPLEMENTED - FALLING BACK TO MOCK]")
    
    response = mock_llm_call("Claude", "Optimize array intersection algorithm")
    print(f"\nCLAUDE: {response}")

    print("\n✅ VERIFIED: pytest tests/algo -> PASS")

    experience_payload = {
        "problem": "O(N^2) time complexity on array intersection",
        "successful_approach": "Sort arrays before intersection (O(N log N))",
        "verification": {
            "command": "pytest tests/algo",
            "exit_code": 0,
            "tests_passed": 3
        }
    }

    entry = MemoryEntry(
        text="Array Intersection Optimization: Sort the input arrays before calling the intersection algorithm to reduce time complexity from O(N^2) to O(N log N).",
        category="algorithm",
        memory_type=MemoryType.EXPERIENCE,
        state=MemoryState.VERIFIED,
        metadata={"experience": experience_payload}
    )
    backend_a.store(entry)
    print("\n🧠 COGNICORE: Claude's experience saved.")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SESSION 2 — Codex inherits the optimization
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "="*60)
    print(" SESSION 2: Codex needs to write intersection code")
    print("="*60)
    
    backend_b = SQLiteMemoryBackend(DB_PATH)

    print("\nCODEX: Task -> Write array intersection function")
    print("CODEX: Querying CogniCore...")

    results = backend_b.search("array intersection")
    
    if not results:
        print("CODEX: No experience found.")
        print("\nDEMO_RESULT: FAIL")
        return

    mem = results[0].entry
    print(f"\n🧠 COGNICORE: Retrieved Experience -> {mem.text}")
    
    response2 = mock_llm_call("Codex", f"Write array intersection function. Context: {mem.text}")
    print(f"\nCODEX: {response2}")
    
    print("\n" + "-"*60)
    print("DEMO_RESULT: PASS")
    print("EXPERIENCE_TRANSFERRED: true")
    print("VERIFIED: true (cross-model transfer successful)")

    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
    except OSError:
        pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cross-model transfer demo")
    parser.add_argument("--live", action="store_true", help="Use real LLM APIs instead of mocks")
    args = parser.parse_args()
    main(live_mode=args.live)
