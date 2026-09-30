# Agents & Integrations

## No API key needed

```python
agent = cognicore.AutoLearner()            # rule-based, fast, ~99% accuracy with memory
agent = cognicore.QLearningAgent(actions=["SAFE", "UNSAFE"])
agent = cognicore.RandomAgent(actions=["SAFE", "UNSAFE"])
```

## LLM agents (API key required)

```python
agent = cognicore.ClaudeAgent(model="claude-sonnet-4-20250514")
agent = cognicore.GeminiAgent(model="gemini-2.0-flash")
agent = cognicore.OpenAIAgent(model="gpt-4o-mini")
agent = cognicore.OllamaAgent(model="llama3")   # local, no API key
```

## ML agents (needs `pip install cognicore-env[rl]`)

```python
agent = cognicore.DeepQAgent(state_dim=10, actions=["SAFE", "UNSAFE"])
agent = cognicore.PolicyGradientAgent(state_dim=10, actions=["SAFE", "UNSAFE"])
```

## API Keys

Keys are **only needed** for LLM agents and NEXUS. Everything else works without them.

```bash
# Linux / macOS
export OPENROUTER_API_KEY="your-key"
export GITHUB_TOKEN="ghp_your-token"
```

```powershell
# Windows (PowerShell)
$env:OPENROUTER_API_KEY = "your-key"
$env:GITHUB_TOKEN = "ghp_your-token"
```

## Claude Plugin (Memory for Claude)

CogniCore includes a **Claude plugin** that gives Claude persistent memory across conversations.

👉 See [`plugins/cognicore-memory/README.md`](../plugins/cognicore-memory/README.md) for setup instructions.
