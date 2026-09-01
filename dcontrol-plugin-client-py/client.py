"""WebSocket client agent for dcontrol-plugin-py."""
from __future__ import annotations

import asyncio
import json
import os
import random
import subprocess
import tempfile
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
SERVER = CONFIG["server_url"].rstrip("/")
WS_URL = SERVER.replace("https://", "wss://").replace("http://", "ws://") + "/client-ws?token=" + CONFIG["token"]
MAX_CONCURRENT_COMMANDS = int(CONFIG.get("max_concurrent_commands", 0))

def output_text(value: str | bytes | None) -> str:
    """TimeoutExpired may carry bytes even when subprocess text mode is enabled."""
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value

def server_request(path: str, method: str = "GET", data: bytes | None = None) -> bytes:
    request = urllib.request.Request(SERVER + path, data=data, method=method, headers={"X-Client-Token": CONFIG["token"]})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()

def execute(method: str, params: dict) -> dict:
    if method == "notes":
        return {"name": CONFIG["name"], "notes": CONFIG.get("notes", "")}
    if method == "command":
        script_path: Path | None = None
        try:
            # A script file preserves multiline commands and avoids command-line escaping.
            is_windows = os.name == "nt"
            suffix = ".ps1" if is_windows else ".sh"
            encoding = "utf-8-sig" if is_windows else "utf-8"
            with tempfile.NamedTemporaryFile(mode="w", encoding=encoding, suffix=suffix, prefix="dcontrol-", delete=False) as script:
                script.write(params["command"])
                script_path = Path(script.name)
            launcher = (
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
                if is_windows
                else ["/bin/bash", str(script_path)]
            )
            done = subprocess.run(
                launcher,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=int(params.get("timeout_seconds", 120)),
            )
            return {"returncode": done.returncode, "stdout": output_text(done.stdout), "stderr": output_text(done.stderr)}
        except subprocess.TimeoutExpired as exc:
            return {"returncode": None, "stdout": output_text(exc.stdout), "stderr": f"Command timed out after {params.get('timeout_seconds', 120)} seconds.\n{output_text(exc.stderr)}"}
        finally:
            if script_path:
                script_path.unlink(missing_ok=True)
    if method == "write_from_server":
        destination = Path(params["path"]).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(server_request(params["source"]))
        return {"written": str(destination)}
    if method == "copy_to_server":
        source = Path(params["path"]).expanduser()
        if not source.is_file(): raise FileNotFoundError(source)
        server_request(params["destination"], "PUT", source.read_bytes())
        return {"uploaded": str(source), "bytes": source.stat().st_size}
    raise ValueError(f"Unknown request: {method}")

async def handle_request(ws, message: dict, command_slots: asyncio.Semaphore | None, send_lock: asyncio.Lock) -> None:
    """Execute one request without blocking the WebSocket receive loop."""
    try:
        if message["method"] == "command" and command_slots is not None:
            async with command_slots:
                value = await asyncio.to_thread(execute, message["method"], message.get("params", {}))
        else:
            value = await asyncio.to_thread(execute, message["method"], message.get("params", {}))
        reply = {"type": "response", "id": message["id"], "result": value}
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        reply = {"type": "response", "id": message.get("id"), "result": {"error": str(exc)}}
    try:
        # Multiple background tasks may finish together; WebSocket sends stay ordered.
        async with send_lock:
            await ws.send(json.dumps(reply))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(f"Could not send response {message.get('id')} after disconnect: {exc}")

async def run() -> None:
    """Keep the agent alive through temporary Internet/server interruptions."""
    retry_seconds = 1
    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=15, ping_timeout=30, close_timeout=5, max_size=None) as ws:
                await ws.send(json.dumps({"type": "hello", "name": CONFIG["name"]}))
                print(f"Connected as {CONFIG['name']}")
                retry_seconds = 1
                command_slots = asyncio.Semaphore(MAX_CONCURRENT_COMMANDS) if MAX_CONCURRENT_COMMANDS > 0 else None
                send_lock = asyncio.Lock()
                background_tasks: set[asyncio.Task] = set()
                async for raw in ws:
                    message = json.loads(raw)
                    if message.get("type") != "request": continue
                    task = asyncio.create_task(handle_request(ws, message, command_slots, send_lock))
                    background_tasks.add(task)
                    task.add_done_callback(background_tasks.discard)
                raise ConnectionError("WebSocket connection closed")
        except asyncio.CancelledError:
            # A real application shutdown should stop cleanly; network errors do not arrive here.
            raise
        except Exception as exc:
            # The WebSocket library reports dropped Wi-Fi, server restarts, and proxy closes here.
            # Randomized backoff prevents rapid retry loops while an Internet connection is unavailable.
            wait_seconds = min(60, retry_seconds) + random.uniform(0, 1)
            print(f"Disconnected: {exc}; retrying in {wait_seconds:.1f} seconds")
            await asyncio.sleep(wait_seconds)
            retry_seconds = min(60, retry_seconds * 2)

if __name__ == "__main__":
    asyncio.run(run())
