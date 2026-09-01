# dcontrol client agent

Copy or edit `config.json`, set a unique `name`, and make `token` exactly match the server's `client_token`. `server_url` must be reachable from this computer; use `https://` and a reverse proxy outside a local/private network.

```powershell
py -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m client
```

The included `config.json` is the WordTeX/revision workstation profile. `config.codex.example.json` is a second profile template; copy it over `config.json` only when running that separate client. The names must remain unique.

This agent writes every `run_command` string to a temporary script file, executes it, then removes it. On Windows it uses UTF-8 PowerShell `.ps1` files with `powershell.exe -File`; on Linux/macOS it uses UTF-8 shell `.sh` files with `/bin/bash`. This supports multiline scripts and avoids command-line quoting issues. It runs without an allow-list, as requested. Treat access to the unauthenticated MCP endpoint as full control of this computer; use it only on a private network.

If its Internet connection, proxy, or server disappears, the client stays running and retries automatically with randomized exponential backoff (about 1 second, 2 seconds, 4 seconds, up to 60 seconds). A Ctrl+C/application shutdown still stops it normally.
