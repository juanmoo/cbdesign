"""Loopback-only browser workbench for bounded illustrative searches."""
from __future__ import annotations

import base64
import json
from dataclasses import asdict, is_dataclass
from fractions import Fraction
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

from .design import DesignRequest, illustrative_request
from .patterns import asymmetric, basket_weave, checkerboard, diamond, letter, mouse_head, stripes, unrelated
from .render_svg import board_svg
from .visualization import difference_svg, target_svg
from .bundle import plan_bundle, zip_bundle
from .search import SearchSettings, search_design
from .target import FrozenTarget, TargetDecodeError, decode_png

MAX_BODY = 1_000_000
MAX_GRID = 32
STATIC = Path(__file__).with_name("static")
PROJECT_VERSION = "cbdesign-project/v1"


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"): return _plain(value.model_dump())
    if is_dataclass(value): return _plain(asdict(value))
    if isinstance(value, dict): return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_plain(v) for v in value]
    if isinstance(value, Fraction): return f"{value.numerator}/{value.denominator}"
    return value


def _target(value: dict[str, Any]) -> FrozenTarget:
    encoded = value.get("png_base64")
    if encoded is not None:
        if not isinstance(encoded, str) or len(encoded) > MAX_BODY * 4 // 3:
            raise ValueError("PNG upload is invalid or too large")
        try: return decode_png(base64.b64decode(encoded, validate=True), max_bytes=MAX_BODY, max_pixels=65_536)
        except (ValueError, TargetDecodeError) as exc: raise ValueError(f"PNG upload rejected: {exc}") from exc
    pattern = value.get("pattern", "checkerboard")
    rows, columns = value.get("rows", 8), value.get("columns", 8)
    if any(isinstance(item, bool) or not isinstance(item, int) or not 2 <= item <= MAX_GRID for item in (rows, columns)): raise ValueError("target rows and columns must be integers from 2 through 32")
    factories = {"checkerboard": checkerboard, "stripes": stripes, "basket_weave": basket_weave,
                 "diamond": diamond, "letter": letter, "asymmetric": asymmetric, "unrelated": unrelated,
                 "mouse_head": mouse_head}
    if pattern not in factories: raise ValueError("unknown built-in target pattern")
    return factories[pattern](rows, columns)


