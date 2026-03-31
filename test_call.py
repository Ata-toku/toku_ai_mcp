import json, urllib.request

url = "http://localhost:8000/mcp"
headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

# Initialize
init_body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-03-26", "capabilities": {},
    "clientInfo": {"name": "test", "version": "1"}
}}).encode()
req = urllib.request.Request(url, data=init_body, headers=headers)
resp = urllib.request.urlopen(req)
sid = resp.headers.get("mcp-session-id")
resp.read()

# Initialized notification
notif_body = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode()
req2 = urllib.request.Request(url, data=notif_body, headers={**headers, "mcp-session-id": sid})
urllib.request.urlopen(req2)

# Call query_ai_knowledge
call_body = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
    "name": "query_ai_knowledge",
    "arguments": {"question": "list all AI models"}
}}).encode()
req3 = urllib.request.Request(url, data=call_body, headers={**headers, "mcp-session-id": sid})
resp3 = urllib.request.urlopen(req3)
text = resp3.read().decode()
for line in text.split("\n"):
    if line.startswith("data:"):
        data = json.loads(line[5:].strip())
        if "result" in data:
            content = data["result"].get("content", [])
            for c in content:
                print(c.get("text", "")[:500])
