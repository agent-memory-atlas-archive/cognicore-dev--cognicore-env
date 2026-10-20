"""
CogniCore framework integrations.

  - LangChain:     cognicore.integrations.langchain
  - CrewAI:        cognicore.integrations.crewai
  - OpenAI Agents: cognicore.integrations.openai_agents
  - mem0:          cognicore.integrations.mem0
  - Hugging Face:  cognicore.integrations.huggingface
  - Claude Code:   cognicore.integrations.claude_code

The NEXUS triggers (GitHub issues, CI, Slack, Linear, schedules, webhooks) moved
to ``cognicore.nexus.triggers``, and the hosted MCP servers (ChatGPT, Claude) to
``cognicore.connectors``. Their old paths here still work, and the names below
are still exported from this package.
"""
from cognicore.nexus.triggers.task_queue import NexusTask, NexusTaskQueue, TaskSource, TaskPriority
from cognicore.fabric.plugins.elevenlabs import ElevenLabsIntegration

__all__ = [
    "NexusTask", "NexusTaskQueue", "TaskSource", "TaskPriority",
    "ElevenLabsIntegration",
]

# Keep old submodule paths such as cognicore.integrations.task_queue available
# as attributes; see cognicore/_compat.py.
from cognicore._compat import alias_loaded as _alias_loaded

_alias_loaded()
