"""OAuth 2.1 authorization server for the remote MCP server, with GitHub sign-in.

Claude (claude.ai, Desktop, mobile, Claude Code) connects to a remote MCP server
through OAuth: it reads protected-resource metadata, registers itself with
Dynamic Client Registration, sends the user to ``/authorize`` with PKCE, and
exchanges the code at ``/token``. This module implements that server side and
delegates the actual sign-in to GitHub, so every user gets a stable, distinct
identity (``github:<numeric id>``) without running a user database.

Everything is stateless except a small in-memory set of consumed code and
refresh-token IDs. Requests, codes and tokens are JWTs signed with the server's
``COGNICORE_JWT_SECRET`` and told apart by their ``typ`` claim. The GitHub
access token is used once to read the user's ID and is never stored.

Enabled when ``GITHUB_CLIENT_ID`` and ``GITHUB_CLIENT_SECRET`` are set.
``COGNICORE_PUBLIC_URL`` should be set to the server's public origin
(e.g. ``https://mcp.example.com``) so the issuer is stable behind proxies.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
from typing import Any

import jwt
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.formparsers import MultiPartException

ACCESS_TOKEN_TTL = 3600
REFRESH_TOKEN_TTL = 30 * 24 * 3600
CODE_TTL = 300
REQUEST_TTL = 600

SCOPES = ["mcp", "offline_access"]
NONCE_COOKIE = "cognicore_oauth_nonce"
CALLBACK_PATH = "/oauth/github/callback"

# Redirect URIs Claude uses. Claude Code uses an RFC 8252 loopback redirect on
# an ephemeral port, accepted separately below.
CLAUDE_REDIRECT_URIS = {
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
}
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

# MCP endpoints a user can enter as the connector URL. Protected-resource
# metadata must name the exact URL the user entered.
SSE_RESOURCE_PATH = "/mcp/sse"
STREAM_RESOURCE_PATH = "/mcp/stream"


def github_enabled() -> bool:
    return bool(os.environ.get("GITHUB_CLIENT_ID") and os.environ.get("GITHUB_CLIENT_SECRET"))


def _github_oauth_base() -> str:
    return os.environ.get("COGNICORE_GITHUB_OAUTH_BASE", "https://github.com").rstrip("/")


def _github_api_base() -> str:
    return os.environ.get("COGNICORE_GITHUB_API_BASE", "https://api.github.com").rstrip("/")


def base_url_from_headers(headers: dict[str, str], scheme: str, host: str) -> str:
    """Public origin of this server: COGNICORE_PUBLIC_URL, else proxy headers, else the request."""
    configured = os.environ.get("COGNICORE_PUBLIC_URL", "").strip().rstrip("/")
    if configured:
        return configured
    proto = headers.get("x-forwarded-proto", scheme).split(",")[0].strip()
    fwd_host = headers.get("x-forwarded-host", host).split(",")[0].strip()
    return f"{proto}://{fwd_host}"


def base_url(request: Request) -> str:
    return base_url_from_headers(
        {k.lower(): v for k, v in request.headers.items()},
        request.url.scheme,
        request.headers.get("host", request.url.netloc),
    )


def base_url_from_scope(scope: dict[str, Any]) -> str:
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    server = scope.get("server") or ("localhost", 80)
    host = headers.get("host") or f"{server[0]}:{server[1]}"
    return base_url_from_headers(headers, scope.get("scheme", "http"), host)


def resource_path_for(request_path: str) -> str:
    """The connector URL path a request belongs to, for the WWW-Authenticate pointer."""
    if request_path.startswith(STREAM_RESOURCE_PATH):
        return STREAM_RESOURCE_PATH
    return SSE_RESOURCE_PATH


def www_authenticate(base: str, request_path: str) -> str:
    resource = resource_path_for(request_path)
    return f'Bearer resource_metadata="{base}/.well-known/oauth-protected-resource{resource}"'


def redirect_uri_allowed(uri: str) -> bool:
    if not uri:
        return False
    extra = {u.strip() for u in os.environ.get("COGNICORE_EXTRA_REDIRECT_URIS", "").split(",") if u.strip()}
    if uri in CLAUDE_REDIRECT_URIS or uri in extra:
        return True
    parsed = urllib.parse.urlparse(uri)
    # RFC 8252 loopback redirect: any port, matched for localhost and 127.0.0.1.
    return parsed.scheme == "http" and parsed.hostname in LOOPBACK_HOSTS


def is_access_token_payload(payload: dict[str, Any]) -> bool:
    """Access tokens are untyped (legacy) or typ=access. Codes, refresh tokens and
    request blobs are signed with the same key and must never authenticate a call."""
    return payload.get("typ") in (None, "access")


def _pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _with_query(uri: str, params: dict[str, str]) -> str:
    sep = "&" if urllib.parse.urlparse(uri).query else "?"
    return f"{uri}{sep}{urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})}"


def _oauth_error(error: str, description: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": error, "error_description": description},
        status_code=status,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _error_page(message: str, status: int = 400) -> HTMLResponse:
    body = f"""<!doctype html><meta charset="utf-8"><title>CogniCore sign-in</title>
