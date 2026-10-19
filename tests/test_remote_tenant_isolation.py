"""On the hosted server, one signed-in user must not read or write another user's memory.

Users are identified by their GitHub account (``github:<id>``), and GitHub ids are
public, so any tool that takes another user's id is a potential cross-account path.
"""
import json
import time
from types import SimpleNamespace

import jwt
import pytest

from cognicore.connectors import remote

ALICE, BOB = "github:1001", "github:2002"


def _ctx(user_id):
    """An MCP request context as the hosted server sees it: a signed-in HTTP request."""
    token = jwt.encode(
        {"sub": user_id, "typ": "access", "exp": int(time.time()) + 600},
        remote.JWT_SECRET, algorithm=remote.JWT_ALGORITHM,
    )
    request = SimpleNamespace(headers={"Authorization": f"Bearer {token}"}, query_params={})
    return SimpleNamespace(request_context=SimpleNamespace(request=request, meta=None))


def _memories(user_id):
    return [r.entry.text for r in remote.get_backend(_ctx(user_id)).search(query="", top_k=1000, scope=None)]


@pytest.fixture(autouse=True)
def hosted_server(tmp_path, monkeypatch):
    monkeypatch.setenv("COGNICORE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COGNICORE_USE_SEMANTIC", "0")
    monkeypatch.delenv("COGNICORE_DB_PATH", raising=False)
    for cache in ("_commerce_db_path", "_agent_registry", "_transaction_ledger", "_reputation_engine"):
        if hasattr(remote, cache):
            monkeypatch.setattr(remote, cache, None)


def test_purchase_requires_seller_to_have_listed():
    remote.cognicore_remember("Alice's private API design notes", _ctx(ALICE), category="secret")
    remote.cognicore_reputation(_ctx(ALICE))  # read-only call that registers Alice

    result = json.loads(remote.cognicore_purchase_memory(_ctx(BOB), seller_agent_id=ALICE))

    assert "not listed" in result["error"]
    assert not any("Alice's private" in text for text in _memories(BOB))


def test_purchase_works_after_seller_opts_in():
    remote.cognicore_remember("Alice's published deployment checklist", _ctx(ALICE), category="ops")
    remote.cognicore_list_for_sale(_ctx(ALICE))

    result = json.loads(remote.cognicore_purchase_memory(_ctx(BOB), seller_agent_id=ALICE, max_price_usd=1000))

    assert "error" not in result
    assert any("deployment checklist" in text for text in _memories(BOB))


def test_share_into_another_users_memory_is_refused():
    before = _memories(ALICE)

    result = json.loads(remote.cognicore_share_experience(query="auth", target_agent_id=ALICE, ctx=_ctx(BOB)))

    assert result["status"] == "refused"
    assert _memories(ALICE) == before


def test_share_within_own_account_is_allowed():
    result = json.loads(remote.cognicore_share_experience(query="auth", target_agent_id=BOB, ctx=_ctx(BOB)))
    assert result["status"] == "transferred"


def test_fabric_tools_run_per_user():
    # These called an undefined _get_backend() and failed on every call.
    out = remote.cognicore_fabric_recommend(_ctx(ALICE), tool_name="figma", task="pick a palette")
    assert "recommendations" in json.loads(out)