class _Job:
    def __init__(self, payload: dict[str, Any]):
        self.cancel, self.done = Event(), Event(); self.lock = Lock()
        self.progress: dict[str, Any] = {"state": "queued", "attempted": 0}; self.result: Any = None; self.error: str | None = None
        # A generation identifies this job even after a later search replaces it.
        self.generation = 0
        self.payload = payload
        # The browser retains at most one traced candidate per job. Switching candidates
        # evicts the prior trace rather than accumulating potentially large snapshots.
        self._walkthrough_index: int | None = None
        self._walkthrough: Any = None
        self._walkthrough_error: str | None = None
        self._walkthrough_building: tuple[int, Event] | None = None

    def start(self) -> None:
        Thread(target=self.run, daemon=True, name="cbdesign-search").start()

    def run(self) -> None:
        try:
            request_data = self.payload.get("request") or illustrative_request().model_dump()
            request = DesignRequest.model_validate(request_data)
            target = _target(self.payload.get("target", {}))
            raw = self.payload.get("settings", {})
            if not isinstance(raw, dict): raise ValueError("settings must be an object")
            def limit(name: str, default: int, maximum: int) -> int:
                value = raw.get(name, default)
                if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                    raise ValueError(f"{name} must be an integer from 1 through {maximum}")
                return value
            seconds = raw.get("time_limit_seconds", 20)
            if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 < seconds <= 30:
                raise ValueError("time_limit_seconds must be a number greater than 0 and at most 30")
            grids = raw.get("grid_dimensions")
            if grids is not None:
                if not isinstance(grids, list) or not grids: raise ValueError("grid_dimensions must be a nonempty list")
                if any(not isinstance(pair, list) or len(pair) != 2 or any(isinstance(v, bool) or not isinstance(v, int) or not 2 <= v <= MAX_GRID for v in pair) for pair in grids):
                    raise ValueError("grid dimensions must be integer pairs from 2 through 32")
            # Browser workbench limits are intentionally tighter than the library.
            settings = SearchSettings(recipe_budget=limit("recipe_budget", 4, 4), max_recipes=limit("max_recipes", 4, 4),
                work_budget=limit("work_budget", 32, 128), archive_limit=limit("archive_limit", 6, 12),
                time_limit_seconds=seconds, grid_dimensions=tuple(tuple(pair) for pair in grids) if grids is not None else None)
            def update(progress: dict[str, Any]) -> None:
                with self.lock: self.progress = {"state": "running", **_plain(progress)}
            result = search_design(request, target, settings, cancel=self.cancel.is_set, progress=update)
            candidates = []
            for index, candidate in enumerate(result.candidates):
                candidates.append({"id": index, "label": candidate.label, "score": _plain(candidate.score), "metrics": _plain(candidate.metrics),
                    "grid": list(candidate.grid), "svg": board_svg(candidate.compile_result.replay), "difference_svg": difference_svg(candidate.compile_result.replay, result.target, dict(candidate.request.species)),
                    "mismatch_percent": float(candidate.score * 100),
                    "mismatch_mm2": float(candidate.score * candidate.request.final.x * candidate.request.final.y / 1_000_000), "plan": _plain(candidate.plan),
                    "report": _plain(candidate.compile_result.report), "bundle": (candidate.plan, candidate.compile_result.report, candidate.compile_result.replay), "achieved": _plain(candidate.score),
                    "target_area": _plain(candidate.target_area), "difference": _plain(candidate.mismatch_area)})
            with self.lock: self.result = {"termination": result.termination, "attempted": result.attempted, "compiled": result.compiled, "rejected": result.rejected, "candidates": candidates}; self.progress = {"state": "complete", "termination": result.termination}
        except Exception as exc:
            with self.lock: self.error = str(exc); self.progress = {"state": "error"}
        finally: self.done.set()

    def status(self) -> dict[str, Any]:
        with self.lock:
            result = self.result
            if result is not None:
                # Status is deliberately a shallow view: a replay trace can be large and
                # is only built through the explicit, lazy walkthrough endpoints.
                visible = ("id", "label", "score", "metrics", "grid", "svg", "difference_svg", "mismatch_percent", "mismatch_mm2", "report", "achieved", "target_area", "difference")
                result = {**result, "candidates": [{key: candidate[key] for key in visible if key in candidate} for candidate in result["candidates"]]}
            return {**self.progress, "generation": self.generation, "done": self.done.is_set(), "error": self.error, "result": result}

    def walkthrough(self, index: int) -> Any:
        """Return the sole cached trace, building without holding the shared lock."""
        with self.lock:
            if self.result is None or not 0 <= index < len(self.result["candidates"]): raise IndexError
            if self._walkthrough_index == index and self._walkthrough is not None: return self._walkthrough
            if self._walkthrough_index == index and self._walkthrough_error is not None: raise ValueError(self._walkthrough_error)
            if self._walkthrough_building is not None and self._walkthrough_building[0] == index:
                waiting, builder = self._walkthrough_building[1], False
            elif self._walkthrough_building is not None:
                # Serialize candidate changes too, so exactly one trace is retained.
                waiting, builder = self._walkthrough_building[1], False
            else:
                waiting, builder = Event(), True
                self._walkthrough_building = (index, waiting)
                plan = self.result["candidates"][index]["bundle"][0]
        if not builder:
            waiting.wait()
            return self.walkthrough(index)
        try:
            from .render_replay import build_walkthrough
            trace = build_walkthrough(plan)
        except Exception as exc:
            with self.lock:
                if self._walkthrough_building and self._walkthrough_building[0] == index:
                    self._walkthrough_error = str(exc); self._walkthrough_index = index
                    self._walkthrough_building[1].set(); self._walkthrough_building = None
            raise ValueError(str(exc)) from exc
        with self.lock:
            # An earlier build may finish after a newer candidate request. It must not
            # evict the newer requested cache slot.
            if self._walkthrough_building is None or self._walkthrough_building[0] == index:
                self._walkthrough_index, self._walkthrough, self._walkthrough_error = index, trace, None
                if self._walkthrough_building: self._walkthrough_building[1].set(); self._walkthrough_building = None
        return trace


class Workbench:
    """Owns the one permitted background search job."""
    def __init__(self): self.job: _Job | None = None; self.lock = Lock(); self._generation = 0
    def start(self, payload: dict[str, Any]) -> _Job:
        with self.lock:
            if self.job is not None and not self.job.done.is_set(): raise RuntimeError("a search is already running")
            self._generation += 1
            self.job = _Job(payload); self.job.generation = self._generation; self.job.start(); return self.job
    def current(self, generation: int) -> _Job:
        with self.lock:
            if self.job is None or self.job.generation != generation: raise LookupError
            return self.job


