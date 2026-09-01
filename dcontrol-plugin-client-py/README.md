# dcontrol client agent

Copy or edit `config.json`, set a unique `name`, and make `token` exactly match the server's `client_token`. `server_url` must be reachable from this computer; use `https://` and a reverse proxy outside a local/private network.

```powershell
py -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m client
```

The included `config.json` is the WordTeX/revision workstation profile. `config.codex.example.json` is a second profile template; copy it over `config.json` only when running that separate client. The names must remain unique.

This agent intentionally executes the `run_command` MCP tool without an allow-list, as requested. Treat possession of the MCP token as full control of this computer; use it only on a private network.
