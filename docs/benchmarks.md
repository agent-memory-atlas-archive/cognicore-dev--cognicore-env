# Benchmarks

## LongMemEval

LongMemEval tests how well an agent can recall facts that are scattered across many past conversations — not just recent ones. It's the hardest memory benchmark because the answer requires **combining evidence from multiple separate sessions**.

### How CogniCore solves it — Multi-Hop Adapter

Most retrieval systems grab the top-N most similar chunks and stop. That fails when the answer is split across chunks that don't individually look relevant.

CogniCore's **Multi-Hop Adapter** works differently:

1. **Extract targets** — pull key names and entities from the query
2. **Hop-1 retrieval** — find the most relevant anchor chunks
3. **Graph traversal** — follow session-ID and time links to find connected chunks the first hop missed
4. **Coverage selection** — pick the set of chunks that together cover the most entities — not just the highest individual scores

### Results (STRICT R@5)

| Context window | Baseline (ZeroShot) | CogniCore Multi-Hop | Gain |
|:---:|:---:|:---:|:---:|
| **5 chunks** | 78.8% | **85.2%** | **+6.4%** 🚀 |
| **10 chunks** | 87.2% | **92.8%** | **+5.6%** 🚀 |
| **20 chunks** | 95.0% | 95.0% | — (brute force catches up) |

At small window sizes — where token efficiency matters — the Multi-Hop Adapter clearly wins by reconstructing dispersed evidence instead of hoping it all fits in one chunk.

Run the benchmark yourself:

```bash
python cognicore_benchmarks/longmemeval/runner.py
```
