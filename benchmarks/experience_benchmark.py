import os
import json
import time
from typing import Dict, Any, List

# Create benchmark_output dir
os.makedirs("benchmark_output", exist_ok=True)

from cognicore.memory.sqlite_backend import SQLiteMemoryBackend
from cognicore.memory.base import MemoryEntry, MemoryState, MemoryType
from cognicore.experience.manager import ExperienceManager
from cognicore.experience.schema import (
    StructuredExperience, Attempt, AttemptOutcome, EnvironmentContext, VerificationStatus, EvidenceRecord
)

# Benchmark settings
REPETITIONS = 5
DB_PATH_A = "benchmark_output/mem_a.db"
DB_PATH_B = "benchmark_output/mem_b.db"
DB_PATH_C = "benchmark_output/mem_c.db"
DB_PATH_D = "benchmark_output/mem_d.db"

def clear_db(path):
    if os.path.exists(path):
        os.remove(path)

class MockAgent:
    def __init__(self, arm: str, db_path: str):
        self.arm = arm
        self.backend = None
        self.manager = None
        if arm != "A":
            self.backend = SQLiteMemoryBackend(db_path)
        if arm in ["C", "D"]:
            self.manager = ExperienceManager(self.backend)
            
    def store_experience(self, exp_data: Dict[str, Any]):
        if self.arm == "A":
            return
        elif self.arm == "B":
            text = f"Task: {exp_data['task']}. Solution: {exp_data['successful_approach']}."
            if exp_data.get('failed_approaches'):
                text += f" Failures: {', '.join(exp_data['failed_approaches'])}"
            entry = MemoryEntry(
                text=text,
                category="task_solution",
                state=MemoryState.VERIFIED.value,
                memory_type=MemoryType.SEMANTIC.value
            )
            self.backend.store(entry)
        elif self.arm in ["C", "D"]:
            attempts = []
            if exp_data.get('failed_approaches'):
                for f in exp_data['failed_approaches']:
                    attempts.append(Attempt(approach=f, outcome=AttemptOutcome.FAILURE.value, reason="Failed"))
            attempts.append(Attempt(approach=exp_data['successful_approach'], outcome=AttemptOutcome.SUCCESS.value, reason="Worked"))
            
            env = EnvironmentContext(
                python_version=exp_data.get('python', '3.9')
            )
            
            exp = StructuredExperience(
                task=exp_data['task'],
                problem=exp_data['task'],
                attempts=attempts,
                environment=env,
                verification_status=VerificationStatus.CANDIDATE.value
            )
            exp_id = self.manager.record(exp)
            
            if self.arm == "D" and exp_data.get('is_verified', True):
                evidence = [EvidenceRecord(command="pytest", exit_code=0, timestamp="2026-08-20T00:00:00")]
                self.manager.verify(exp_id, evidence)
                
    def solve_task(self, task: str, env_data: Dict[str, str], options: List[str], correct_option: str, conflict_mode=False) -> Dict[str, Any]:
        retrieved_text = ""
        context_size = 0
        approaches_tried = []
        is_success = False
        
        if self.arm == "B":
            res = self.backend.search(task, top_k=3)
            for r in res:
                retrieved_text += r.entry.text + "\n"
                context_size += len(r.entry.text)
                
        elif self.arm in ["C", "D"]:
            env = EnvironmentContext(
                python_version=env_data.get('python', '3.9')
            )
            exps = self.manager.retrieve(task, current_env=env, require_verified=(self.arm == "D"))
            
            if conflict_mode and len(exps.experiences) > 1:
                # Mock conflict resolution manager behavior
                # For D, only keep the VERIFIED/TRANSFERABLE one
                # For C, keep both
                pass
                
            for e in exps.experiences:
                # D trusts only VERIFIED+
                if self.arm == "D":
                    # Simple heuristic: if we want to reject unverified / incompatible
                    # Manager.retrieve handles some, but we enforce strict filtering for D
                    if e.verification_status not in [VerificationStatus.VERIFIED.value, VerificationStatus.PROMOTED.value, VerificationStatus.TRANSFERABLE.value]:
                        continue
                        
                for a in e.attempts:
                    if a.outcome == AttemptOutcome.FAILURE.value:
                        retrieved_text += f"Avoid: {a.approach}\n"
                    elif a.outcome == AttemptOutcome.SUCCESS.value:
                        retrieved_text += f"Try: {a.approach}\n"
                context_size += len(json.dumps(e._to_payload_dict()))

        # Simulate agent reasoning
        for opt in options:
            if opt in retrieved_text and "Avoid:" in retrieved_text and retrieved_text.find(f"Avoid: {opt}") != -1:
                continue # Skip failed
            approaches_tried.append(opt)
            
            # If we see a "Try:" we might try it first. But we just iterate options.
            if f"Try: {opt}" in retrieved_text:
                pass # Already tried
                
            if opt == correct_option:
                is_success = True
                break
                
        return {
            "success": is_success,
            "attempts": len(approaches_tried),
            "context_injected": context_size,
            "approaches": approaches_tried
        }

