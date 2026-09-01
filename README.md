# dcontrol-plugin

Three cooperating Python projects:

| Directory | Purpose |
| --- | --- |
| `dcontrol-plugin-py` | Token-protected SSE MCP server and file relay |
| `dcontrol-plugin-docker` | Docker wrapper for the server |
| `dcontrol-plugin-client-py` | WebSocket-connected machine/client agent |

Start with the setup and security notes in the server README. This is intentionally a personal-network tool: never expose it to the public Internet without real OAuth, TLS, token rotation, and command restrictions.
