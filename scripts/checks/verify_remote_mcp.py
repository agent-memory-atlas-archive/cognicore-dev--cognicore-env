"""Verify a deployed CogniCore remote MCP server is ready for Claude connectors.

Checks everything Claude needs before a user signs in: health, the 401 that
starts OAuth, protected-resource metadata for both transports, authorization
server metadata, and dynamic client registration with Claude's callback URLs.
Sign-in itself needs a browser: add the server as a custom connector in Claude.

Usage:
    python scripts/checks/verify_remote_mcp.py https://mcp.cognicoree.tech
"""
import json
import ssl
import sys
import urllib.error
import urllib.request

try:  # certifi's CA bundle avoids stale OS certificate stores (common on Windows)
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://mcp.cognicoree.tech").rstrip("/")
failures = 0


def request(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
        "User-Agent": "cognicore-verify",
    })
    try:
        with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as resp:  # nosec B310
            return resp.status, dict(resp.headers), resp.read(4096).decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), err.read(4096).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as err:
        return 0, {}, f"connection failed: {getattr(err, 'reason', err)}"


def check(name, ok, detail=""):
    global failures
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


status, _, body = request("GET", "/health")
check("GET /health", status == 200, f"HTTP {status} {body[:60]}")

for path in ("/mcp/stream", "/mcp/sse"):
    status, headers, _ = request("POST" if path.endswith("stream") else "GET", path, {} if path.endswith("stream") else None)
    challenge = {k.lower(): v for k, v in headers.items()}.get("www-authenticate", "")
    expected = f'Bearer resource_metadata="{BASE}/.well-known/oauth-protected-resource{path}"'
    check(f"{path} without a token -> 401 pointing at metadata", status == 401 and challenge == expected,
          f"HTTP {status}, WWW-Authenticate: {challenge or 'missing'}")
    status, _, body = request("GET", f"/.well-known/oauth-protected-resource{path}")
    prm = json.loads(body) if status == 200 else {}
    check(f"protected-resource metadata for {path}", prm.get("resource") == BASE + path
          and (prm.get("authorization_servers") or [None])[0] == BASE, f"HTTP {status} {body[:90]}")

status, _, body = request("GET", "/.well-known/oauth-authorization-server")
meta = json.loads(body) if status == 200 else {}
check("authorization server metadata", status == 200 and meta.get("issuer") == BASE
      and meta.get("code_challenge_methods_supported") == ["S256"]
      and meta.get("registration_endpoint") == f"{BASE}/register",
      f"HTTP {status}, issuer={meta.get('issuer')} (must equal {BASE}; set COGNICORE_PUBLIC_URL)")

for callback in ("https://claude.ai/api/mcp/auth_callback", "http://localhost:33418/callback"):
    status, _, body = request("POST", "/register", {"redirect_uris": [callback], "client_name": "verify"})
    check(f"client registration accepts {callback}", status == 201, f"HTTP {status} {body[:80]}")

print()
if failures:
    print(f"{failures} check(s) failed. Fix these before adding the connector in Claude.")
    sys.exit(1)
print("All checks passed. Next: add the connector in Claude and sign in with GitHub.")
