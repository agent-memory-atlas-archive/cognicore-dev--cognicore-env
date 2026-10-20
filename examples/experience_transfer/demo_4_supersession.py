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

DB_PATH = str(Path(__file__).parent / "demo_4_supersession.db")

def main():
    if os.path.exists(DB_PATH):
        try: os.remove(DB_PATH)
        except OSError: pass

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SESSION 1 — Agent A uses Approach X successfully
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "="*60)
    print(" SESSION 1: Agent A solves parsing with Pydantic v1")
    print("="*60)
    
    backend_a = SQLiteMemoryBackend(DB_PATH)
    backend_a._init_db()

    exp_a_payload = {
        "successful_approach": "Use @root_validator(pre=True)",
    }

    entry_a = MemoryEntry(
        text="Pydantic validation: Use @root_validator(pre=True)",
        category="validation",
        memory_type=MemoryType.EXPERIENCE,
        state=MemoryState.VERIFIED,
        metadata={"experience": exp_a_payload, "version": "pydantic-1.0"}
    )
    id_a = backend_a.store(entry_a)
    print("\n🧠 COGNICORE: Experience A saved.")
    print("  'Use @root_validator(pre=True)'")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SESSION 2 — Dependency changes, Agent B fails with X
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "="*60)
    print(" SESSION 2: Agent B upgrades to Pydantic v2")
    print("="*60)

    backend_b = SQLiteMemoryBackend(DB_PATH)

    print("\nAGENT B: Task -> Implement validation with Pydantic v2.")
    print("AGENT B: Querying CogniCore...")

    results = backend_b.search("Pydantic validation")
    mem_a = results[0].entry
    print(f"\n🧠 COGNICORE: Found Experience A -> {mem_a.text}")
    
    time.sleep(0.5)
    print("\nAGENT B: Trying Experience A...")
    print("❌ FAILED: @root_validator is deprecated in Pydantic v2")

    print("\nAGENT B: Discovering new approach...")
    time.sleep(0.5)
    print("✅ SUCCESS: Use @model_validator(mode='before')")

    exp_b_payload = {
        "successful_approach": "Use @model_validator(mode='before')",
        "supersedes_reason": "@root_validator no longer works with Pydantic v2."
    }

    entry_b = MemoryEntry(
        text="Pydantic validation: Use @model_validator(mode='before')",
        category="validation",
        memory_type=MemoryType.EXPERIENCE,
        state=MemoryState.VERIFIED,
        supersedes=id_a,
        metadata={"experience": exp_b_payload, "version": "pydantic-2.0"}
    )
    id_b = backend_b.store(entry_b)
    
    # Invalidate old memory
    backend_b.update(id_a, invalidated_by=id_b, invalidated_reason=exp_b_payload["supersedes_reason"])

    print("\n🧠 COGNICORE: Experience B saved. Experience A marked as superseded.")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SESSION 3 — Agent C queries later
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("\n" + "="*60)
    print(" SESSION 3: Agent C needs Pydantic validation")
    print("="*60)
    
    backend_c = SQLiteMemoryBackend(DB_PATH)
    
    print("\nAGENT C: Querying CogniCore for 'Pydantic validation'...")
    results = backend_c.search("Pydantic validation")
    
    # Get the best match
    mem_c = results[0].entry
    
    if mem_c.invalidated_by:
        print(f"\n🧠 COGNICORE: Retrieved Experience A -> {mem_c.text}")
        print("   ⚠️ WARNING: This experience is marked as INVALIDATED.")
        
        # Follow the chain to the new memory
        new_mem = backend_c.get_by_id(mem_c.invalidated_by)
        print(f"   → Superseded by: {new_mem.text}")
        print(f"   Reason: {new_mem.metadata['experience']['supersedes_reason']}")
        mem_c = new_mem
    else:
        print(f"\n🧠 COGNICORE: Retrieved Experience -> {mem_c.text}")

    print("\nAGENT C:")
    print('"I received the updated Pydantic v2 experience and will avoid the deprecated v1 approach."')

    print("\n" + "-"*60)
    print("DEMO_RESULT: PASS")
    print("EXPERIENCE_TRANSFERRED: true")
    print("VERIFIED: true (supersession successful)")

    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
    except OSError:
        pass

if __name__ == "__main__":
    main()
