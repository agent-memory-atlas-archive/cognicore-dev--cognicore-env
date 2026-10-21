"""Hardening of the hosted MCP server: rate limits, header-only tokens, terse errors."""
import time

import jwt
import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from cognicore.connectors import remote


def _access_token(sub):
    return jwt.encode(
        {"sub": sub, "typ": "access", "exp": int(time.time()) + 600},
        remote.JWT_SECRET, algorithm=remote.JWT_ALGORITHM,
    )


# ── Tokens only in the Authorization header ──────────────────────────────────

def test_token_in_url_is_not_accepted():
    # A valid token passed as ?token= must be refused: URLs end up in logs.
    client = TestClient(remote.app)
    response = client.get(f"/mcp/sse?token={_access_token('github:1')}")
    assert response.status_code == 401


# ── Errors reveal nothing about the request or why a token failed ────────────

@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer not-a-jwt"},
    {"Authorization": f"Bearer {jwt.encode({'sub': 'x'}, 'wrong-secret', algorithm='HS256')}"},
])
def test_unauthorized_response_is_terse(headers):
    response = TestClient(remote.app).post("/mcp/stream", headers={**headers, "X-Probe": "1"})
    assert response.status_code == 401
    assert response.text in ("Authentication required.", "Invalid or expired token.")
    for leak in ("x-probe", "user-agent", "JWT", "Signature", "Debug"):
        assert leak.lower() not in response.text.lower()
    # Clients still need this header to start the sign-in flow.
    assert "resource_metadata" in response.headers["www-authenticate"]


# ── Rate limiting ──────────────────────────────────────────────────────────────

def _limited_client(user_per_minute=3, ip_per_minute=2):
    async def ok(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/{path:path}", ok, methods=["GET", "POST", "OPTIONS"])])
    return TestClient(remote.RateLimitMiddleware(app, user_per_minute=user_per_minute, ip_per_minute=ip_per_minute))


def _codes(client, n, path="/mcp/stream", method="GET", headers=None):
    return [client.request(method, path, headers=headers or {}).status_code for _ in range(n)]


def test_unauthenticated_requests_are_limited_per_ip():
    client = _limited_client(ip_per_minute=2)
    assert _codes(client, 3) == [200, 200, 429]


def test_limited_response_says_when_to_retry():
    client = _limited_client(ip_per_minute=1)
    client.get("/mcp/stream")
    response = client.get("/mcp/stream")
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) >= 1


def test_forwarded_for_is_ignored():
    # Clients can write X-Forwarded-For, and on Railway its entries vary per request.
    client = _limited_client(ip_per_minute=2)
    codes = [client.get("/mcp/stream", headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code for i in range(3)]
    assert codes == [200, 200, 429]


def test_limit_is_per_real_ip():
    client = _limited_client(ip_per_minute=1)
    assert client.get("/mcp/stream", headers={"X-Real-IP": "203.0.113.7"}).status_code == 200
    assert client.get("/mcp/stream", headers={"X-Real-IP": "203.0.113.7"}).status_code == 429
    assert client.get("/mcp/stream", headers={"X-Real-IP": "203.0.113.8"}).status_code == 200


def test_signed_in_users_are_limited_per_user_not_per_ip():
    # Claude and ChatGPT call from shared IPs; one heavy user must not block another.
    client = _limited_client(user_per_minute=2, ip_per_minute=1)
    alice = {"Authorization": f"Bearer {_access_token('github:1')}", "X-Real-IP": "198.51.100.1"}
    bob = {"Authorization": f"Bearer {_access_token('github:2')}", "X-Real-IP": "198.51.100.1"}
    assert _codes(client, 3, headers=alice) == [200, 200, 429]
    assert _codes(client, 2, headers=bob) == [200, 200]


def test_invalid_token_is_counted_per_ip():
    client = _limited_client(user_per_minute=100, ip_per_minute=2)
    forged = {"Authorization": "Bearer forged.token.value"}
    assert _codes(client, 3, headers=forged) == [200, 200, 429]


def test_health_and_preflight_are_never_limited():
    client = _limited_client(ip_per_minute=1)
    assert _codes(client, 3, path="/health") == [200, 200, 200]
    assert _codes(client, 3, method="OPTIONS") == [200, 200, 200]


def test_zero_turns_the_limit_off():
    client = _limited_client(ip_per_minute=0)
    assert set(_codes(client, 5)) == {200}


def test_budget_refills_over_time(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(remote._time, "monotonic", lambda: clock[0])
    client = _limited_client(ip_per_minute=60)  # one request per second
    assert _codes(client, 61) == [200] * 60 + [429]
    clock[0] += 1.0
    assert client.get("/mcp/stream").status_code == 200
