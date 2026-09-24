import http.client
import json
from threading import Thread

from cbdesign.web import MAX_BODY, PROJECT_VERSION, make_server


def live_server():
    server = make_server(0)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    return server, thread


def request(server, method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
    headers = {"Host": f"127.0.0.1:{server.server_port}", **(headers or {})}
    if data is not None: headers["Content-Type"] = "application/json"
    conn.request(method, path, data, headers); response = conn.getresponse(); out = response.read(); conn.close()
    return response.status, json.loads(out) if response.getheader("Content-Type", "").startswith("application/json") else out


def test_host_and_origin_protections_and_static_page():
    server, _ = live_server()
    try:
        status, body = request(server, "GET", "/", headers={"Host":"evil.example"})
        assert status == 403 and body["error"] == "local origin required"
        status, body = request(server, "POST", "/api/cancel", {}, headers={"Origin":"http://evil.example"})
        assert status == 403
        # Missing Origin is allowed for local direct navigation, but Host is never optional.
        status, body = request(server, "POST", "/api/cancel", {})
        assert status == 200
        status, page = request(server, "GET", "/")
        assert status == 200 and b"Grain Study" in page
    finally: server.shutdown(); server.server_close()


def test_status_done_is_a_json_boolean_not_fraction_text():
    server, _ = live_server()
    try:
        status, body = request(server, "GET", "/api/status")
        assert status == 200
        assert body["done"] is True
    finally: server.shutdown(); server.server_close()


def test_oversize_body_rejected_and_project_contract_is_versioned():
    server, _ = live_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
        conn.request("POST", "/api/search", b"x", {"Host":f"127.0.0.1:{server.server_port}", "Content-Length":str(MAX_BODY + 1)})
        response = conn.getresponse(); assert response.status == 413; response.read(); conn.close()
        assert PROJECT_VERSION == "cbdesign-project/v1"
    finally: server.shutdown(); server.server_close()


def test_cancel_flow_returns_promptly():
    server, _ = live_server()
    try:
        status, _ = request(server, "POST", "/api/search", {"target":{"pattern":"mouse_head","rows":32,"columns":32}, "settings":{"work_budget":128,"time_limit_seconds":30}})
        assert status == 202
        status, body = request(server, "POST", "/api/cancel", {})
        assert status == 200 and body["state"] == "cancelling"
        status, body = request(server, "GET", "/api/status")
        assert status == 200 and body["state"] in {"queued", "running", "complete"}
    finally: server.shutdown(); server.server_close()
