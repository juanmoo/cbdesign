"""Focused manufacturing-state checks independent of the reference fixture."""
from types import SimpleNamespace as NS

import pytest

from cbdesign.construction_v2 import V2State
from cbdesign.geometry import Box
from cbdesign.models import load_plan
from cbdesign.replay import Part, ReplayError, _region
from cbdesign.validation import validate


def _part(part_id: str, species: str, size: tuple[int, int, int]) -> Part:
    box = Box((0, 0, 0), size)
    return Part(part_id, size, (_region(part_id, species, box, box, (0, 1, 0)),))


def _plan(*, separation_min=(10, 10, 10), separation_kerf=2):
    prep = NS(x_min=1, x_max=1, y_min=1, y_max=1, z_min=1, z_max=1)
    stock = [
        NS(id="a", species="ash", width=20, thickness=10, preparation=prep),
        NS(id="b", species="birch", width=20, thickness=10, preparation=prep),
    ]
    cut = lambda: NS(kerf=separation_kerf, min_input=separation_min, max_input=(100, 100, 100))
    cutting = NS(separation=cut(), preparation=cut(), slicing=cut(), final_trim=cut(),
                 minimum_rip_width=1, slice_min=2, slice_max=20,
                 slicing_reserve=2, new_face_jointing=1)
    surfacing = [NS(process="jointer", axes=[0, 2], min_input=(1, 1, 1),
                    max_input=(100, 100, 100), glue_ready=True, end_grain_supported=True)]
    return NS(
        shop=NS(manufacturing_increment=1, max_workpiece=(100, 100, 100), cutting=cutting, surfacing=surfacing),
        stock_types=stock,
        source_segments=[NS(id="root", stock_type="a", length=40, boundary="allocated_window", separation_operation="separate")],
        grid=NS(pitch=5, columns=4, strip_thickness=8, panel_thickness=6, slice_length=4),
        template=NS(recipes=[], panels=[], rows=[]),
        finishing=NS(terminal="finished", method="jointer"),
    )


def _separation(*, kerf=2):
    return NS(kind="cut", id="separate", input="root", outputs=["window", "reserve"],
              axis=1, retained=30, kerf=kerf, retained_side="min", category="other_offcuts", tool="saw")


def test_source_separation_checks_feed_minimum_before_replay_pop():
    parts = {"root": _part("root", "ash", (20, 40, 10))}
    state = V2State(_plan(separation_min=(21, 1, 1)), parts)
    with pytest.raises(ReplayError, match="feed minimum"):
        state.before(_separation(), parts)
    assert "root" in parts  # state checks run before replay mutates live inventory


def test_source_separation_requires_its_declared_profile_kerf():
    parts = {"root": _part("root", "ash", (20, 40, 10))}
    state = V2State(_plan(separation_kerf=2), parts)
    with pytest.raises(ReplayError, match="kerf differs"):
        state.before(_separation(kerf=3), parts)


def test_source_separation_requires_positive_external_reserve():
    parts = {"root": _part("root", "ash", (20, 40, 10))}
    state = V2State(_plan(), parts)
    op = _separation()
    op.retained = 38  # 38 + 2 leaves no terminal reserve
    with pytest.raises(ReplayError, match="positive children"):
        state.before(op, parts)


def test_root_cannot_be_surfaced_before_declared_separation():
    parts = {"root": _part("root", "ash", (20, 40, 10))}
    state = V2State(_plan(), parts)
    op = NS(kind="surface", id="root-plane", input="root", output="root-flat", removed="chips",
            axis=0, side="min", amount=1, process="jointer")
    with pytest.raises(ReplayError, match="only undergo their declared separation"):
        state.before(op, parts)


def test_glue_cannot_claim_unprepared_faces():
    parts = {"root": _part("root", "ash", (20, 40, 10))}
    state = V2State(_plan(), parts)
    op = NS(kind="glue", id="bad-glue", inputs=["root", "root"], output="panel", axis=0,
            stage="first", prepared_faces=False, negligible_glue_line=True)
    with pytest.raises(ReplayError, match="unprepared mating faces"):
        state.before(op, parts)