<body style="font-family:system-ui;max-width:32rem;margin:4rem auto;padding:0 1rem">
<h1 style="font-size:1.25rem">Sign-in could not continue</h1><p>{html.escape(message)}</p></body>"""
    return HTMLResponse(body, status_code=status)


def _http_json(url: str, data: dict[str, str] | None = None, token: str | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": "CogniCore-MCP"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers)  # nosec B310
    with urllib.request.urlopen(req, timeout=8) as resp:  # nosec B310
        return json.loads(resp.read().decode("utf-8"))


class GitHubOAuthServer:
    """Stateless OAuth 2.1 authorization server backed by GitHub sign-in."""

    def __init__(self, secret: str, algorithm: str = "HS256"):
        self._secret = secret
        self._algorithm = algorithm
        self._consumed: dict[str, float] = {}

    # -- signing ---------------------------------------------------------------

    def _sign(self, typ: str, ttl: int, **claims: Any) -> str:
        now = int(time.time())
        payload = {"typ": typ, "iat": now, "exp": now + ttl, **claims}
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def _verify(self, token: str, typ: str) -> dict[str, Any] | None:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.InvalidTokenError:
            return None
        return payload if payload.get("typ") == typ else None

    def _consume(self, jti: str, exp: float) -> bool:
        """Mark a one-time ID used. Returns False if it was already used."""
        now = time.time()
        for key in [k for k, v in self._consumed.items() if v < now]:
            del self._consumed[key]
        if jti in self._consumed:
            return False
        self._consumed[jti] = exp
        return True

    # -- discovery -------------------------------------------------------------

    def protected_resource_metadata(self, request: Request, resource_path: str) -> JSONResponse:
        base = base_url(request)
        return JSONResponse({
            "resource": f"{base}{resource_path}",
            "authorization_servers": [base],
            "bearer_methods_supported": ["header"],
            "scopes_supported": ["mcp"],
            "resource_name": "CogniCore Memory",
        })

    def authorization_server_metadata(self, request: Request) -> JSONResponse:
        base = base_url(request)
        return JSONResponse({
            "issuer": base,
            "authorization_endpoint": f"{base}/authorize",
            "token_endpoint": f"{base}/token",
            "registration_endpoint": f"{base}/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": SCOPES,
            "authorization_response_iss_parameter_supported": True,
        })

    # -- dynamic client registration (RFC 7591) --------------------------------

    async def register(self, request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        redirect_uris = body.get("redirect_uris") or []
        if not isinstance(redirect_uris, list) or not redirect_uris:
            return _oauth_error("invalid_redirect_uri", "redirect_uris is required")
        bad = [u for u in redirect_uris if not isinstance(u, str) or not redirect_uri_allowed(u)]
        if bad:
            return _oauth_error("invalid_redirect_uri", f"redirect URI not allowed: {bad[0]}")
        return JSONResponse({
            "client_id": f"cognicore_{secrets.token_urlsafe(16)}",
            "client_id_issued_at": int(time.time()),
            "client_name": body.get("client_name", "MCP client"),
            "redirect_uris": redirect_uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }, status_code=201)

    # -- authorization ---------------------------------------------------------

    def authorize(self, request: Request):
        q = request.query_params
        client_id = q.get("client_id", "")
        redirect_uri = q.get("redirect_uri", "")
        state = q.get("state")
        # Never redirect to an unvalidated URI: report these problems on our own page.
        if not client_id:
            return _error_page("The request is missing client_id.")
        if not redirect_uri_allowed(redirect_uri):
            return _error_page("The application asked to return to an address this server does not allow.")
        if q.get("response_type") != "code":
            return RedirectResponse(_with_query(redirect_uri, {"error": "unsupported_response_type", "state": state}), 302)
        challenge = q.get("code_challenge", "")
        if not challenge or q.get("code_challenge_method") != "S256":
            return RedirectResponse(_with_query(redirect_uri, {
                "error": "invalid_request",
                "error_description": "PKCE with code_challenge_method=S256 is required",
                "state": state,
            }), 302)

        auth_request = self._sign(
            "authreq", REQUEST_TTL,
            client_id=client_id, redirect_uri=redirect_uri, code_challenge=challenge,
            state=state, scope=q.get("scope", ""), resource=q.get("resource", ""),
        )
        target = urllib.parse.urlparse(redirect_uri)
        loopback = target.hostname in LOOPBACK_HOSTS
        app_name = "Claude Code on this computer" if loopback else (target.hostname or "an application")
        warning = (
            "<p style='color:#a15c00'>Only continue if you just started this connection from Claude Code. "
            "Any program on this computer can request a localhost sign-in.</p>" if loopback else ""
        )
        continue_url = f"/authorize/github?{urllib.parse.urlencode({'request': auth_request})}"
        body = f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Connect to CogniCore</title>
<body style="font-family:system-ui;max-width:32rem;margin:4rem auto;padding:0 1rem;line-height:1.5">
<h1 style="font-size:1.35rem">Connect {html.escape(app_name)} to CogniCore Memory</h1>
<p>You'll sign in with GitHub. CogniCore uses only your GitHub account ID to keep your memories separate
from other users, and returns you to <strong>{html.escape(target.netloc)}</strong>.</p>{warning}
<p><a href="{html.escape(continue_url)}" style="display:inline-block;padding:.6rem 1.1rem;background:#24292f;
color:#fff;border-radius:6px;text-decoration:none">Continue with GitHub</a></p></body>"""
        return HTMLResponse(body, headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"})

    def authorize_github(self, request: Request):
        auth_request = request.query_params.get("request", "")
        if not self._verify(auth_request, "authreq"):
            return _error_page("This sign-in link has expired. Start the connection again from Claude.")
        nonce = secrets.token_urlsafe(16)
        state = self._sign("ghstate", REQUEST_TTL, req=auth_request, nonce=nonce)
        url = f"{_github_oauth_base()}/login/oauth/authorize?" + urllib.parse.urlencode({
            "client_id": os.environ["GITHUB_CLIENT_ID"],
            "redirect_uri": f"{base_url(request)}{CALLBACK_PATH}",
            "state": state,
            "allow_signup": "true",
        })
        resp = RedirectResponse(url, 302)
        resp.set_cookie(
            NONCE_COOKIE, nonce, max_age=REQUEST_TTL, httponly=True, samesite="lax",
            secure=base_url(request).startswith("https://"), path="/oauth",
        )
        return resp

    async def github_callback(self, request: Request):
        q = request.query_params
        gh_state = self._verify(q.get("state", ""), "ghstate")
        if not gh_state:
            return _error_page("This sign-in has expired or was not started here. Start the connection again from Claude.")
        cookie = request.cookies.get(NONCE_COOKIE, "")
        if not cookie or not secrets.compare_digest(cookie, gh_state.get("nonce", "")):
            return _error_page("This sign-in was started in a different browser. Start the connection again from Claude.")
        auth_request = self._verify(gh_state.get("req", ""), "authreq")
        if not auth_request:
            return _error_page("This sign-in has expired. Start the connection again from Claude.")
        redirect_uri, client_state = auth_request["redirect_uri"], auth_request.get("state")

        if q.get("error") or not q.get("code"):
            return RedirectResponse(_with_query(redirect_uri, {
                "error": "access_denied", "error_description": q.get("error_description", "GitHub sign-in was cancelled"),
                "state": client_state,
            }), 302)

        try:
            token = await asyncio.to_thread(_http_json, f"{_github_oauth_base()}/login/oauth/access_token", {
                "client_id": os.environ["GITHUB_CLIENT_ID"],
                "client_secret": os.environ["GITHUB_CLIENT_SECRET"],
                "code": q["code"],
                "redirect_uri": f"{base_url(request)}{CALLBACK_PATH}",
            })
            gh_token = token.get("access_token")
            if not gh_token:
                raise ValueError(token.get("error_description") or token.get("error") or "no access_token")
            user = await asyncio.to_thread(_http_json, f"{_github_api_base()}/user", None, gh_token)
            github_id = user["id"]
        except (OSError, ValueError, KeyError) as exc:  # network, bad JSON, or unexpected GitHub response
            print(f"[OAUTH] GitHub sign-in failed: {exc}")
            return RedirectResponse(_with_query(redirect_uri, {
                "error": "server_error", "error_description": "GitHub sign-in failed", "state": client_state,
            }), 302)

        code = self._sign(
            "code", CODE_TTL, jti=secrets.token_urlsafe(16),
            sub=f"github:{github_id}", login=user.get("login", ""),
            client_id=auth_request["client_id"], redirect_uri=redirect_uri,
            code_challenge=auth_request["code_challenge"], scope=auth_request.get("scope", ""),
        )
        resp = RedirectResponse(_with_query(redirect_uri, {
            "code": code, "state": client_state, "iss": base_url(request),
        }), 302)
        resp.delete_cookie(NONCE_COOKIE, path="/oauth")
        return resp

    # -- token endpoint --------------------------------------------------------

    def _issue_tokens(self, sub: str, login: str, client_id: str, scope: str) -> JSONResponse:
        access = self._sign("access", ACCESS_TOKEN_TTL, sub=sub, login=login, client_id=client_id, scope=scope)
        refresh = self._sign(
            "refresh", REFRESH_TOKEN_TTL, jti=secrets.token_urlsafe(16),
            sub=sub, login=login, client_id=client_id, scope=scope,
        )
        return JSONResponse({
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_TTL,
            "refresh_token": refresh,
            "scope": scope or "mcp",
        }, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})

    async def token(self, request: Request) -> JSONResponse:
        content_type = request.headers.get("content-type", "")
        try:
            if "application/json" in content_type:
                form = await request.json()
            else:
                form = dict(await request.form())
        except (ValueError, MultiPartException):
            return _oauth_error("invalid_request", "could not parse request body")
        grant_type = form.get("grant_type", "")

        if grant_type == "authorization_code":
            code = self._verify(form.get("code", ""), "code")
            if not code:
                return _oauth_error("invalid_grant", "authorization code is invalid or expired")
            if form.get("redirect_uri") != code["redirect_uri"]:
                return _oauth_error("invalid_grant", "redirect_uri does not match the authorization request")
            if form.get("client_id") and form["client_id"] != code["client_id"]:
                return _oauth_error("invalid_grant", "client_id does not match the authorization request")
            verifier = form.get("code_verifier", "")
            if not verifier or not secrets.compare_digest(_pkce_s256(verifier), code["code_challenge"]):
                return _oauth_error("invalid_grant", "PKCE verification failed")
            if not self._consume(code["jti"], code["exp"]):
                return _oauth_error("invalid_grant", "authorization code was already used")
            return self._issue_tokens(code["sub"], code.get("login", ""), code["client_id"], code.get("scope", ""))

        if grant_type == "refresh_token":
            refresh = self._verify(form.get("refresh_token", ""), "refresh")
            if not refresh:
                return _oauth_error("invalid_grant", "refresh token is invalid or expired")
            if form.get("client_id") and form["client_id"] != refresh["client_id"]:
                return _oauth_error("invalid_grant", "client_id does not match the refresh token")
            if not self._consume(refresh["jti"], refresh["exp"]):
                return _oauth_error("invalid_grant", "refresh token was already used")
            return self._issue_tokens(refresh["sub"], refresh.get("login", ""), refresh["client_id"], refresh.get("scope", ""))

        return _oauth_error("unsupported_grant_type", f"grant_type {grant_type!r} is not supported")
