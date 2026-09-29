# CogniCore Memory

Store anything. Retrieve it later by meaning, not just exact keywords.

```python
import cognicore

memory = cognicore.Memory(max_size=10000)
memory.store({"category": "crash", "fix": "add null check", "correct": True})

context = memory.get_context("crash", top_k=3)
```

See the Quickstart on the README for more information.