def run_scenario(name, train_data, test_task, env_data, options, correct_option, conflict_mode=False):
    results = {}
    for arm in ["A", "B", "C", "D"]:
        db_path = f"benchmark_output/mem_{arm.lower()}_{time.time()}.db"
        agent = MockAgent(arm, db_path)
        
        for d in train_data:
            agent.store_experience(d)
            
        res = agent.solve_task(test_task, env_data, options, correct_option, conflict_mode)
        results[arm] = res
    return results

def main():
    print("Starting experience benchmark...")
    all_results = []
    
    scenarios = [
        {
            "name": "1. Reduces repeated failed approaches & improves successful reuse",
            "train": [{"task": "Fix JWT auth", "failed_approaches": ["use RS256", "use HS256 without salt"], "successful_approach": "use HS256 with strong salt", "is_verified": True}],
            "test_task": "Fix JWT auth",
            "env_data": {"os": "linux", "python": "3.9"},
            "options": ["use RS256", "use HS256 without salt", "use HS256 with strong salt", "other"],
            "correct_option": "use HS256 with strong salt"
        },
        {
            "name": "2. Prevents unverified experience from being trusted",
            "train": [{"task": "Sort list fast", "failed_approaches": [], "successful_approach": "bogo sort", "is_verified": False}], 
            "test_task": "Sort list fast",
            "env_data": {"os": "linux", "python": "3.9"},
            "options": ["bogo sort", "quick sort"],
            "correct_option": "quick sort"
        },
        {
            "name": "3. Rejects stale/incompatible experience",
            "train": [{"task": "Install tensorflow", "failed_approaches": ["pip install tf"], "successful_approach": "pip install tensorflow==2.4", "python": "2.7", "is_verified": True}],
            "test_task": "Install tensorflow",
            "env_data": {"os": "linux", "python": "3.11"},
            "options": ["pip install tensorflow==2.4", "pip install tensorflow>=2.13", "pip install tf"],
            "correct_option": "pip install tensorflow>=2.13"
        },
        {
            "name": "4. Handles conflicting experiences",
            "train": [
                {"task": "Run tests", "successful_approach": "pytest", "is_verified": False},
                {"task": "Run tests", "successful_approach": "nose2", "is_verified": True}
            ],
            "test_task": "Run tests",
            "env_data": {"os": "linux", "python": "3.9"},
            "options": ["pytest", "nose2", "unittest"],
            "correct_option": "nose2",
            "conflict_mode": True
        }
    ]
    
    for _ in range(REPETITIONS):
        for sc in scenarios:
            res = run_scenario(
                sc["name"], sc["train"], sc["test_task"], sc["env_data"], 
                sc["options"], sc["correct_option"], 
                conflict_mode=sc.get("conflict_mode", False)
            )
            all_results.append({
                "scenario": sc["name"],
                "results": res
            })
            
    with open("benchmark_output/experience_benchmark_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
        
    print("Benchmark complete. Results saved.")
    
    print("\nComparison Table (Averages over {} repetitions):".format(REPETITIONS))
    print(f"{'Scenario':<60} | {'Arm':<4} | {'Success':<8} | {'Attempts':<10} | {'Context Size'}")
    print("-" * 110)
    
    for sc in scenarios:
        for arm in ["A", "B", "C", "D"]:
            rel_res = [r["results"][arm] for r in all_results if r["scenario"] == sc["name"]]
            succ = sum(1 for r in rel_res if r["success"]) / len(rel_res)
            att = sum(r["attempts"] for r in rel_res) / len(rel_res)
            ctx = sum(r["context_injected"] for r in rel_res) / len(rel_res)
            print(f"{sc['name']:<60} | {arm:<4} | {succ:<8.2f} | {att:<10.2f} | {ctx:.0f}")

if __name__ == '__main__':
    main()
