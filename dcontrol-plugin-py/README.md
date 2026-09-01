# dcontrol-plugin MCP server

This server exposes an unauthenticated Streamable HTTP MCP endpoint at `POST /mcp`. Select **No Auth** when creating the ChatGPT connector. A connected workstation agent still authenticates with the server's `client_token` over `ws://host:port/client-ws`.

## Run locally

```powershell
cd dcontrol-plugin-py
py -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m app
```

Replace `client_token` before starting. `mcp_token` remains in `config.json` but is deliberately unused for now. Keep `config.json` private, since the client token allows a client to register with the server.

Set `public_url` to the exact externally reachable HTTPS URL before using a ChatGPT connector (for example, `https://dcontrol.example.com`). `127.0.0.1` works only for a client running on the same machine as the server.

## MCP tools

`list_clients`, `get_client_notes`, `run_command`, `create_upload`, `complete_upload`, and `create_download` operate on the named connected agent. `create_upload` returns an HTTP endpoint for a separate Python process to `PUT` bytes. Call `complete_upload` after the PUT to write the server-side blob to the agent's requested path. `create_download` returns a temporary download URL after fetching a file from the agent. File URLs are also unauthenticated; their random IDs are the only protection.

## Security warning

MCP tools, including unrestricted remote command execution and file transfers, have **no authentication**. Anyone who can reach `/mcp` can control any connected client. This is strictly for a disposable private setup; do not expose it to the Internet.
