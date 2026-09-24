#!/usr/bin/env python3
"""Regenerate deterministic common-pattern gallery inputs and measured outputs.

Run from the repository root::

    .venv/bin/python scripts/regenerate_gallery.py --write-fixtures --regenerate

The script intentionally records failures and bounded-search termination rather
than presenting an empty/partial search as an infeasibility proof.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
from fractions import Fraction
from html import escape

from cbdesign.design import DesignRequest, illustrative_request
from cbdesign.compiler import compile_design
from cbdesign.metrics import plan_metrics
from cbdesign.replay import replay
from cbdesign.patterns import asymmetric, basket_weave, checkerboard, diamond, letter, mouse_head, stripes, unrelated
from cbdesign.render_svg import board_svg, species_colors
from cbdesign.visualization import difference_svg, target_svg
from cbdesign.search import SearchSettings, search_design
from cbdesign.target import FrozenTarget, decode_png, target_occupancy

ROOT = Path(__file__).resolve().parents[1]
DESIGNS = ROOT / "examples" / "designs"
GALLERY = ROOT / "examples" / "gallery"
COMMON = {"checkerboard": checkerboard, "stripes": stripes, "diamond": diamond,
          "basket_weave": basket_weave, "letter": lambda: letter(12, 12, glyph="A"),
          "asymmetric": asymmetric, "unrelated": unrelated}
BUDGETS = (1, 2, 4, 8)


def _fixture_target(name: str) -> FrozenTarget:
    """Load the frozen target snapshot; regeneration must never redraw it."""
    data = json.loads((DESIGNS / f"{name}.target.json").read_text())
    return FrozenTarget(tuple(tuple(row) for row in data["rows"]), data.get("metadata", {}))


def _target(name: str) -> FrozenTarget:
    """Pattern factory used only while writing fixtures."""
    if name == "mouse_head":
        return decode_png(ROOT / "examples" / "targets" / "mouse-head.png")
    factory = COMMON[name]
    return factory() if name == "letter" else factory(12, 12)


def _request(target: FrozenTarget, name: str):
    # Request matrices obey N2's 32×32 ceiling. Mouse-head remains a 64×64
    # immutable target and is exactly area-resampled into this frozen 12×12 design.
    sampled = target_occupancy(target, 12, 12)
    matrix = [["B" if value >= Fraction(1, 2) else "A" for value in row] for row in sampled]
    # The request fixes illustrative nominal geometry.  Finite individual source
    # entries are intentionally ample enough for the selected gallery plans, not a
    # claim about real inventory or an unlimited stock pool.
    request = illustrative_request(matrix)
    data = request.model_dump(mode="json")
    data["title"] = f"Illustrative {name.replace('_', ' ')} gallery board"
    for stock in data["stock_types"]:
        stock["available_lengths"] = [419000] * 192
    return data


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def write_fixtures() -> None:
    DESIGNS.mkdir(parents=True, exist_ok=True)
    for name in (*COMMON, "mouse_head"):
        target = _target(name)
        (DESIGNS / f"{name}.target.json").write_text(_json(target.as_dict()))
        (DESIGNS / f"{name}.request.json").write_text(_json(_request(target, name)))


def _pixel_svg(target: FrozenTarget, title: str, actual=None) -> str:
    """Render target pixels and optional replayed physical rectangles separately."""
    size, pad = 480, 20
    cell_w, cell_h = size / target.width, size / target.height
    pixels = []
    for y, row in enumerate(target.rows):
        for x, value in enumerate(row):
            pixels.append(f'<rect x="{pad+x*cell_w:.3f}" y="{pad+y*cell_h:.3f}" width="{cell_w:.3f}" height="{cell_h:.3f}" fill="{"#242424" if value else "#f6f2e8"}"/>')
    overlay = ""
    if actual is not None:
        terminal = actual.parts[actual.terminal]; colors = species_colors(actual)
        sx, sy = size / terminal.size[0], size / terminal.size[1]
        overlay = "".join(f'<rect x="{pad+r.current.origin[0]*sx:.3f}" y="{pad+r.current.origin[1]*sy:.3f}" width="{r.current.size[0]*sx:.3f}" height="{r.current.size[1]*sy:.3f}" fill="{colors[r.species]}" fill-opacity=".48" stroke="#111" stroke-width=".5"/>' for r in terminal.regions)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 550" role="img"><title>{escape(title)}</title><rect width="100%" height="100%" fill="white"/><text x="20" y="18" font-family="sans-serif" font-size="14" font-weight="bold">{escape(title)}</text>{''.join(pixels)}{overlay}<rect x="20" y="20" width="480" height="480" fill="none" stroke="#111"/></svg>\n'''


def regenerate() -> dict:
    GALLERY.mkdir(parents=True, exist_ok=True)
    summaries = []
    for name in (*COMMON, "mouse_head"):
        request_path = DESIGNS / f"{name}.request.json"
        target_path = DESIGNS / f"{name}.target.json"
        if not request_path.exists() or not target_path.exists():
            raise RuntimeError("fixtures missing; run with --write-fixtures first")
        target = _fixture_target(name)
        request = json.loads(request_path.read_text())
        output = GALLERY / name; output.mkdir(parents=True, exist_ok=True)
        (output / "request.json").write_text(_json(request)); (output / "target.json").write_text(_json(target.as_dict()))
        (output / "target.svg").write_text(target_svg(target, f"{name}: immutable target pixels"))
        rows, cols = len(request["matrix"]), len(request["matrix"][0])
        comparisons = []
        selected = None
        exact_started = perf_counter()
        exact = compile_design(DesignRequest.model_validate(request))
        exact_elapsed = perf_counter() - exact_started
        from cbdesign.metrics import plan_metrics
        exact_record = {"kind": "exact_compile", "elapsed_seconds": exact_elapsed,
                        "compiled": exact.plan is not None, "validation": exact.report,
                        "metrics": plan_metrics(exact.plan, exact.replay) if exact.replay is not None else exact.metrics,
                        "failure": None if exact.error is None else {"code": exact.error.code, "message": exact.error.message}}
        comparisons.append(exact_record)
        if exact.plan is not None and exact.replay is not None:
            (output / "exact-plan.json").write_text(_json(exact.plan.model_dump(mode="json")))
        for budget in BUDGETS:
            started = perf_counter()
            result = search_design(request, target, SearchSettings(recipe_budget=budget, grid_dimensions=((rows, cols),), work_budget=32, seed=0))
            elapsed = perf_counter() - started
            candidate = min(result.candidates, key=lambda item: (item.score, item.metrics["joint_count"], item.label), default=None)
            record = {"kind": "search", "recipe_budget": budget, "elapsed_seconds": elapsed, "attempted": result.attempted, "compiled": result.compiled, "rejected": result.rejected, "termination": result.termination, "candidate_count": len(result.candidates)}
            if candidate is not None:
                record.update({"mismatch_fraction": str(candidate.score), "recipe_families": candidate.recipe_families, "metrics": candidate.metrics})
                if selected is None or candidate.score < selected.score: selected = candidate
            comparisons.append(record)
        metrics = {"gallery_format": "cbdesign-gallery/v1", "pattern": name, "target": {"width": target.width, "height": target.height}, "comparisons": comparisons, "selected": None}
        if selected is not None:
            metrics["selected"] = {"label": selected.label, "mismatch_fraction": str(selected.score), "recipe_families": selected.recipe_families, "metrics": selected.metrics}
            (output / "selected-plan.json").write_text(_json(selected.plan.model_dump(mode="json")))
            (output / "achieved.svg").write_text(board_svg(selected.compile_result.replay))
            (output / "difference.svg").write_text(difference_svg(selected.compile_result.replay, target, {"A": "maple", "B": "walnut"}, f"{name}: target pixels versus achieved replay rectangles"))
        (output / "metrics.json").write_text(_json(metrics)); summaries.append(metrics)
    index = {"gallery_format": "cbdesign-gallery/v1", "patterns": summaries}
    (GALLERY / "metrics.json").write_text(_json(index))
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-fixtures", action="store_true")
    parser.add_argument("--regenerate", action="store_true")
    parser.add_argument("--png", action="store_true", help="Render gallery PNGs with optional CairoSVG")
    args = parser.parse_args()
    if not args.write_fixtures and not args.regenerate: parser.error("choose --write-fixtures and/or --regenerate")
    if args.write_fixtures: write_fixtures()
    if args.regenerate:
        regenerate()
        from cbdesign.bundle import plan_bundle
        from cbdesign.models import load_plan
        from cbdesign.validation import validate
        directory = GALLERY / 'mouse_head'
        plan = load_plan(json.loads((directory / 'selected-plan.json').read_text()))
        report, replay = validate(plan)
        bundle = plan_bundle(plan, report, replay)
        for name in ('report.pdf', 'operations.csv', 'material.csv'):
            (directory / name).write_bytes(bundle[name])
    if args.png:
        import cairosvg
        for directory in GALLERY.iterdir():
            if directory.is_dir():
                for name in ('achieved', 'target', 'difference'):
                    cairosvg.svg2png(url=str(directory / f'{name}.svg'),
                                    write_to=str(directory / f'{name}.png'), output_width=700)
    return 0

if __name__ == "__main__": raise SystemExit(main())
