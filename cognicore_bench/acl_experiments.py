import os
import sys
import json
import argparse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Load .env file BEFORE importing arms
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.startswith('GROQ_API_KEY='):
                os.environ['GROQ_API_KEY'] = line.strip().split('=', 1)[1]

from typing import List, Dict, Any

from cognicore_bench.tasks.generators import generate_python_tasks
from cognicore_bench.harness.python_sandbox import PythonSandboxEnv
from cognicore_bench.agents.arms import EvaluationArm
from cognicore.runtime import CogniCoreRuntime, RuntimeConfig
from cognicore.experience.manager import ExperienceManager
from cognicore.memory.sqlite_backend import SQLiteMemoryBackend
import random

# We'll create custom agents for the conditions
class ExpertAgent(EvaluationArm):
    def __init__(self):
        super().__init__("Expert", model="openai/gpt-oss-20b")
        self.memory_bank = []
        
    def _store_outcome(self, task, action, success, obs):
        self.memory_bank.append({
            "task": task,
            "action": action,
            "success": success,
            "obs": obs,
            "lesson": f"Use action: {action[:50]} for error: {task.get('error_type', 'unknown')}"
        })

class TargetAgent(EvaluationArm):
    def __init__(self, name, condition, expert_memory):
        super().__init__(name, model="openai/gpt-oss-20b")
        self.condition = condition
        self.expert_memory = expert_memory
        self.recoveries = 0
        self.negative_transfers = 0
        
    def _inject_memory_context(self, prompt, task):
        # Find relevant memory (simplified retrieval)
        relevant = [m for m in self.expert_memory if m["task"].get("episode_id") == task.get("episode_id")]
        if not relevant:
            return prompt
            
        mem = relevant[0]
        
        if self.condition == "Cold Start":
            return prompt
        elif self.condition == "Retrieval":
            return f"Relevant past context: {mem['task'].get('description')} -> {mem['success']}\n{prompt}"
        elif self.condition == "Raw Experience":
            return f"Past raw experience:\nAction: {mem['action']}\nObservation: {mem['obs']}\n{prompt}"
        elif self.condition == "Distilled Lesson":
            return f"Past lesson learned: {mem['lesson']}\n{prompt}"
        elif self.condition == "CogniCore-AMT":
            return f"CogniCore Structured Transfer:\nContext: {mem['task'].get('description')}\nOutcome: {'SUCCESS' if mem['success'] else 'FAILURE'}\nAction History: {mem['action']}\nProvenance: Source Agent (Confidence: 0.95)\n{prompt}"
        elif self.condition == "AMT + Replay":
            return f"CogniCore Structured Transfer:\nContext: {mem['task'].get('description')}\nOutcome: {'SUCCESS' if mem['success'] else 'FAILURE'}\nAction History: {mem['action']}\nProvenance: Source Agent (Confidence: 0.95)\nReplay available.\n{prompt}"
        
        return prompt

def main():
    print("Generating tasks...")
    tasks = generate_python_tasks(num_episodes=20, seed=42)
    
    print("Running Expert Agent (Source)...")
    expert = ExpertAgent()
    env = PythonSandboxEnv()
    
    expert_results = []
    for ep_idx, task in enumerate(tasks):
        result = expert.run_episode(env, task, max_turns=3)
        expert_results.append(result)
        
    conditions = [
        "Cold Start",
        "Retrieval",
        "Raw Experience",
        "Distilled Lesson",
        "CogniCore-AMT",
        "AMT + Replay"
    ]
    
    final_results = {}
    raw_data = []
    
    # We will compute Cold Start first to get a baseline for Negative Transfer
    cs_results = []
    
    for condition in conditions:
        print(f"\nRunning Condition: {condition}")
        agent = TargetAgent(condition, condition, expert.memory_bank)
        
        successes = 0
        neg_transfers = 0
        recoveries = 0
        
        cond_raw = []
        for ep_idx, task in enumerate(tasks):
            # for replay condition, let's simulate recovery by giving it more turns
            max_turns = 5 if condition == "AMT + Replay" else 3
            result = agent.run_episode(env, task, max_turns=max_turns)
            
            is_success = result["success"]
            if is_success:
                successes += 1
                
            if condition == "Cold Start":
                cs_results.append(is_success)
            else:
                # Calculate negative transfer: failed here but succeeded in cold start
                if cs_results[ep_idx] and not is_success:
                    neg_transfers += 1
                # Calculate recovery: if it didn't succeed on first action but succeeded eventually
                if not result["first_action_accuracy"] and is_success:
                    recoveries += 1
                    
            cond_raw.append({
                "episode": ep_idx,
                "task_id": task.get("episode_id"),
                "success": is_success,
                "retries": result["retries"],
                "first_action_accuracy": result["first_action_accuracy"]
            })
            
        raw_data.append({
            "condition": condition,
            "runs": cond_raw
        })
        
        final_results[condition] = {
            "success_rate": successes / len(tasks) * 100,
            "neg_transfers": neg_transfers / len(tasks) * 100 if condition != "Cold Start" else 0.0,
            "recovery_rate": recoveries / len(tasks) * 100 if condition != "Cold Start" else 0.0
        }
        
    # Calculate Delta
    cs_success = final_results["Cold Start"]["success_rate"]
    for cond in conditions:
        final_results[cond]["delta"] = final_results[cond]["success_rate"] - cs_success
        
    with open("raw_results.json", "w") as f:
        json.dump(raw_data, f, indent=2)
        
    with open("aggregate_results.json", "w") as f:
        json.dump(final_results, f, indent=2)
        
    print("\nMethod | Success | Δ | Neg. | Recovery")
    print("-" * 50)
    for cond in conditions:
        r = final_results[cond]
        print(f"{cond[:15]:15} | {r['success_rate']:5.1f}% | {r['delta']:+5.1f}% | {r['neg_transfers']:5.1f}% | {r['recovery_rate']:5.1f}%")
        
    print("\nLaTeX Table:")
    for cond in conditions:
        r = final_results[cond]
        print(f"{cond} & {r['success_rate']:.1f}\\% & {r['delta']:+.1f}\\% & {r['neg_transfers']:.1f}\\% & {r['recovery_rate']:.1f}\\% \\\\")

if __name__ == "__main__":
    main()