def make_server(port: int = 8765) -> ThreadingHTTPServer:
    """Create a threaded, loopback-only server; callers may use ``serve`` to run it."""
    if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535: raise ValueError("port must be 0 through 65535")
    workbench = Workbench()
    class Handler(BaseHTTPRequestHandler):
        server_version = "cbdesign-local/1"
        def log_message(self, format, *args): pass
        def _same_origin(self) -> bool:
            host = self.headers.get("Host", "")
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if host not in allowed: return False
            origin = self.headers.get("Origin")
            return not origin or origin in {f"http://{item}" for item in allowed}
        def _json(self, code: int, data: Any) -> None:
            encoded = json.dumps(_plain(data), separators=(",", ":")).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(encoded))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(encoded)
        def _body(self) -> dict[str, Any]:
            length = self.headers.get("Content-Length")
            if length is None or not length.isdigit() or int(length) > MAX_BODY: raise ValueError("request body is invalid or too large")
            value = json.loads(self.rfile.read(int(length)))
            if not isinstance(value, dict): raise ValueError("JSON body must be an object")
            return value
        def do_GET(self):
            if not self._same_origin(): self._json(HTTPStatus.FORBIDDEN, {"error":"local origin required"}); return
            path = urlparse(self.path).path
            if path == "/api/status": self._json(200, workbench.job.status() if workbench.job else {"state":"idle", "generation": 0, "done":True}); return
            if path.startswith("/api/walkthrough/"):
                try:
                    parts = path.strip("/").split("/")
                    # /api/walkthrough/<generation>/<candidate>/manifest
                    # /api/walkthrough/<generation>/<candidate>/step/<index>
                    if parts[:2] != ["api", "walkthrough"] or len(parts) not in (5, 6): raise ValueError
                    generation, candidate = int(parts[2]), int(parts[3])
                    job = workbench.current(generation)
                    if not job.done.is_set() or job.result is None: raise LookupError
                    plan = job.result["candidates"][candidate]["bundle"][0]
                    # Reject malformed/out-of-range requests before producing a trace.
                    if len(parts) == 6 and (parts[4] != "step" or not 0 <= int(parts[5]) <= len(plan.operations) + 1): raise ValueError
                    if len(parts) == 5 and parts[4] != "manifest": raise ValueError
                    trace = job.walkthrough(candidate)
                    from .render_replay import walkthrough_manifest, walkthrough_step
                    if len(parts) == 5:
                        self._json(200, {"generation": generation, "candidate": candidate, **walkthrough_manifest(plan, trace)})
                    elif len(parts) == 6:
                        index = int(parts[5])
                        self._json(200, {"generation": generation, "candidate": candidate, **walkthrough_step(plan, trace, index)})
                    else: raise ValueError
                except (ValueError, IndexError, LookupError): self._json(404, {"error":"walkthrough not found"})
                return
            if path == "/api/target":
                try:
                    query = parse_qs(urlparse(self.path).query)
                    raw = {key: values[-1] for key, values in query.items()}
                    for name in ("rows", "columns"):
                        text = raw.get(name, "12")
                        if not text.isascii() or not text.isdecimal(): raise ValueError(f"{name} must be an integer")
                        raw[name] = int(text)
                    target = _target(raw)
                    self._json(200, {"target": target.as_dict(), "svg": target_svg(target)})
                except ValueError as exc: self._json(400, {"error": str(exc)})
                return
            if path.startswith("/api/download/"):
                try:
                    segments = path.strip("/").split("/")
                    # Keep /api/download/<candidate> for saved old pages, but new UI
                    # scopes links to the generation that produced the candidate.
                    if len(segments) == 3:
                        index = int(segments[2]); job = workbench.job
                    elif len(segments) == 4:
                        job = workbench.current(int(segments[2])); index = int(segments[3])
                    else: raise ValueError
                    candidate = job.result["candidates"][index] if job and job.result else None
                    if candidate is None: raise IndexError
                    plan, report, replay = candidate["bundle"]
                    encoded = zip_bundle(plan_bundle(plan, report, replay))
                    self.send_response(200); self.send_header("Content-Type", "application/zip"); self.send_header("Content-Disposition", "attachment; filename=cbdesign-bundle.zip"); self.send_header("Content-Length", str(len(encoded))); self.end_headers(); self.wfile.write(encoded)
                except (ValueError, IndexError, KeyError): self._json(404, {"error":"candidate not found"})
                return
            if path == "/": path = "/index.html"
            if path not in {"/index.html", "/app.js", "/style.css"}: self._json(404, {"error":"not found"}); return
            file = STATIC / path[1:]
            data = file.read_bytes(); types = {".html":"text/html", ".js":"application/javascript", ".css":"text/css"}
            self.send_response(200); self.send_header("Content-Type", types[file.suffix] + "; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        def do_POST(self):
            if not self._same_origin(): self._json(HTTPStatus.FORBIDDEN, {"error":"local origin required"}); return
            try: body = self._body()
            except (ValueError, json.JSONDecodeError) as exc: self._json(413, {"error":str(exc)}); return
            path = urlparse(self.path).path
            if path == "/api/search":
                try: job = workbench.start(body); self._json(202, {"state":"started", "generation": job.generation})
                except (ValueError, RuntimeError) as exc: self._json(409, {"error":str(exc)})
            elif path == "/api/cancel":
                if workbench.job: workbench.job.cancel.set()
                self._json(200, {"state":"cancelling"})
            else: self._json(404, {"error":"not found"})
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    # Kept private by convention, but available to in-process regression tests.
    server.workbench = workbench
    return server


def serve(port: int = 8765) -> None:
    """Run the local workbench until interrupted."""
    server = make_server(port)
    try: server.serve_forever()
    finally: server.server_close()
