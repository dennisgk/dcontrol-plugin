# dcontrol-plugin MCP server

This server exposes a legacy SSE MCP endpoint at `GET /sse`. Send `Authorization: Bearer <mcp_token>` when connecting. A connected client agent authenticates with the server's `client_token` over `ws://host:port/client-ws`.

## Run locally

```powershell
cd dcontrol-plugin-py
py -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m app
```

Replace both placeholder tokens before starting. Keep `config.json` private; it is deliberately ignored by neither Git nor Docker, so either do not commit it or use a secret manager in any non-personal deployment.

## MCP tools

`list_clients`, `get_client_notes`, `run_command`, `create_upload`, `complete_upload`, and `create_download` operate on the named connected agent. `create_upload` returns an HTTP endpoint for a separate Python process to `PUT` bytes. Call `complete_upload` after the PUT to write the server-side blob to the agent's requested path. `create_download` returns a bearer-protected URL after fetching a file from the agent.

## Auth note

The implementation accepts a bearer token, which is what a manually configured personal MCP connection needs. It also exposes minimal OAuth discovery/token metadata for token-only, `client_credentials`-style integrations. This is **not** a complete production OAuth authorization server: there is no user login, consent screen, refresh-token rotation, or persistent client registration. For a public ChatGPT connector, put this behind a real OAuth provider and validate issued JWTs instead of using a shared token.
