"""N1 construction-state validation for ``cbdesign-plan/v2``.

The replay engine owns geometry and accounting.  This module deliberately owns only
manufacturing lineage: operation profiles, face preparation evidence, the restricted
strip/panel/slice template, and the final finishing path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .geometry import Box
from .replay import ReplayError


Face = dict[str, Any]


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _size(part: Any) -> tuple[int, int, int]:
    return tuple(int(x) for x in part.size)


def _kind(op: Any) -> str:
    return str(_value(op, "kind"))


def _id(op: Any) -> str:
    return str(_value(op, "id", ""))


def _inputs(op: Any) -> list[str]:
    return [str(_value(op, "input"))] if _value(op, "input", None) is not None else [str(x) for x in _value(op, "inputs", [])]


def _outputs(op: Any) -> list[str]:
    if _kind(op) == "cut":
        return [str(x) for x in _value(op, "outputs", [])]
    if _kind(op) == "surface":
        return [str(_value(op, "output")), str(_value(op, "removed"))]
    return [str(_value(op, "output"))]


@dataclass
class _Meta:
    phase: str
    source_type: str | None = None
    source_segment: str | None = None
    # Faces are indexed (axis, side), and hold independent source-removal / fresh-cut
    # evidence.  A fresh face is never copied into the new child at a cut boundary.
    faces: dict[tuple[int, str], Face] = field(default_factory=dict)
    grain: tuple[int, int, int] = (0, 1, 0)
    panel: str | None = None
    strips: tuple[str, ...] = ()
    row_reversed: bool | None = None
    sliced_count: int = 0


class V2State:
    """State hook consumed by the v2 replay path.

    ``before`` is intentionally called while inputs are live, so machine feed and
    profile checks happen before replay pops them.  ``after`` receives replay's exact
    geometrical outputs and updates only the evidence that geometry cannot represent.
    """

    def __init__(self, plan: Any, parts: dict[str, Any]):
        self.plan = plan
        self.parts = parts
        self.meta: dict[str, _Meta] = {}
        self.pending: dict[str, tuple[Any, list[tuple[str, _Meta, tuple[int, int, int]]]]] = {}
        self.final_glue: Any | None = None
        self._final_output: str | None = None
        self._panel_z_faces: set[str] = set()
        self._slices: dict[str, str] = {}
        self._single_panels: dict[str, Any] = {}
        self._single_panel_snapshots: dict[str, Any] = {}
        self._registered_panels: set[str] = set()
        self._blank_lengths: dict[str, int] = {}
        self._produced_by: dict[str, Any] = {}
        self._consumed_by: dict[str, Any] = {}

        stock_types = list(_value(plan, "stock_types", []))
        self.stock_types = {str(_value(s, "id")): s for s in stock_types}
        if len(stock_types) != 2 or len(self.stock_types) != 2:
            self._fail("two_stock_types", "v2 requires exactly two uniquely identified stock types")
        species = [_value(s, "species") for s in stock_types]
        if len(set(species)) != 2:
            self._fail("two_species_scope", "v2 requires exactly two distinct stock species")

        segments = list(_value(plan, "source_segments", []))
        self.segments = {str(_value(s, "id")): s for s in segments}
        if len(segments) != len(self.segments) or not segments:
            self._fail("source_segments", "source segment IDs must be unique and nonempty")
        if set(parts) != set(self.segments):
            self._fail("source_segments", "replay roots must exactly equal declared source segments", expected=sorted(self.segments), actual=sorted(parts))
        for segment_id, segment in self.segments.items():
            type_id = str(_value(segment, "stock_type"))
            stock = self.stock_types.get(type_id)
            if stock is None:
                self._fail("unknown_stock_type", "source segment names an unknown stock type", part=segment_id, actual=type_id)
            if _value(segment, "boundary") != "allocated_window":
                self._fail("source_boundary", "v2 source segments must declare allocated_window boundaries", part=segment_id)
            if not _value(segment, "separation_operation", None):
                self._fail("source_separation", "source segment requires a separation operation", part=segment_id)
            expected = (int(_value(stock, "width")), int(_value(segment, "length")), int(_value(stock, "thickness")))
            if _size(parts[segment_id]) != expected:
                self._fail("source_dimensions", "root dimensions must derive from its stock type and segment length", part=segment_id, expected=list(expected), actual=list(_size(parts[segment_id])))
            faces = {(axis, side): {"raw": True, "removed": 0, "cut": False, "ready": False, "cut_prepared": False}
                     for axis in range(3) for side in ("min", "max")}
            self.meta[segment_id] = _Meta("root", type_id, segment_id, faces)

        self.grid = _value(plan, "grid")
        self.template = _value(plan, "template")
        self._validate_grid()
        self.recipes = {str(_value(r, "id")): r for r in _value(self.template, "recipes", [])}
        self.panels = {str(_value(p, "id")): p for p in _value(self.template, "panels", [])}
        if len(self.panels) != len(list(_value(self.template, "panels", []))):
            self._fail("panel_declaration", "panel IDs must be unique")
        self.rows = list(_value(self.template, "rows", []))
        self._panel_by_part = {str(_value(p, "part")): name for name, p in self.panels.items()}
        if len(self._panel_by_part) != len(self.panels):
            self._fail("panel_declaration", "panel parts must be uniquely registered")

    def _fail(self, code: str, message: str, op: Any | None = None, part: str | None = None, expected: Any = None, actual: Any = None) -> None:
        raise ReplayError(code, message, _id(op) if op is not None else None, part, expected, actual)

    def _validate_grid(self) -> None:
        if self.grid is None:
            self._fail("grid", "v2 requires construction grid metadata")
        for name in ("pitch", "columns", "strip_thickness", "panel_thickness", "slice_length"):
            value = _value(self.grid, name)
            if value is None or int(value) <= 0:
                self._fail("grid", "all grid dimensions must be positive", actual=name)

    def _profile(self, name: str) -> Any:
        cutting = _value(_value(self.plan, "shop"), "cutting")
        profile = _value(cutting, name)
        if profile is None:
            self._fail("shop_profile", "required cutting profile is missing", actual=name)
        return profile

    def _increment(self, value: int, label: str, op: Any | None = None) -> None:
        inc = int(_value(_value(self.plan, "shop"), "manufacturing_increment"))
        if value <= 0 or value % inc:
            self._fail("increment_violation", "manufacturing dimensions must be positive grid multiples", op, expected=inc, actual={label: value})

    def _check_capacity(self, size: tuple[int, int, int], op: Any, part: str) -> None:
        max_piece = _value(_value(self.plan, "shop"), "max_workpiece")
        if max_piece is not None and any(size[i] > int(max_piece[i]) for i in range(3)):
            self._fail("shop_capacity", "input workpiece exceeds configured capacity", op, part, list(max_piece), list(size))

    def _check_input_profile(self, profile: Any, size: tuple[int, int, int], op: Any, part: str) -> None:
        minimum = _value(profile, "min_input")
        maximum = _value(profile, "max_input")
        if minimum is not None and any(size[i] < int(minimum[i]) for i in range(3)):
            self._fail("min_input", "actual workpiece is below operation feed minimum", op, part, list(minimum), list(size))
        if maximum is not None and any(size[i] > int(maximum[i]) for i in range(3)):
            self._fail("max_input", "actual workpiece exceeds operation profile maximum", op, part, list(maximum), list(size))

    def _prep(self, meta: _Meta) -> Any:
        stock = self.stock_types[meta.source_type or ""]
        return _value(stock, "preparation")

    def _qualifying_surface(self, op: Any, meta: _Meta, axis: int, is_end_grain: bool) -> Any:
        process_name = _value(op, "process")
        candidates = list(_value(_value(self.plan, "shop"), "surfacing", []))
        process = next((x for x in candidates if _value(x, "process") == process_name), None)
        if process is None:
            self._fail("surface_process", "surface operation names no supported shop process", op, actual=process_name)
        axes = list(_value(process, "axes", []))
        if axis not in axes:
            self._fail("surface_axis", "surfacing process does not support this axis", op, expected=axes, actual=axis)
        if is_end_grain and not bool(_value(process, "end_grain_supported")):
            self._fail("end_grain_process", "surfacing process does not support end grain", op)
        return process

    def _cut_profile_name(self, op: Any, meta: _Meta) -> str:
        axis = int(_value(op, "axis"))
        if meta.phase == "root":
            return "separation"
        if meta.phase == "panel_ready":
            return "slicing"
        if meta.phase in {"final", "final_finished"}:
            return "final_trim"
        if meta.phase in {"blank", "rough", "strip"}:
            return "preparation"
        self._fail("construction_phase", "cut is not permitted at this manufacturing phase", op, actual=meta.phase)
        raise AssertionError

    def before(self, op: Any, parts: dict[str, Any]) -> None:
        """Validate one operation before replay consumes its live inputs."""
        inputs = _inputs(op)
        snapshots: list[tuple[str, _Meta, tuple[int, int, int]]] = []
        for pid in inputs:
            meta = self.meta.get(pid)
            if meta is None or pid not in parts:
                self._fail("construction_lineage", "operation input has no v2 manufacturing state", op, pid)
            # A physical one-strip panel is registered at its actual live prepared
            # strip, before the next operation takes its snapshot or consumes it.
            self._maybe_register_single_panel(pid, meta, parts[pid], op)
            size = _size(parts[pid])
            self._check_capacity(size, op, pid)
            snapshots.append((pid, meta, size))
            self._consumed_by[pid] = op

        kind = _kind(op)
        if kind == "cut":
            if len(snapshots) != 1:
                self._fail("operation_shape", "cut needs exactly one input", op)
            pid, meta, size = snapshots[0]
            profile_name = self._cut_profile_name(op, meta)
            profile = self._profile(profile_name)
            self._check_input_profile(profile, size, op, pid)
            axis = int(_value(op, "axis")); kerf = int(_value(op, "kerf")); retained = int(_value(op, "retained"))
            self._increment(kerf, "kerf", op); self._increment(retained, "retained", op)
            if kerf != int(_value(profile, "kerf")):
                self._fail("kerf_profile_mismatch", "cut kerf differs from its operation profile", op, expected=int(_value(profile, "kerf")), actual=kerf)
            if axis not in (0, 1, 2) or retained + kerf >= size[axis]:
                self._fail("invalid_operation_geometry", "cut must leave two positive children and positive kerf", op)
            side = _value(op, "retained_side")
            if side not in ("min", "max"):
                self._fail("retained_side", "v2 cuts require retained_side min or max", op)
            if profile_name == "separation":
                segment = self.segments[pid]
                if axis != 1 or _id(op) != str(_value(segment, "separation_operation")):
                    self._fail("source_separation", "each source root may only be consumed by its declared Y separation cut", op, pid)
                if side != "min":
                    self._fail("source_separation", "allocated windows retain the minimum Y child", op)
                if size[1] - retained - kerf <= 0:
                    self._fail("source_reserve", "separation must leave a positive external terminal reserve", op)
            elif profile_name == "preparation":
                if axis not in (0, 1):
                    self._fail("preparation_axis", "strip preparation cuts are restricted to X rips and Y end trims", op)
                if axis == 0:
                    minimum_rip = int(_value(_value(_value(self.plan, "shop"), "cutting"), "minimum_rip_width"))
                    if size[0] < minimum_rip or retained < minimum_rip:
                        self._fail("minimum_rip_width", "rip input and retained strip must meet the shop minimum rip width", op, pid, expected=minimum_rip, actual={"input": size[0], "retained": retained})
                if axis == 1 and meta.phase not in {"blank", "rough", "strip"}:
                    self._fail("end_preparation", "Y end preparation must occur before panel assembly", op)
            elif profile_name == "slicing":
                if axis != 1 or side != "min" or retained != int(_value(self.grid, "slice_length")):
                    self._fail("slicing_geometry", "slicing extracts minimum-side grid-length slices along Y", op)
                if size[0] != int(_value(self.grid, "columns")) * int(_value(self.grid, "pitch")) or size[2] != int(_value(self.grid, "panel_thickness")):
                    self._fail("slicing_geometry", "slicing requires the complete prepared panel width and thickness", op, pid)
                if size[1] - retained - kerf < int(_value(_value(_value(self.plan, "shop"), "cutting"), "slicing_reserve")):
                    self._fail("slicing_reserve", "every slice cut must leave the configured positive terminal reserve", op, pid)
                minimum = int(_value(_value(_value(self.plan, "shop"), "cutting"), "slice_min")); maximum = int(_value(_value(_value(self.plan, "shop"), "cutting"), "slice_max"))
                if not minimum <= retained <= maximum:
                    self._fail("slice_range", "slice length is outside shop slicing bounds", op, expected=[minimum, maximum], actual=retained)
            else:  # final trim
                if axis not in (0, 1) or side not in ("min", "max") or _value(op, "category") != "trim":
                    self._fail("final_trim", "only retained X/Y trim cuts may follow final glue", op)

        elif kind == "surface":
            if len(snapshots) != 1:
                self._fail("operation_shape", "surface needs exactly one input", op)
            pid, meta, size = snapshots[0]
            axis = int(_value(op, "axis")); side = _value(op, "side"); amount = int(_value(op, "amount"))
            self._increment(amount, "surface amount", op)
            if side not in ("min", "max") or not 0 < amount < size[axis]:
                self._fail("invalid_operation_geometry", "surface removal must remove a positive proper face", op)
            process = self._qualifying_surface(op, meta, axis, abs(meta.grain[axis]) == 1)
            self._check_input_profile(process, size, op, pid)
            if not bool(_value(process, "glue_ready")):
                self._fail("surface_process", "surface operation does not use a glue-ready qualifying process", op, actual=_value(op, "process"))
            if meta.phase == "root":
                self._fail("source_separation", "rough source roots may only undergo their declared separation cut", op, pid)
            if meta.phase in {"blank", "rough", "strip"}:
                if axis not in (0, 2):
                    self._fail("preparation_axis", "pre-panel surfacing is restricted to X and Z faces", op)
            elif meta.phase in {"panel", "panel_ready"}:
                if meta.sliced_count:
                    self._fail("slicing_lineage", "panel remainders may not be resurfaced after slicing begins", op, pid)
                if axis != 2:
                    self._fail("panel_preparation", "assembled panels require Z-face preparation before slicing", op)
                if not bool(_value(process, "glue_ready")):
                    self._fail("panel_preparation", "panel Z preparation requires a glue-ready process", op)
            elif meta.phase in {"final", "final_finished"}:
                if axis != 2 or _value(op, "process") != _value(_value(self.plan, "finishing"), "method"):
                    self._fail("finishing_process_mismatch", "final Z finishing must use the declared finishing method", op)
            else:
                self._fail("construction_phase", "surfacing is not permitted at this phase", op, pid, actual=meta.phase)

        elif kind == "rotate":
            if len(snapshots) != 1 or snapshots[0][1].phase != "slice":
                self._fail("rotation_lineage", "only a direct extracted slice may be rotated", op)
            perm = list(_value(op, "perm", [])); sign = list(_value(op, "sign", []))
            normal = ([0, 2, 1], [1, -1, 1]); reverse = ([0, 2, 1], [-1, 1, 1])
            if (perm, sign) not in (normal, reverse):
                self._fail("row_rotation", "rows must use one of the two declared direct slice rotations", op)
        elif kind == "glue":
            self._before_glue(op, snapshots)
        else:
            self._fail("operation_kind", "v2 operation kind is not supported", op)
        self.pending[_id(op)] = (op, snapshots)

    def _before_glue(self, op: Any, snapshots: list[tuple[str, _Meta, tuple[int, int, int]]]) -> None:
        stage = _value(op, "stage"); axis = int(_value(op, "axis"))
        if not bool(_value(op, "prepared_faces")):
            self._fail("unprepared_glue_faces", "v2 glue operations may not assert unprepared mating faces", op)
        if not bool(_value(op, "negligible_glue_line")):
            self._fail("glue_line", "v2 restricted construction requires negligible glue lines", op)
        if stage == "first":
            if axis != 0 or len(snapshots) < 2:
                self._fail("first_glue_orientation", "first glue joins at least two strips along X", op)
            if any(m.phase not in {"blank", "rough", "strip"} for _, m, _ in snapshots):
                self._fail("first_glue_lineage", "first glue inputs must be unrotated prepared strips", op)
            self._check_prepared_strips(op, snapshots)
            output = str(_value(op, "output"))
            panel_name = self._panel_by_part.get(output)
            if panel_name is None:
                self._fail("panel_declaration", "every first glue output must be declared as a physical panel", op, output)
            panel = self.panels[panel_name]
            declared = [str(x) for x in _value(panel, "strips", [])]
            actual = [pid for pid, _, _ in snapshots]
            if declared != actual:
                self._fail("panel_strips", "physical panel strip list must exactly match its first glue inputs", op, expected=declared, actual=actual)
            self._check_panel_recipe(panel_name, actual, op)
        elif stage == "final":
            if self.final_glue is not None or axis != 1 or len(snapshots) < 2:
                self._fail("final_glue_orientation", "exactly one final Y glue needs at least two rows", op)
            if any(m.phase != "rotated" for _, m, _ in snapshots):
                self._fail("row_lineage", "final glue inputs must be direct rotated slices", op)
            self._check_final_rows(op, snapshots)
        else:
            self._fail("glue_stage", "v2 construction supports only first and final glue stages", op)

    def _check_prepared_strips(self, op: Any, snapshots: list[tuple[str, _Meta, tuple[int, int, int]]]) -> None:
        pitch = int(_value(self.grid, "pitch")); thickness = int(_value(self.grid, "strip_thickness"))
        for pid, meta, size in snapshots:
            if size[2] != thickness or size[0] <= 0 or size[0] % pitch:
                self._fail("prepared_strip_dimensions", "prepared strips require pitch-multiple X width and declared thickness", op, pid)
            if meta.grain != (0, 1, 0):
                self._fail("strip_grain", "prepared strips must preserve +Y grain", op, pid)
            prep = self._prep(meta)
            # Face flags alone cannot prove that an original raw X/Z source face was
            # actually removed: a small rip and a later joint must not launder that
            # requirement.  Verify the exact provenance boxes retained in the strip.
            part = self.parts[pid]
            for axis, lo_name, hi_name, root_extent in ((0, "x_min", "x_max", int(_value(self.stock_types[meta.source_type or ""], "width"))),
                                                        (2, "z_min", "z_max", int(_value(self.stock_types[meta.source_type or ""], "thickness")))):
                lo = min(region.source.origin[axis] for region in part.regions)
                hi = max(region.source.origin[axis] + region.source.size[axis] for region in part.regions)
                if lo < int(_value(prep, lo_name)) or hi > root_extent - int(_value(prep, hi_name)):
                    self._fail("preparation_allowance", "strip provenance retains an insufficiently prepared raw source face", op, pid,
                               expected={"min": int(_value(prep, lo_name)), "max": root_extent - int(_value(prep, hi_name))}, actual={"min": lo, "max": hi})
            for axis, side, req_name in ((0, "min", "x_min"), (0, "max", "x_max"), (1, "min", "y_min"), (1, "max", "y_max"), (2, "min", "z_min"), (2, "max", "z_max")):
                face = meta.faces[(axis, side)]; requirement = int(_value(prep, req_name))
                # Raw faces need their named source allowance; a rip boundary instead
                # needs fresh-face jointing and may not borrow its old neighbour's credit.
                if axis == 0 and face["cut"]:
                    joint = int(_value(_value(_value(self.plan, "shop"), "cutting"), "new_face_jointing"))
                    if not face["ready"] or int(face["removed"]) < joint:
                        self._fail("fresh_face_preparation", "fresh X cut faces require explicit qualifying jointing", op, pid, expected=joint, actual=face)
                elif axis == 1:
                    if not face["cut_prepared"] or int(face["removed"]) < requirement:
                        self._fail("end_allowance", "both strip ends need explicit blank-relative trim allowances", op, pid, expected=requirement, actual=face)
                elif axis == 0 and (not face["ready"] or int(face["removed"]) < requirement):
                    self._fail("preparation_allowance", "raw longitudinal faces need their allowance and a glue-ready surface", op, pid, expected=requirement, actual=face)
                elif axis == 2 and (not face["ready"] or int(face["removed"]) < requirement):
                    self._fail("preparation_allowance", "raw Z faces need their allowance and a qualifying glue-ready surface", op, pid, expected=requirement, actual=face)
                elif int(face["removed"]) < requirement:
                    self._fail("preparation_allowance", "prepared strip does not satisfy all declared raw-face allowances", op, pid, expected=requirement, actual=face)

    def _recipe_cells(self, recipe: Any) -> list[str]:
        cells = _value(recipe, "cells", [])
        # schemas may represent the visual row as a flat list or a one-row grid.
        if cells and isinstance(cells[0], (list, tuple)):
            if len(cells) != 1:
                self._fail("recipe_cells", "N1 recipes describe exactly one X row of cells", actual=cells)
            cells = cells[0]
        return [str(x) for x in cells]

    def _check_panel_recipe(self, panel_name: str, strip_ids: list[str], op: Any) -> None:
        """Compare every declared visual cell to exact physical region intersections."""
        panel = self.panels[panel_name]; recipe_id = str(_value(panel, "recipe")); recipe = self.recipes.get(recipe_id)
        if recipe is None:
            self._fail("recipe_missing", "panel names an unknown recipe", op, actual=recipe_id)
        cells = self._recipe_cells(recipe)
        pitch = int(_value(self.grid, "pitch")); width = int(_value(self.grid, "columns")) * pitch
        if len(cells) != int(_value(self.grid, "columns")):
            self._fail("recipe_cells", "recipe cell count must equal grid columns", op, expected=int(_value(self.grid, "columns")), actual=len(cells))
        if not strip_ids:
            self._fail("panel_strips", "panel must have at least one physical strip", op)
        physical: list[tuple[int, Any]] = []
        offset = 0
        for strip in strip_ids:
            part = self.parts.get(strip)
            if part is None:
                self._fail("panel_strips", "declared physical strip is not live", op, strip)
            physical.append((offset, part)); offset += _size(part)[0]
        if offset != width:
            self._fail("panel_width", "physical strip widths must exactly cover declared grid width", op, expected=width, actual=offset)
        y, z = _size(physical[0][1])[1:]
        for offset, part in physical[1:]:
            if _size(part)[1:] != (y, z):
                self._fail("panel_strips", "physical strips must share panel Y/Z extents", op, part=part.id)
        for index, species in enumerate(cells):
            cell = Box((index * pitch, 0, 0), (pitch, y, z))
            hits = []
            for offset, part in physical:
                for region in part.regions:
                    shifted = Box((region.current.origin[0] + offset, region.current.origin[1], region.current.origin[2]), region.current.size)
                    hit = shifted.intersect(cell)
                    if hit is not None:
                        hits.append((region.species, hit.volume))
            if sum(volume for _, volume in hits) != cell.volume or any(actual != species for actual, _ in hits):
                self._fail("recipe_sequence_mismatch", "each visual recipe cell must be exactly covered by its declared species", op, expected=species, actual=hits)

    def _maybe_register_single_panel(self, pid: str, meta: _Meta, part: Any, op: Any) -> None:
        """Register a one-strip panel without manufacturing a fictitious glue joint."""
        size = _size(part)
        candidates = [
            (name, panel) for name, panel in self.panels.items()
            if _value(panel, "part") == pid and [str(x) for x in _value(panel, "strips", [])] == [pid]
        ]
        if not candidates:
            return
        if meta.phase not in {"blank", "rough", "strip"}:
            return
        name, panel = candidates[0]
        # Registration is allowed only after the material genuinely qualifies as a
        # prepared strip.  The next panel-Z surface is then independently checked.
        self._check_prepared_strips(op, [(pid, meta, size)])
        self._check_panel_recipe(name, [pid], op)
        meta.phase = "panel"
        meta.panel = name
        meta.strips = (pid,)
        self._reset_panel_z_faces(meta)
        self._single_panels[pid] = panel
        self._single_panel_snapshots[pid] = part
        self._registered_panels.add(name)

    def _check_final_rows(self, op: Any, snapshots: list[tuple[str, _Meta, tuple[int, int, int]]]) -> None:
        ids = [pid for pid, _, _ in snapshots]
        declared = [str(_value(r, "rotated_part")) for r in self.rows]
        if declared != ids or len(set(declared)) != len(declared):
            self._fail("row_assignment_mismatch", "declared rows must be an ordered bijection with final glue inputs", op, expected=declared, actual=ids)
        for (pid, meta, _), row in zip(snapshots, self.rows):
            if meta.panel != str(_value(row, "panel")) or meta.row_reversed != bool(_value(row, "reversed", False)):
                self._fail("row_assignment_mismatch", "row declaration must name the actual panel and rotation", op, pid)
            panel = self.panels.get(meta.panel or "")
            if panel is None or str(_value(panel, "recipe")) != str(_value(row, "recipe")):
                self._fail("row_recipe", "row recipe must equal its physical panel recipe", op, pid)

    def after(self, op: Any, parts: dict[str, Any]) -> None:
        """Carry face/phase evidence across replay's already-validated geometry."""
        pending = self.pending.pop(_id(op), None)
        if pending is None:
            self._fail("construction_state", "operation completed without a pre-consumption state check", op)
        _, snapshots = pending
        kind = _kind(op)
        outputs = _outputs(op)
        for output in outputs:
            self._produced_by[output] = op
        if kind == "cut":
            pid, meta, old_size = snapshots[0]
            axis = int(_value(op, "axis")); side = str(_value(op, "retained_side")); retained = str(_value(op, "outputs")[0])
            residual = str(_value(op, "outputs")[1])
            left = self._copy_meta(meta); right = self._copy_meta(meta)
            # output[0] is the declared retained child. retained_side determines which
            # source boundary it preserves; its opposite is a brand-new saw face.
            retained_new_side = "max" if side == "min" else "min"
            residual_new_side = "min" if side == "min" else "max"
            # Retained-side cuts replace one boundary.  Save its blank-relative
            # distance before reset so repeated trims on the same end accumulate.
            prior_replaced = int(left.faces[(axis, retained_new_side)]["removed"])
            self._fresh_face(left, axis, retained_new_side)
            self._fresh_face(right, axis, residual_new_side)
            profile = self._cut_profile_name(op, meta)
            if profile == "separation":
                left.phase = "blank"; right.phase = "reserve"
                self._blank_lengths[retained] = _size(parts[retained])[1]
            elif profile == "slicing":
                left.phase = "slice"; left.panel = meta.panel; left.sliced_count = meta.sliced_count + 1
                right.phase = "panel_ready"; right.panel = meta.panel; right.sliced_count = meta.sliced_count + 1
                self._slices[retained] = meta.panel or ""
            elif profile == "final_trim":
                left.phase = "final_finished"; right.phase = "discard"
            else:
                left.phase = "rough"; right.phase = "rough"
                # Y cuts are explicit end preparation; only their new retained boundary
                # receives this evidence.  X cut boundaries remain fresh until jointed.
                if axis == 1:
                    face = left.faces[(axis, retained_new_side)]
                    face["cut_prepared"] = True
                    # The discarded child length is the actual removed allowance.
                    # A blank-relative end allowance consumes both the explicit
                    # terminal offcut and the saw kerf.  The external separation
                    # reserve is never eligible to donate this credit.
                    removed = prior_replaced + _size(parts[residual])[axis] + int(_value(op, "kerf"))
                    face["removed"] = removed
            self.meta[retained] = left; self.meta[residual] = right
        elif kind == "surface":
            pid, meta, _ = snapshots[0]
            output = str(_value(op, "output")); kept = self._copy_meta(meta)
            axis = int(_value(op, "axis")); side = str(_value(op, "side")); amount = int(_value(op, "amount"))
            face = kept.faces[(axis, side)]
            face["removed"] = int(face["removed"]) + amount
            process = next(x for x in _value(_value(self.plan, "shop"), "surfacing", []) if _value(x, "process") == _value(op, "process"))
            face["ready"] = bool(_value(process, "glue_ready"))
            if meta.phase in {"panel", "panel_ready"}:
                self._panel_z_faces.add(f"{output}:{side}")
                # Prepared faces are necessary but are not sufficient: intermediate
                # flattening passes remain panel preparation until target thickness.
                kept.phase = "panel_ready" if self._has_panel_z_pair(kept) and _size(parts[output])[2] == int(_value(self.grid, "panel_thickness")) else "panel"
            elif meta.phase in {"final", "final_finished"}:
                kept.phase = "final_finished"
            else:
                kept.phase = "strip"
            self.meta[output] = kept
            self.meta[str(_value(op, "removed"))] = self._copy_meta(meta, phase="discard")
        elif kind == "rotate":
            pid, meta, _ = snapshots[0]; output = str(_value(op, "output")); perm = list(_value(op, "perm")); sign = list(_value(op, "sign"))
            new = self._copy_meta(meta, phase="rotated")
            new.grain = tuple(sign[i] * meta.grain[perm[i]] for i in range(3))
            new.faces = {(out_axis, new_side): self._copy_face(meta.faces[(perm[out_axis], "min" if (new_side == "min") == (sign[out_axis] > 0) else "max")])
                         for out_axis in range(3) for new_side in ("min", "max")}
            new.row_reversed = sign == [-1, 1, 1]
            self.meta[output] = new
        else:  # glue
            output = str(_value(op, "output")); stage = _value(op, "stage")
            if stage == "first":
                panel_name = self._panel_by_part[output]
                new = self._copy_meta(snapshots[0][1], phase="panel")
                new.panel = panel_name; new.strips = tuple(pid for pid, _, _ in snapshots)
                self._reset_panel_z_faces(new)
                self.meta[output] = new
                self._registered_panels.add(panel_name)
            else:
                new = self._copy_meta(snapshots[0][1], phase="final")
                new.panel = None; new.strips = ()
                self.meta[output] = new
                self.final_glue = op; self._final_output = output
        self.parts = parts

    @staticmethod
    def _reset_panel_z_faces(meta: _Meta) -> None:
        # Strip thickness preparation is not panel flattening.  Assembly creates new
        # panel faces whose independent glue-ready evidence must be established before
        # slicing, even for a physical one-strip panel.
        for side in ("min", "max"):
            meta.faces[(2, side)] = {"raw": False, "removed": 0, "cut": False, "ready": False, "cut_prepared": False}

    def _has_panel_z_pair(self, meta: _Meta) -> bool:
        return all(meta.faces[(2, side)]["ready"] for side in ("min", "max")) and all(meta.faces[(2, side)]["removed"] > 0 for side in ("min", "max"))

    @staticmethod
    def _copy_face(face: Face) -> Face:
        return dict(face)

    def _copy_meta(self, meta: _Meta, phase: str | None = None) -> _Meta:
        return _Meta(phase or meta.phase, meta.source_type, meta.source_segment,
                     {key: self._copy_face(value) for key, value in meta.faces.items()},
                     meta.grain, meta.panel, meta.strips, meta.row_reversed, meta.sliced_count)

    @staticmethod
    def _fresh_face(meta: _Meta, axis: int, side: str) -> None:
        meta.faces[(axis, side)] = {"raw": False, "removed": 0, "cut": True, "ready": False, "cut_prepared": False}

    def finish(self, rep: Any) -> Any:
        """Validate terminal construction lineage and return the final glue operation."""
        if self.final_glue is None or self._final_output is None:
            self._fail("construction_template", "v2 requires exactly one final Y glue")
        terminal = str(_value(_value(self.plan, "finishing"), "terminal"))
        if terminal != str(_value(self.plan, "finishing").terminal):  # defensive duck-type sanity
            self._fail("missing_terminal", "invalid finishing terminal declaration")
        current = terminal
        saw_final_z = {"min": False, "max": False}
        while current != self._final_output:
            op = self._produced_by.get(current)
            if op is None:
                self._fail("finishing_lineage", "finished terminal does not descend from final glue", part=current)
            if _kind(op) == "surface" and str(_value(op, "output")) == current:
                if int(_value(op, "axis")) != 2 or _value(op, "process") != _value(_value(self.plan, "finishing"), "method"):
                    self._fail("finishing_lineage", "only declared final Z finishing may follow final glue", op)
                saw_final_z[str(_value(op, "side"))] = True
                current = str(_value(op, "input"))
            elif _kind(op) == "cut" and str(_value(op, "outputs")[0]) == current:
                if int(_value(op, "axis")) not in (0, 1) or _value(op, "retained_side") not in ("min", "max") or _value(op, "category") != "trim":
                    self._fail("finishing_lineage", "only retained final X/Y trim cuts may follow final glue", op)
                current = str(_value(op, "input"))
            else:
                self._fail("finishing_lineage", "terminal must follow retained final surfaces and trim cuts", op, current)
        if not all(saw_final_z.values()):
            self._fail("missing_end_grain_finishing", "final construction requires retained declared-process Z finishing on both faces", part=terminal)
        missing = set(self.panels) - self._registered_panels
        if missing:
            self._fail("panel_declaration", "every declared physical panel must actually be registered", actual=sorted(missing))
        # A one-strip panel is real material, not a synthetic first-stage glue.  Its
        # snapshot is taken while it is live at registration; it is intentionally
        # retained even after the panel is surfaced, sliced, and consumed.
        rep.first_glue_panels.update(self._single_panel_snapshots)
        return self.final_glue
