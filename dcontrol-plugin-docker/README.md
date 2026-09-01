# Docker server

Edit `config.json` first. Only `client_token` must match the client configuration; `mcp_token` is intentionally unused. Then run:

```powershell
cd dcontrol-plugin-docker
docker compose up --build -d
```

The named Docker volume stores temporary uploads/downloads. The client never needs a shared filesystem with the container: it transfers data through its authenticated `/agent-files/...` endpoints.
