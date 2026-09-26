import http.client
import json
import time
from concurrent.futures import ThreadPoolExecutor
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


def finished_search(server):
    status, started = request(server, "POST", "/api/search", {"target":{"pattern":"checkerboard", "rows":12,"columns":12}, "settings":{"work_budget":32,"time_limit_seconds":20, "grid_dimensions":[[12,12]]}})
    assert status == 202
    for _ in range(100):
        status, body = request(server, "GET", "/api/status")
        if body["done"]: return body
        time.sleep(.03)
    raise AssertionError("search did not finish")


def test_walkthrough_is_lazy_generation_scoped_and_navigates_every_step():
    server, _ = live_server()
    try:
        done = finished_search(server)
        assert "trace" not in json.dumps(done)
        assert done["result"]["candidates"]
        generation = done["generation"]
        candidate = done["result"]["candidates"][0]
        job = server.workbench.job
        assert job._walkthrough is None
        status, manifest = request(server, "GET", f"/api/walkthrough/{generation}/{candidate['id']}/manifest")
        assert status == 200 and job._walkthrough is not None
        assert manifest["steps"][0]["label"] == "Stock inventory"
        assert manifest["steps"][-1]["label"] == "Finished board"
        for item in manifest["steps"]:
            status, step = request(server, "GET", f"/api/walkthrough/{generation}/{candidate['id']}/step/{item['index']}")
            assert status == 200 and step["index"] == item["index"] and "html" in step
        for path in (f"/api/walkthrough/{generation}/-1/manifest", f"/api/walkthrough/{generation}/999/manifest", f"/api/walkthrough/{generation}/0/step/-1", f"/api/walkthrough/{generation}/0/step/{len(manifest['steps'])}"):
            status, _ = request(server, "GET", path)
            assert status == 404
        status, body = request(server, "GET", f"/api/walkthrough/{generation}/0/manifest", headers={"Host":"evil.example"})
        assert status == 403 and body["error"] == "local origin required"
    finally: server.shutdown(); server.server_close()


def test_walkthrough_build_deduplicates_and_single_cache_eviction(monkeypatch):
    server, _ = live_server()
    try:
        done = finished_search(server); generation = done["generation"]; job = server.workbench.job
        import cbdesign.render_replay as renderer
        original, calls = renderer.build_walkthrough, []
        def counted(plan):
            calls.append(plan); time.sleep(.04); return original(plan)
        monkeypatch.setattr(renderer, "build_walkthrough", counted)
        path = f"/api/walkthrough/{generation}/0/manifest"
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(lambda _: request(server, "GET", path)[0], range(4)))
        assert replies == [200] * 4 and len(calls) == 1
        # If the search returned another candidate, moving to it replaces the sole slot.
        if len(done["result"]["candidates"]) > 1:
            request(server, "GET", f"/api/walkthrough/{generation}/1/manifest")
            assert job._walkthrough_index == 1 and not isinstance(job._walkthrough, dict)
    finally: server.shutdown(); server.server_close()


def test_walkthrough_old_generation_is_rejected_after_next_job():
    server, _ = live_server()
    try:
        first = finished_search(server); old = first["generation"]
        second = finished_search(server); assert second["generation"] > old
        status, _ = request(server, "GET", f"/api/walkthrough/{old}/0/manifest")
        assert status == 404
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