def test_prepared_strip_allows_rectangular_panel_length():
    parts = {"root": _part("root", "ash", (20, 40, 10))}
    state = V2State(_plan(), parts)
    meta = state.meta["root"]
    meta.phase = "strip"
    meta.faces = {(axis, side): {"raw": True, "removed": 1, "cut": False, "ready": True, "cut_prepared": axis == 1}
                  for axis in range(3) for side in ("min", "max")}
    # X width is a pitch multiple and Z is strip thickness, but Y intentionally
    # differs from columns * pitch: rectangular panels are valid.
    source = Box((1, 0, 1), (10, 17, 8))
    current = Box((0, 0, 0), (10, 17, 8))
    strip = Part("root", current.size, (_region("root", "ash", source, current, (0, 1, 0)),))
    state.parts["root"] = strip
    state._check_prepared_strips(NS(id="check"), [("root", meta, strip.size)])


def _single_strip_plan():
    """A complete public-API V2 plan with two rows from one physical strip panel."""
    cut = lambda ident, input, outputs, axis, retained, side, category="other_offcuts": {
        "kind": "cut", "id": ident, "input": input, "outputs": outputs, "axis": axis,
        "retained": retained, "kerf": 2, "tool": "saw", "category": category, "retained_side": side,
    }
    surface = lambda ident, input, output, removed, axis, side: {
        "kind": "surface", "id": ident, "input": input, "output": output, "removed": removed,
        "axis": axis, "side": side, "amount": 1, "category": "milling", "process": "jointer",
    }
    ops = [
        cut("separate", "root", ["window", "reserve"], 1, 30, "min"),
        cut("end-max", "window", ["end-max-blank", "end-max-offcut"], 1, 27, "min", "trim"),
        cut("end-min", "end-max-blank", ["blank", "end-min-offcut"], 1, 24, "max", "trim"),
        surface("z-min", "blank", "z-min-flat", "z-min-chips", 2, "min"),
        surface("z-max", "z-min-flat", "z-flat", "z-max-chips", 2, "max"),
        surface("x-min", "z-flat", "x-min-flat", "x-min-chips", 0, "min"),
        surface("x-max", "x-min-flat", "strip", "x-max-chips", 0, "max"),
        # Single panel registration happens before this first panel-Z operation.
        surface("panel-z-min", "strip", "panel-z-min-flat", "panel-z-min-chips", 2, "min"),
        surface("panel-z-max", "panel-z-min-flat", "panel", "panel-z-max-chips", 2, "max"),
        cut("slice-one", "panel", ["slice-one", "panel-rem-one"], 1, 4, "min"),
        cut("slice-two", "panel-rem-one", ["slice-two", "panel-reserve"], 1, 4, "min"),
        {"kind": "rotate", "id": "rotate-one", "input": "slice-one", "output": "row-one", "perm": [0, 2, 1], "sign": [1, -1, 1]},
        {"kind": "rotate", "id": "rotate-two", "input": "slice-two", "output": "row-two", "perm": [0, 2, 1], "sign": [-1, 1, 1]},
        {"kind": "glue", "id": "final", "inputs": ["row-one", "row-two"], "output": "board", "axis": 1,
         "stage": "final", "prepared_faces": True, "negligible_glue_line": True},
        {**surface("finish-min", "board", "finish-min-flat", "finish-min-chips", 2, "min"), "process": "drum_sander"},
        {**surface("finish-max", "finish-min-flat", "finished", "finish-max-chips", 2, "max"), "process": "drum_sander"},
    ]
    produced = {"root"}
    consumed = set()
    removal_categories = {}
    for op in ops:
        inputs = [op["input"]] if "input" in op else op["inputs"]
        consumed.update(inputs)
        if op["kind"] == "cut":
            produced.update(op["outputs"])
            removal_categories[op["outputs"][1]] = op["category"]
        elif op["kind"] == "surface":
            produced.update([op["output"], op["removed"]])
            removal_categories[op["removed"]] = op["category"]
        else:
            produced.add(op["output"])
    terminal = "finished"
    dispositions = [{"part": part, "category": removal_categories.get(part, "other_offcuts"), "reusable": False}
                    for part in sorted(produced - consumed - {terminal})]
    profile = {"kerf": 2, "min_input": [1, 1, 1], "max_input": [100, 100, 100]}
    prep = {"x_min": 1, "x_max": 1, "y_min": 1, "y_max": 1, "z_min": 1, "z_max": 1}
    return {
        "schema_version": "cbdesign-plan/v2", "title": "Single-strip panel", "assumptions": ["nominal"],
        "shop": {"max_workpiece": [100, 100, 100], "manufacturing_increment": 1,
                 "cutting": {"separation": profile, "preparation": profile, "slicing": profile, "final_trim": profile,
                             "minimum_rip_width": 1, "slice_min": 4, "slice_max": 4, "slicing_reserve": 2, "new_face_jointing": 1},
                 "surfacing": [
                     {"process": "jointer", "axes": [0, 2], "min_input": [1, 1, 1], "max_input": [100, 100, 100],
                      "glue_ready": True, "end_grain_supported": True},
                     {"process": "drum_sander", "axes": [2], "min_input": [1, 1, 1], "max_input": [100, 100, 100],
                      "glue_ready": True, "end_grain_supported": True},
                 ]},
        "stock_types": [
            {"id": "ash", "species": "ash", "width": 20, "thickness": 10, "grain": [0, 1, 0], "preparation": prep},
            {"id": "birch", "species": "birch", "width": 20, "thickness": 10, "grain": [0, 1, 0], "preparation": prep},
        ],
        "source_segments": [{"id": "root", "stock_type": "ash", "length": 40, "boundary": "allocated_window", "separation_operation": "separate"}],
        "grid": {"pitch": 18, "columns": 1, "strip_thickness": 8, "panel_thickness": 6, "slice_length": 4},
        "template": {"recipes": [{"id": "A", "cells": ["ash"]}],
                     "panels": [{"id": "single", "part": "strip", "recipe": "A", "strips": ["strip"]}],
                     "rows": [{"rotated_part": "row-one", "panel": "single", "recipe": "A", "reversed": False},
                              {"rotated_part": "row-two", "panel": "single", "recipe": "A", "reversed": True}]},
        "operations": ops, "finishing": {"terminal": terminal, "method": "drum_sander", "end_grain_supported": True},
        "dispositions": dispositions, "expected_final_size": [18, 12, 2],
    }


def test_public_single_strip_panel_registers_snapshot_and_ledger():
    report, replay = validate(load_plan(_single_strip_plan()))
    assert report["status"] == "nominal_valid", report
    assert replay.parts[replay.terminal].size == (18, 12, 2)
    assert not [joint for joint in replay.joints if joint["stage"] == "first"]
    assert set(replay.first_glue_panels) == {"strip"}
    assert replay.first_glue_panels["strip"].size == (18, 24, 8)
    assert replay.ledger()["species"]["ash"]["balance"] == 0
    assert "birch" not in replay.ledger()["species"]  # configured but deliberately unused


@pytest.mark.parametrize("mutate", [
    lambda raw: raw["template"]["panels"][0].update(part="not-the-strip"),
    lambda raw: raw["operations"].__setitem__(8, {**raw["operations"][8], "axis": 0}),
])
def test_public_single_strip_rejects_misdeclaration_or_missing_panel_faces(mutate):
    raw = _single_strip_plan()
    mutate(raw)
    report, _ = validate(load_plan(raw))
    assert report["status"] == "invalid"
