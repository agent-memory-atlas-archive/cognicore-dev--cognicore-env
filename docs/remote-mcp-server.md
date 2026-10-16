# Remote MCP server (Claude connector)

`cognicore/extension/remote.py` is the hosted MCP server behind the CogniCore Claude connector and the `cognicore-memory` plugin. Users sign in with GitHub, and each GitHub account gets its own memory database.

## How sign-in works

The server is its own OAuth 2.1 authorization server (`cognicore/extension/oauth.py`) and hands the actual sign-in to GitHub:

1. Claude calls the MCP URL without a token and gets `401` with a `WWW-Authenticate` header pointing at `/.well-known/oauth-protected-resource/...`.
2. Claude reads the metadata, registers itself at `/register`, and opens `/authorize` with PKCE.
3. The user sees a consent page, continues to GitHub, and returns to `/oauth/github/callback`.
4. The server reads the user's numeric GitHub ID, issues its own access and refresh tokens with `sub = github:<id>`, and discards the GitHub token.
5. Every MCP call carries the access token; the server maps `sub` to `memory_<sha256(sub)>.db`.

No user database or Supabase project is involved.

## Endpoints

| URL | Purpose |
|---|---|
| `/mcp/stream` | Streamable HTTP transport. Use this as the connector URL. |
| `/mcp/sse` | Legacy SSE transport, still supported by Claude but deprecated. |
| `/health` | Health check for the platform. |

## Environment variables

| Variable | Required | Value |
|---|---|---|
| `COGNICORE_JWT_SECRET` | Yes | Long random string, e.g. `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Changing it signs everyone out. |
| `GITHUB_CLIENT_ID` | Yes | From the GitHub OAuth App. |
| `GITHUB_CLIENT_SECRET` | Yes | From the GitHub OAuth App. |
| `COGNICORE_PUBLIC_URL` | Yes | Public origin, e.g. `https://mcp.cognicoree.tech`. Must match the GitHub callback URL's origin. |
| `COGNICORE_DATA_DIR` | Set by the Dockerfile | `/data/cognicore`. Memories go to `$COGNICORE_DATA_DIR/remote`, so mount a persistent volume at `/data`. |
| `COGNICORE_USE_SEMANTIC` | No | `0` to skip loading sentence-transformers. |
| `COGNICORE_EXTRA_REDIRECT_URIS` | No | Comma-separated extra OAuth redirect URIs accepted at `/register`, on top of Claude's callbacks and RFC 8252 loopback. Add one per MCP client that needs to register dynamically — e.g. `https://connect.smithery.ai/oauth/callback` for Smithery. |

## GitHub OAuth App

GitHub → Settings → Developer settings → OAuth Apps → New OAuth App:

- **Homepage URL:** `https://mcp.cognicoree.tech`
- **Authorization callback URL:** `https://mcp.cognicoree.tech/oauth/github/callback`

The callback URL must use the same origin as `COGNICORE_PUBLIC_URL`.

## Deploying on Railway

`railway.toml` builds the Dockerfile and starts `cognicore.extension.remote:app`.

1. Set the environment variables above on the service.
2. Add a volume mounted at `/data`, or memories are lost on every deploy.
3. Add the custom domain under Settings → Networking, and point a CNAME for `mcp` at the target Railway shows.
4. Verify:

   ```bash
   python scripts/checks/verify_remote_mcp.py https://mcp.cognicoree.tech
   ```

5. In Claude, add a custom connector with URL `https://mcp.cognicoree.tech/mcp/stream` and sign in with GitHub.

## Testing locally

`tests/test_remote_oauth.py` covers the OAuth flow with GitHub stubbed out. To run the server locally:

```bash
COGNICORE_JWT_SECRET=dev-secret GITHUB_CLIENT_ID=... GITHUB_CLIENT_SECRET=... \
COGNICORE_PUBLIC_URL=http://localhost:8000 \
uvicorn cognicore.extension.remote:app --port 8000
```

A local GitHub OAuth App needs the callback `http://localhost:8000/oauth/github/callback`.
