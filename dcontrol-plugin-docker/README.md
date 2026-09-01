# Docker server

Edit `config.json` first. Its `mcp_token` and `client_token` must have the same values as the matching local server/client configuration. Then run:

```powershell
cd dcontrol-plugin-docker
docker compose up --build -d
```

The named Docker volume stores temporary uploads/downloads. The client never needs a shared filesystem with the container: it transfers data through its authenticated `/agent-files/...` endpoints.
