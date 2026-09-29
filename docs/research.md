# Research & Built-in Environments

## Built-in Environments (62 total)

```python
import cognicore
for env in cognicore.list_envs():
    print(env["id"])
```

| Category | Examples | What it tests |
|---|---|---|
| **Safety** | SafetyClassification, RealWorldSafety | Classify AI outputs as SAFE / UNSAFE |
| **Code** | CodeDebugging, RealWorldCodeBugs | Find and fix bugs in Python |
| **Planning** | Planning, WorkflowAgent | Multi-step task execution |
| **Reasoning** | MathReasoning, Summarization | Arithmetic, algebra, summarization |
| **RL** | GridWorld, MazeRunner, Trading | Classic RL problems |
| **Multi-Agent** | MultiAgent, NPCSimulation | Coordination and negotiation |

All environments support `difficulty="easy"`, `"medium"`, or `"hard"`.

## 🤖 NEXUS — Autonomous Coding Agent

Give NEXUS a bug description. It reads the code, writes a fix, runs tests, and (optionally) opens a PR.

```python
from cognicore.nexus.autonomous import NexusRunner

runner = NexusRunner(max_attempts=3)
result = runner.solve(
    "Fix crash when content is None in detect_encoding",
    repo_path=".",
    auto_pr=False
)

print(f"Solved: {result.solved}")
print(f"Tests:  {result.tests_passed} passed / {result.tests_failed} failed")
```

Requires `OPENROUTER_API_KEY`. Start the live dashboard with:

```bash
python -m cognicore.nexus.live_server
# Open http://localhost:8420
```
