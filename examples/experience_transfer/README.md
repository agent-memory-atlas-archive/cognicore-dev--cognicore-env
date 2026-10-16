# CogniCore Experience Transfer Demos

This directory contains the core sequence of demonstrations illustrating the fundamental value proposition of CogniCore: **"Agents don't share conversations. They share experience."**

These demos use the **real CogniCore `SQLiteMemoryBackend` engine** to store, retrieve, filter, and verify memories across independent sessions. The LLM outputs are mocked to ensure reliable, fast, and repeatable execution for videos/screen recordings.

---

### 1. The Killer Moment
**What it demonstrates:** A new agent completely skipping failed coding approaches because a previous agent in a different session already tried and failed them.
- **Command:** `python demo_1_killer_moment.py`
- **Expected Output:** Agent B encounters the JWT bug, retrieves the failures and success from CogniCore, and states it will skip the failures to use the verified fix.
- **Real vs Simulated:** SQLite database and search retrieval are 100% real. Agent outputs are mock text.

### 2. Verification Guard
**What it demonstrates:** How CogniCore prevents a "lucky fix" from becoming bad doctrine. When the Python/FastAPI environment changes, the previous experience is flagged for independent verification.
- **Command:** `python demo_2_verification_guard.py`
- **Expected Output:** CogniCore detects an environment mismatch (Python 3.11 -> 3.13) and flags the retrieved experience with `Compatibility: LOW`, requiring Agent B to independently verify it.

### 3. Failure Transfer
**What it demonstrates:** Often, knowing what *not* to do is more valuable than a direct answer. 
- **Command:** `python demo_3_failure_transfer.py`
- **Expected Output:** Agent A records a failure with a stateful Singleton pattern. Agent B avoids the Singleton entirely based on the retrieved failure.

### 4. Memory Supersession
**What it demonstrates:** Experience lifecycle. When a dependency updates (Pydantic v1 to v2) and a previously verified experience fails, a new experience correctly supersedes the old one.
- **Command:** `python demo_4_supersession.py`
- **Expected Output:** Agent B fails using Experience A (v1 approach), creates Experience B (v2 approach), and explicitly marks Experience A as superseded. Agent C subsequently retrieves Experience B.

### 5. Cross-Model Integrations
**What it demonstrates:** Real cross-pollination between different model families.
- **Command:** `python demo_5_integrations.py`
- **Expected Output:** Claude learns an algorithmic optimization and Codex later retrieves it via CogniCore.
- **Real vs Simulated:** Agent API calls are mocked. To attempt live API calls (requires credentials in environment variables), run:
  `python demo_5_integrations.py --live`
