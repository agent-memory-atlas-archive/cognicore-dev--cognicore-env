# Benchmarks

Benchmark harnesses and experiment scripts. Run them from the repository root.
Results go to `results/`, `benchmark_output/` or `experiments/`, which are git-ignored.

| Path | What it is |
|---|---|
| [`longmemeval/`](longmemeval/) | LongMemEval runner, adapters (baseline, zero-shot, multi-hop, ...), evaluator and metrics |
| [`longmemeval/analysis/`](longmemeval/analysis/) | Ablation and multi-hop analysis scripts, with their result write-ups |
| [`data/`](data/) | Dataset download scripts (`data/longmemeval/download_datasets.py`) |
| [`common/`](common/) | Shared runner, evaluator and LLM client |
| [`reproducible/`](reproducible/) | Prints the LongMemEval methodology report (dataset, config, commands, results) |
| [`agent_learning/`](agent_learning/) | Agent-learning experiments: task generators, sandboxes, evaluation arms, Sarvam benchmarks |
| `*.py` | Standalone benchmarks: memory strength, head-to-head, scaling, reranking, experience transfer |

```bash
python benchmarks/data/longmemeval/download_datasets.py
python benchmarks/longmemeval/runner.py --help
```

The regression suite used by `make bench` and CI is part of the package, in
[`cognicore/benchmarks/`](../cognicore/benchmarks/).
