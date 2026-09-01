"""Personal SSE MCP bridge for WebSocket-connected workstation agents."""
from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
STORE = (ROOT / CONFIG.get("storage_dir", "./storage")).resolve()
STORE.mkdir(parents=True, exist_ok=True)
MCP_TOKEN = CONFIG["mcp_token"]
CLIENT_TOKEN = CONFIG["client_token"]
TTL = int(CONFIG.get("upload_ttl_seconds", 3600))

app = FastAPI(title="dcontrol-plugin")
clients: dict[str, WebSocket] = {}
pending: dict[str, asyncio.Future] = {}
transports: dict[str, asyncio.Queue[str]] = {}
files: dict[str, dict[str, Any]] = {}

TOOLS = [
    {"name": "list_clients", "description": "List connected dcontrol clients.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_client_notes", "description": "Read a client's notes and usage instructions.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "run_command", "description": "Run a shell command on a named personal client and return its output.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "command": {"type": "string"}, "timeout_seconds": {"type": "integer", "default": 120}}, "required": ["name", "command"]}},
    {"name": "create_upload", "description": "Create a one-time server upload URL, then PUT bytes there and call complete_upload.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "path": {"type": "string"}}, "required": ["name", "path"]}},
    {"name": "complete_upload", "description": "Tell the client to copy a completed upload to its requested path.", "inputSchema": {"type": "object", "properties": {"upload_id": {"type": "string"}}, "required": ["upload_id"]}},
    {"name": "create_download", "description": "Fetch a client file and return a temporary bearer-protected download URL.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "path": {"type": "string"}}, "required": ["name", "path"]}},
]

def authorized(value: str | None) -> bool:
    return bool(value and secrets.compare_digest(value.removeprefix("Bearer ").strip(), MCP_TOKEN))

def require_token(value: str | None) -> None:
    if not authorized(value):
        raise HTTPException(401, "Bearer MCP token required")

def result(request_id: Any, value: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}

def text_result(request_id: Any, value: Any) -> dict[str, Any]:
    return result(request_id, {"content": [{"type": "text", "text": json.dumps(value, indent=2, default=str)}]})

async def call_client(name: str, method: str, params: dict[str, Any]) -> Any:
    ws = clients.get(name)
    if not ws:
        raise ValueError(f"Client '{name}' is not connected")
    request_id = str(uuid.uuid4())
    future: asyncio.Future = asyncio.get_running_loop().create_future()
    pending[request_id] = future
    try:
        await ws.send_json({"type": "request", "id": request_id, "method": method, "params": params})
        return await asyncio.wait_for(future, timeout=150)
    finally:
        pending.pop(request_id, None)

async def invoke(name: str, args: dict[str, Any]) -> Any:
    if name == "list_clients":
        return {"clients": sorted(clients)}
    if name == "get_client_notes":
        return await call_client(args["name"], "notes", {})
    if name == "run_command":
        return await call_client(args["name"], "command", {"command": args["command"], "timeout_seconds": args.get("timeout_seconds", 120)})
    if name == "create_upload":
        file_id = str(uuid.uuid4())
        files[file_id] = {"name": args["name"], "path": args["path"], "kind": "upload", "expires": time.time() + TTL, "blob": STORE / file_id}
        return {"upload_id": file_id, "method": "PUT", "url": f"/files/upload/{file_id}", "headers": {"Authorization": "Bearer <mcp_token>"}, "next_step": "PUT file bytes, then call complete_upload with upload_id."}
    if name == "complete_upload":
        entry = files.get(args["upload_id"])
        if not entry or entry["kind"] != "upload" or not entry["blob"].is_file():
            raise ValueError("Unknown or incomplete upload_id")
        return await call_client(entry["name"], "write_from_server", {"source": f"/agent-files/{args['upload_id']}", "path": entry["path"]})
    if name == "create_download":
        file_id = str(uuid.uuid4())
        blob = STORE / file_id
        entry = {"name": args["name"], "path": args["path"], "kind": "download", "expires": time.time() + TTL, "blob": blob}
        files[file_id] = entry
        await call_client(args["name"], "copy_to_server", {"path": args["path"], "destination": f"/agent-files/{file_id}"})
        if not blob.is_file():
            raise ValueError("Client did not provide the file")
        return {"download_id": file_id, "url": f"/files/download/{file_id}", "headers": {"Authorization": "Bearer <mcp_token>"}, "expires_in_seconds": TTL}
    raise ValueError(f"Unknown tool '{name}'")

async def handle_mcp(message: dict[str, Any]) -> dict[str, Any] | None:
    method, request_id = message.get("method"), message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        return result(request_id, {"protocolVersion": message.get("params", {}).get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}}, "serverInfo": {"name": "dcontrol-plugin", "version": "0.1.0"}})
    if method == "tools/list":
        return result(request_id, {"tools": TOOLS})
    if method == "tools/call":
        try:
            return text_result(request_id, await invoke(message["params"]["name"], message["params"].get("arguments", {})))
        except Exception as exc:
            return result(request_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

@app.get("/sse")
async def sse(authorization: str | None = Header(default=None)):
    require_token(authorization)
    session_id, queue = str(uuid.uuid4()), asyncio.Queue()
    transports[session_id] = queue
    async def events():
        yield f"event: endpoint\ndata: /messages?session_id={session_id}\n\n"
        try:
            while True:
                yield f"event: message\ndata: {await queue.get()}\n\n"
        finally:
            transports.pop(session_id, None)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.post("/messages")
async def messages(request: Request, session_id: str, authorization: str | None = Header(default=None)):
    require_token(authorization)
    queue = transports.get(session_id)
    if not queue:
        raise HTTPException(404, "SSE session not found")
    response = await handle_mcp(await request.json())
    if response is not None:
        await queue.put(json.dumps(response))
    return Response(status_code=202)

@app.websocket("/client-ws")
async def client_ws(ws: WebSocket):
    if ws.query_params.get("token") != CLIENT_TOKEN:
        await ws.close(code=4401); return
    await ws.accept()
    name: str | None = None
    try:
        hello = await asyncio.wait_for(ws.receive_json(), timeout=15)
        name = hello.get("name")
        if hello.get("type") != "hello" or not isinstance(name, str) or not name:
            await ws.close(code=4400); return
        if name in clients:
            await ws.close(code=4409); return
        clients[name] = ws
        await ws.send_json({"type": "ready", "name": name})
        while True:
            message = await ws.receive_json()
            if message.get("type") == "response" and (future := pending.get(message.get("id"))) and not future.done():
                future.set_result(message.get("result"))
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        if name and clients.get(name) is ws:
            clients.pop(name, None)

@app.put("/files/upload/{file_id}")
async def upload(file_id: str, request: Request, authorization: str | None = Header(default=None)):
    require_token(authorization)
    entry = files.get(file_id)
    if not entry or entry["kind"] != "upload" or entry["expires"] < time.time(): raise HTTPException(404, "Expired upload")
    entry["blob"].write_bytes(await request.body())
    return {"upload_id": file_id, "status": "stored"}

@app.get("/files/download/{file_id}")
async def download(file_id: str, authorization: str | None = Header(default=None)):
    require_token(authorization)
    entry = files.get(file_id)
    if not entry or entry["kind"] != "download" or entry["expires"] < time.time() or not entry["blob"].is_file(): raise HTTPException(404, "Expired download")
    return Response(entry["blob"].read_bytes(), media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{Path(entry["path"]).name}"'})

@app.get("/agent-files/{file_id}")
async def agent_get(file_id: str, x_client_token: str | None = Header(default=None)):
    if not x_client_token or not secrets.compare_digest(x_client_token, CLIENT_TOKEN): raise HTTPException(401, "Client token required")
    entry = files.get(file_id)
    if not entry or entry["expires"] < time.time() or not entry["blob"].is_file(): raise HTTPException(404, "Expired file")
    return Response(entry["blob"].read_bytes(), media_type="application/octet-stream")

@app.put("/agent-files/{file_id}")
async def agent_put(file_id: str, request: Request, x_client_token: str | None = Header(default=None)):
    if not x_client_token or not secrets.compare_digest(x_client_token, CLIENT_TOKEN): raise HTTPException(401, "Client token required")
    entry = files.get(file_id)
    if not entry or entry["expires"] < time.time(): raise HTTPException(404, "Expired file")
    entry["blob"].write_bytes(await request.body())
    return {"file_id": file_id, "status": "stored"}

@app.get("/.well-known/oauth-protected-resource")
async def protected_resource(): return {"resource": "/", "authorization_servers": ["/.well-known/oauth-authorization-server"]}

@app.get("/.well-known/oauth-authorization-server")
async def oauth_metadata(): return {"issuer": "/", "token_endpoint": "/oauth/token", "grant_types_supported": ["client_credentials"], "token_endpoint_auth_methods_supported": ["client_secret_post"]}

@app.post("/oauth/token")
async def oauth_token(request: Request):
    form = await request.form()
    if form.get("grant_type") != "client_credentials" or not secrets.compare_digest(str(form.get("client_secret", "")), MCP_TOKEN): raise HTTPException(401, "Invalid client secret")
    return JSONResponse({"access_token": MCP_TOKEN, "token_type": "Bearer", "expires_in": 86400})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=CONFIG.get("host", "0.0.0.0"), port=int(CONFIG.get("port", 8000)))
