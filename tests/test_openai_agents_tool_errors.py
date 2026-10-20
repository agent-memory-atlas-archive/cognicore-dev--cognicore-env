"""What the model sees when a CogniCore tool fails in the OpenAI Agents SDK.

The exception text must not reach the model (it can contain paths and
internals), memory failures must not invite retry loops, and a failed threat
scan must never read as a clean one.
"""
import asyncio
import json

import pytest

from cognicore.integrations import openai_agents as oa

SECRET = "internal detail /srv/data/memory.db"
MEMORY_TOOLS = {
    "remember_outcome": {"text": "t"},
    "recall_context": {"query": "q"},
    "recall_failures": {},
    "reflect_on_category": {"category": "c"},
}


def test_memory_error_hides_details_and_says_not_to_retry():
    msg = oa._memory_tool_error(None, RuntimeError(SECRET))
    assert SECRET not in msg
    assert "Do not retry" in msg


def test_failed_threat_scan_is_not_treated_as_safe():
    msg = oa._threat_scan_error(None, RuntimeError(SECRET))
    assert SECRET not in msg
    assert "untrusted" in msg
    assert "SAFE" not in msg


@pytest.mark.parametrize("name, args", [*MEMORY_TOOLS.items(), ("scan_for_threats", {"text": "hi"})])
def test_sdk_returns_our_message_when_a_tool_fails(name, args, monkeypatch):
    pytest.importorskip("agents")
    from agents.tool_context import ToolContext

    def boom():
        raise RuntimeError(SECRET)

    for getter in ("_get_runtime", "_get_semantic_memory", "_get_threat_detector"):
        monkeypatch.setattr(oa, getter, boom)

    tool = getattr(oa, name)
    payload = json.dumps(args)
    ctx = ToolContext(context=None, tool_name=name, tool_call_id="1", tool_arguments=payload)
    out = asyncio.run(tool.on_invoke_tool(ctx, payload))

    expected = oa._threat_scan_error if name == "scan_for_threats" else oa._memory_tool_error
    assert out == expected(None, RuntimeError(SECRET))
