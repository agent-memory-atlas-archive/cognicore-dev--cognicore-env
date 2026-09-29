import os, json, requests, time, re

API_KEY = os.environ.get("SARVAM_API_KEY")
URL = "https://api.sarvam.ai/v1/chat/completions"
MODEL = "sarvam-105b-conversations"

V2_SYSTEM_PROMPT = """Extract core facts, rules, preferences, constraints, successful solutions, and failed approaches from this transcript into a JSON array: [{"text": "3rd person detail", "memory_type": "preference|semantic|constraint"}]. Return [] if none. Preserve context and negations. ONLY output valid JSON."""

def compress_transcript_safe(transcript: str) -> str:
    # Safe compression: only replace prefixes and strip extra whitespace. Never remove words.
    lines = []
    for line in transcript.split("\n"):
        line = line.strip()
        if not line: continue
        line = line.replace("User:", "U:").replace("Agent:", "A:")
        lines.append(line)
    return "\n".join(lines)

def generate_dataset():
    samples = []
    samples.append({
        "id": "regression_test_1",
        "transcript": "User: Hi there! I'm working on a new web project.\nAgent: Hello! What kind of project is it?\nUser: It's a dashboard for visualizing sales data. I really prefer using React and TypeScript for the frontend.\nAgent: Sounds great! What about the backend?\nUser: The backend has to be Python with FastAPI, that's a hard constraint because the rest of the company uses it.\nAgent: Understood.\nUser: Also, please always use single quotes instead of double quotes in JS/TS. It's my preference.",
        "expected_keywords": ["sales", "react", "typescript", "fastapi", "single quote"],
        "category": "mixed"
    })
    techs = ["Vue", "Angular", "Svelte", "Next.js", "Nuxt", "Django", "Flask", "Spring Boot", "Go Fiber", "Ruby on Rails"]
    for i, t in enumerate(techs):
        samples.append({
            "id": f"pref_{i}",
            "transcript": f"User: Let's build a new microservice.\nAgent: Sure, what stack?\nUser: I want to use {t}. It's an absolute must for this project.\nAgent: Got it, {t} it is.\nUser: Also, make sure to use 4 spaces for indentation.",
            "expected_keywords": [t.lower(), "microservice", "4 spaces"],
            "category": "preferences"
        })
    issues = ["CORS error", "OOM kill", "Timeout", "Connection reset", "Segfault", "Deadlock", "NullPointer", "Type mismatch", "Memory leak", "Race condition"]
    fixes = ["add proxy", "increase swap", "extend timeout", "keepalive", "gdb", "mutex lock", "optional chaining", "cast variable", "weakref", "atomic"]
    for i, (issue, fix) in enumerate(zip(issues, fixes)):
        samples.append({
            "id": f"fail_fix_{i}",
            "transcript": f"User: I'm getting a {issue} in the production server.\nAgent: Have you tried looking at the logs?\nUser: Yes. I applied the {fix} fix and it completely resolved the {issue}. Remember this for next time.",
            "expected_keywords": [issue.lower(), fix.lower(), "production"],
            "category": "failures_fixes"
        })
    domains = ["e-commerce", "healthcare", "fintech", "edtech", "gaming", "social media", "logistics", "crypto", "real estate", "streaming"]
    for i, d in enumerate(domains):
        samples.append({
            "id": f"fact_{i}",
            "transcript": f"User: Our new {d} platform is launching next month.\nAgent: Exciting! Any specific architecture?\nUser: We decided to go with event-driven architecture using Kafka.\nAgent: Noted. Kafka for the {d} platform.",
            "expected_keywords": [d.lower(), "event-driven", "kafka"],
            "category": "facts"
        })
    for i in range(10):
        samples.append({
            "id": f"conflict_{i}",
            "transcript": f"User: Let's use MongoDB for the database.\nAgent: Okay, setting up MongoDB.\nUser: Wait, actually no, the team changed their mind. We must use PostgreSQL instead due to ACID requirements.",
            "expected_keywords": ["postgresql", "acid"],
            "category": "conflicts"
        })
    for i in range(4):
        samples.append({
            "id": f"env_{i}",
            "transcript": f"User: I'm deploying the app now.\nAgent: Where is it being deployed?\nUser: We are running on Ubuntu 22.04 LTS. The Python version is strictly 3.11.\nAgent: Noted, Ubuntu 22.04 and Python 3.11.",
            "expected_keywords": ["ubuntu 22.04", "python 3.11"],
            "category": "environment"
        })
    for i in range(5):
        samples.append({
            "id": f"long_{i}",
            "transcript": f"User: Welcome back.\nAgent: Hello! Ready to continue?\nUser: Yes. Previously we set up the Redis cache. Today let's add rate limiting.\nAgent: Sounds good. Standard sliding window?\nUser: Yes. But note that our Redis instance is hosted on AWS ElastiCache, not local. Also, my API keys are stored in AWS Secrets Manager. Don't use .env files.\nAgent: Okay, AWS ElastiCache for Redis, and AWS Secrets Manager for keys.",
            "expected_keywords": ["redis", "rate limiting", "aws elasticache", "aws secrets manager", ".env"],
            "category": "long_multi"
        })
    return samples

