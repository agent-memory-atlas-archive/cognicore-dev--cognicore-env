import json

with open("raw_results.json") as f:
    raw_data = json.load(f)

# Get cold start results
cs_runs = {}
for cond in raw_data:
    if cond["condition"] == "Cold Start":
        cs_runs = {r["episode"]: r["success"] for r in cond["runs"]}
        break

total_tasks = 20

final_results = {}
for cond in raw_data:
    condition = cond["condition"]
    runs = cond["runs"]
    
    successes = sum(1 for r in runs if r["success"])
    success_rate = successes / total_tasks * 100
    
    neg_transfers = 0
    if condition != "Cold Start":
        neg_transfers = sum(1 for r in runs if cs_runs[r["episode"]] and not r["success"])
    neg_transfer_rate = neg_transfers / total_tasks * 100
    
    recoveries = 0
    initial_failures = sum(1 for r in runs if not r["first_action_accuracy"])
    
    if initial_failures > 0:
        recoveries = sum(1 for r in runs if not r["first_action_accuracy"] and r["success"])
        recovery_rate = recoveries / initial_failures * 100
    else:
        recovery_rate = 0.0
        
    final_results[condition] = {
        "success_rate": success_rate,
        "neg_transfers": neg_transfer_rate,
        "recovery_rate": recovery_rate,
    }

cs_success = final_results["Cold Start"]["success_rate"]
for cond in final_results:
    final_results[cond]["delta"] = final_results[cond]["success_rate"] - cs_success

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

print("\nMethod | Success | Delta | Neg. | Recovery")
print("-" * 50)
conditions = ["Cold Start", "Retrieval", "Raw Experience", "Distilled Lesson", "CogniCore-AMT", "AMT + Replay"]
for cond in conditions:
    r = final_results[cond]
    print(f"{cond[:15]:15} | {r['success_rate']:5.1f}% | {r['delta']:+5.1f}% | {r['neg_transfers']:5.1f}% | {r['recovery_rate']:5.1f}%")
    
print("\nLaTeX Table:")
for cond in conditions:
    r = final_results[cond]
    print(f"{cond} & {r['success_rate']:.1f}\\% & {r['delta']:+.1f}\\% & {r['neg_transfers']:.1f}\\% & {r['recovery_rate']:.1f}\\% \\\\")

with open("aggregate_results_fixed.json", "w") as f:
    json.dump(final_results, f, indent=2)
