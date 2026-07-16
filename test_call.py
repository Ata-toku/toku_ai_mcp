"""Manual streamable-HTTP smoke test for a running local server."""

import json
import urllib.request


URL = "http://localhost:8000/mcp"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _read_event(response) -> dict:
    while line := response.readline():
        decoded = line.decode()
        if decoded.startswith("data:"):
            return json.loads(decoded[5:].strip())
    raise RuntimeError("The server returned no MCP data event")


def _request(
    method: str,
    request_id: int,
    session_id: str,
    params: dict | None = None,
) -> dict:
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
    ).encode()
    response = urllib.request.urlopen(
        urllib.request.Request(
            URL,
            data=body,
            headers=HEADERS | {"mcp-session-id": session_id},
        )
    )
    return _read_event(response)


def main() -> None:
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "smoke-test", "version": "1"},
        },
    }
    response = urllib.request.urlopen(
        urllib.request.Request(
            URL, data=json.dumps(initialize).encode(), headers=HEADERS
        )
    )
    session_id = response.headers.get("mcp-session-id")
    response.read()
    if not session_id:
        raise RuntimeError("The server did not return an MCP session ID")

    notification = json.dumps(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    ).encode()
    urllib.request.urlopen(
        urllib.request.Request(
            URL,
            data=notification,
            headers=HEADERS | {"mcp-session-id": session_id},
        )
    )

    for request_id, method, key in (
        (2, "tools/list", "tools"),
        (3, "resources/list", "resources"),
        (4, "prompts/list", "prompts"),
    ):
        payload = _request(method, request_id, session_id)
        names = [
            item.get("name") or item.get("uri")
            for item in payload["result"][key]
        ]
        print(f"{key}: {names}")

if __name__ == "__main__":
    main()