def call_sarvam(prompt_system, prompt_user):
    for attempt in range(3):
        try:
            res = requests.post(
                URL,
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": MODEL,
                    "messages": [{"role": "system", "content": prompt_system}, {"role": "user", "content": prompt_user}],
                    "temperature": 0.0
                },
                timeout=30
            )
            data = res.json()
            if 'usage' in data: return data
            elif res.status_code == 429: time.sleep(2 ** attempt); continue
            else: print(f"API Error: {data}"); time.sleep(1)
        except Exception as e:
            print(f"Request failed: {e}"); time.sleep(1)
    return None

def parse_json_response(content):
    content = content.strip()
    if content.startswith("```json"): content = content[7:]
    if content.startswith("```"): content = content[3:]
    if content.endswith("```"): content = content[:-3]
    try: return json.loads(content.strip())
    except: return []

def evaluate_extraction(memories, expected_keywords, text_key="text"):
    if not expected_keywords: return 1.0
    combined_text = " ".join([str(m.get(text_key, "")).lower() for m in memories])
    hits = sum(1 for kw in expected_keywords if kw.lower() in combined_text)
    return hits / len(expected_keywords)

def main():
    dataset = generate_dataset()
    
    # Load V1 results
    with open("cognicore_bench/benchmark_results.json", "r") as f:
        v1_results = json.load(f)
    v1_map = {r["id"]: r for r in v1_results}
    
    v2_results = []
    print(f"Running V2 benchmark on {len(dataset)} samples...")
    for i, sample in enumerate(dataset):
        v1_data = v1_map.get(sample["id"])
        if not v1_data: continue
        
        opt_transcript = compress_transcript_safe(sample["transcript"])
        opt_resp = call_sarvam(V2_SYSTEM_PROMPT, opt_transcript)
        if not opt_resp: continue
        
        opt_content = opt_resp['choices'][0]['message']['content']
        opt_mems = parse_json_response(opt_content)
        opt_recall = evaluate_extraction(opt_mems, sample["expected_keywords"], text_key="text")
        
        o_usage = opt_resp['usage']
        
        result = {
            "id": sample["id"],
            "category": sample["category"],
            "expected_keywords": sample["expected_keywords"],
            "baseline": v1_data["baseline"],
            "v1": v1_data["optimized"],
            "v2": {
                "prompt_tokens": o_usage["prompt_tokens"],
                "completion_tokens": o_usage["completion_tokens"],
                "total_tokens": o_usage["total_tokens"],
                "recall": opt_recall,
                "extracted": opt_mems
            },
            "regression_from_baseline": opt_recall < v1_data["baseline"]["recall"]
        }
        v2_results.append(result)
        time.sleep(0.5)

    with open("cognicore_bench/benchmark_results_v2.json", "w") as f:
        json.dump(v2_results, f, indent=2)
        
    avg_b_recall = sum(r["baseline"]["recall"] for r in v2_results) / len(v2_results)
    avg_v1_recall = sum(r["v1"]["recall"] for r in v2_results) / len(v2_results)
    avg_v2_recall = sum(r["v2"]["recall"] for r in v2_results) / len(v2_results)
    
    b_total = sum(r["baseline"]["total_tokens"] for r in v2_results)
    v1_total = sum(r["v1"]["total_tokens"] for r in v2_results)
    v2_total = sum(r["v2"]["total_tokens"] for r in v2_results)
    
    v2_total_red = (b_total - v2_total) / b_total
    v1_total_red = (b_total - v1_total) / b_total
    
    regressions = [r for r in v2_results if r["regression_from_baseline"]]
    reg_categories = {}
    for r in regressions:
        reg_categories[r["category"]] = reg_categories.get(r["category"], 0) + 1
        
    report = f"""# CogniCore Sarvam AI Memory Extraction Benchmark - V2

## V2 Prompt Enhancements
- Restored output keys back to standard `"text"` and `"memory_type"` (CogniCore compatible)
- Explicitly requested: *facts, rules, preferences, constraints, successful solutions, and failed approaches*
- Safe compression: `User:` -> `U:`, `Agent:` -> `A:`, stripped blank lines (preserved all text/negations).

## Aggregate Token Reductions (Across {len(v2_results)} samples)
- **Baseline Total Tokens**: {b_total}
- **V1 Total Tokens**: {v1_total} (Reduction: {v1_total_red:.1%})
- **V2 Total Tokens**: {v2_total} (Reduction: {v2_total_red:.1%})

## Memory Quality Metrics
- **Baseline Average Recall**: {avg_b_recall:.1%}
- **V1 Optimized Average Recall**: {avg_v1_recall:.1%}
- **V2 Optimized Average Recall**: {avg_v2_recall:.1%}
- **Total V2 Regressions**: {len(regressions)} out of {len(v2_results)} samples

### Regressions by Category
"""
    if not reg_categories:
        report += "None! V2 successfully matches baseline recall across the board.\\n"
    else:
        for cat, count in reg_categories.items():
            report += f"- **{cat}**: {count} regression(s)\\n"
            
        report += "\\n### Regression Deep-Dive\\n"
        for reg in regressions:
            report += f"- Sample `{reg['id']}` ({reg['category']}): Baseline {reg['baseline']['recall']:.1%} -> V2 {reg['v2']['recall']:.1%}\\n"
            report += f"  - Expected: {reg['expected_keywords']}\\n"
            report += f"  - V2 Output: {json.dumps(reg['v2']['extracted'])}\\n"
            
    with open("cognicore_bench/sarvam_benchmark_report_v2.md", "w", encoding="utf-8") as f:
        f.write(report)
        
    print("V2 Benchmark complete. Reports generated.")

if __name__ == "__main__":
    main()
