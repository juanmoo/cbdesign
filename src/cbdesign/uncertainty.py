"""F1 conservative, opt-in dimensional uncertainty validation.

This module is deliberately separate from nominal replay.  Its declaration is a
versioned sidecar whose named settings are bounded variables.  Dimensions are
propagated as exact affine :class:`fractions.Fraction` expressions, retaining a
variable's identity wherever it is shared.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
from typing import Any

from .models import Cut, Glue, Rotate, Surface
from .models_v2 import PlanV2

CONTRACT = "cbdesign-uncertainty/v1"


def plan_digest(plan: PlanV2) -> str:
    """Return the canonical SHA-256 digest to which a sidecar is bound."""
    payload = plan.model_dump(mode="json")
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Affine:
    constant: Fraction = Fraction(0)
    terms: tuple[tuple[str, Fraction], ...] = ()

    @classmethod
    def variable(cls, name: str) -> "Affine": return cls(Fraction(0), ((name, Fraction(1)),))
    @classmethod
    def number(cls, value: int | Fraction) -> "Affine": return cls(Fraction(value))
    def _map(self) -> dict[str, Fraction]: return dict(self.terms)
    def __add__(self, other: "Affine") -> "Affine":
        values = self._map()
        for name, coefficient in other.terms: values[name] = values.get(name, Fraction(0)) + coefficient
        return Affine(self.constant + other.constant, tuple(sorted((n, c) for n, c in values.items() if c)))
    def __sub__(self, other: "Affine") -> "Affine": return self + other.scale(-1)
    def scale(self, amount: int) -> "Affine": return Affine(self.constant * amount, tuple((n, c * amount) for n, c in self.terms))
    def interval(self, variables: dict[str, tuple[Fraction, Fraction]]) -> tuple[Fraction, Fraction]:
        lo = hi = self.constant
        for name, coefficient in self.terms:
            low, high = variables[name]
            lo += coefficient * (low if coefficient >= 0 else high)
            hi += coefficient * (high if coefficient >= 0 else low)
        return lo, hi
    def same(self, other: "Affine") -> bool: return self == other


def _as_fraction(value: Any) -> Fraction:
    if isinstance(value, bool): raise ValueError("boolean is not a dimensional bound")
    return Fraction(value)


def _interval(expr: Affine, variables: dict[str, tuple[Fraction, Fraction]]) -> list[str]:
    lo, hi = expr.interval(variables)
    def text(v: Fraction) -> str: return str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"
    return [text(lo), text(hi)]


def _ref(value: Any, variables: dict[str, tuple[Fraction, Fraction]], errors: list[dict], where: str) -> Affine | None:
    if not isinstance(value, str) or value not in variables:
        errors.append({"code": "missing_declaration", "where": where, "message": "requires a declared named variable"})
        return None
    return Affine.variable(value)


def validate_uncertainty(plan: PlanV2, declaration: dict[str, Any]) -> dict[str, Any]:
    """Validate a V2 plan against an explicit F1 uncertainty sidecar.

    The returned result never changes nominal validation.  ``dimensionally_valid``
    is false for missing declarations, unsupported semantics, or failed bounds.
    See decision 0004 for the exact sidecar shape.
    """
    errors: list[dict] = []; unsupported: list[dict] = []; checks: list[dict] = []
    if not isinstance(plan, PlanV2):
        return {"status": "unsupported", "dimensionally_valid": False, "nominal_valid": False, "unsupported": [{"code": "plan_version", "message": "F1 supports cbdesign-plan/v2 only"}], "failed": [], "coverage": []}
    # Dimensional bounds are an additional label, never a replacement for nominal
    # replay. A constructed/model-copied PlanV2 can still be nominally invalid.
    from .replay import ReplayError, replay
    try:
        replay(plan)
    except ReplayError as error:
        return {"status": "invalid", "dimensionally_valid": False, "nominal_valid": False,
                "contract": CONTRACT, "plan_digest": plan_digest(plan),
                "final_intervals_um": {}, "failed": [{"code": "nominal_replay_invalid", "nominal": error.diagnostic}],
                "unsupported": [], "coverage": []}
    if not isinstance(declaration, dict) or declaration.get("version") != CONTRACT:
        errors.append({"code": "contract_version", "message": f"sidecar version must be {CONTRACT!r}"})
        declaration = declaration if isinstance(declaration, dict) else {}
    actual_digest = plan_digest(plan)
    if declaration.get("plan_digest") != actual_digest:
        errors.append({"code": "digest_mismatch", "expected": actual_digest, "actual": declaration.get("plan_digest")})
    raw_variables = declaration.get("variables")
    variables: dict[str, tuple[Fraction, Fraction]] = {}
    nominal: dict[str, Fraction] = {}
    if not isinstance(raw_variables, dict):
        errors.append({"code": "missing_declaration", "where": "variables"}); raw_variables = {}
    for name, value in raw_variables.items():
        try:
            if not isinstance(value, dict) or set(value) != {"nominal", "min", "max"}: raise ValueError("requires nominal, min, max")
            low, high, mid = _as_fraction(value["min"]), _as_fraction(value["max"]), _as_fraction(value["nominal"])
            if low > high or not low <= mid <= high: raise ValueError("requires min <= nominal <= max")
            variables[name] = (low, high); nominal[name] = mid
        except (ValueError, TypeError, ZeroDivisionError) as exc:
            errors.append({"code": "invalid_variable", "variable": name, "message": str(exc)})
    def fail(code: str, message: str, **more: Any) -> None: errors.append({"code": code, "message": message, **more})
    def nominal_value(expr: Affine) -> Fraction:
        return expr.interval({n: (nominal[n], nominal[n]) for n in nominal})[0]
    def require_nominal(expr: Affine | None, expected: int | Fraction, where: str) -> None:
        if expr is not None and nominal_value(expr) != Fraction(expected):
            fail("nominal_binding", "declared variable nominal does not equal nominal command", where=where, expected=str(expected))
    def positive(expr: Affine, where: str) -> None:
        lo, _ = expr.interval(variables)
        if lo <= 0: fail("nonpositive_dimension", "minimum possible dimension must be positive", where=where, interval_um=_interval(expr, variables))
    def capacity(size: list[Affine], where: str, profile: Any = None) -> None:
        maximum = list(profile.max_input if profile else plan.shop.max_workpiece)
        minimum = list(profile.min_input) if profile else [1, 1, 1]
        for axis, expr in enumerate(size):
            lo, hi = expr.interval(variables)
            if lo < int(minimum[axis]): fail("minimum_capacity", "actual workpiece can be below supported minimum", where=where, axis=axis, interval_um=_interval(expr, variables), minimum_um=int(minimum[axis]))
            if hi > int(maximum[axis]): fail("maximum_capacity", "actual workpiece can exceed supported maximum", where=where, axis=axis, interval_um=_interval(expr, variables), maximum_um=int(maximum[axis]))
    roots = declaration.get("roots")
    if not isinstance(roots, dict): fail("missing_declaration", "every source root requires explicit x/y/z variables", where="roots"); roots = {}
    types = {stock.id: stock for stock in plan.stock_types}
    parts: dict[str, list[Affine]] = {}
    for segment in plan.source_segments:
        root = roots.get(segment.id)
        if not isinstance(root, dict) or set(root) != {"x", "y", "z"}:
            fail("missing_declaration", "source root needs exactly x, y, z named variables", where=f"roots.{segment.id}"); continue
        dimensions = [_ref(root[axis], variables, errors, f"roots.{segment.id}.{axis}") for axis in "xyz"]
        if any(d is None for d in dimensions): continue
        expected = [int(types[segment.stock_type].width), int(segment.length), int(types[segment.stock_type].thickness)]
        for axis, (expr, amount) in enumerate(zip(dimensions, expected)): require_nominal(expr, amount, f"roots.{segment.id}.{axis}")
        parts[segment.id] = dimensions  # type: ignore[assignment]
        capacity(parts[segment.id], f"root:{segment.id}")
    operation_specs = declaration.get("operations")
    if not isinstance(operation_specs, dict): fail("missing_declaration", "every operation requires an uncertainty declaration", where="operations"); operation_specs = {}
    final_intervals: dict[str, list[str]] = {}
    for operation in plan.operations:
        spec = operation_specs.get(operation.id)
        if not isinstance(spec, dict):
            fail("missing_declaration", "operation has no uncertainty declaration", where=f"operations.{operation.id}"); continue
        try:
            if isinstance(operation, Cut):
                if set(spec) != {"kerf", "retained"}: raise ValueError("cut requires kerf and retained")
                source = parts[operation.input]; kerf = _ref(spec["kerf"], variables, errors, f"operations.{operation.id}.kerf")
                retained_spec = spec["retained"]
                if kerf is None or not isinstance(retained_spec, dict): raise ValueError("invalid cut setting")
                require_nominal(kerf, int(operation.kerf), f"operations.{operation.id}.kerf")
                mode = retained_spec.get("mode")
                setting = _ref(retained_spec.get("variable"), variables, errors, f"operations.{operation.id}.retained.variable")
                if setting is None: continue
                if mode == "machine_to_target":
                    retained = setting; require_nominal(retained, int(operation.retained), f"operations.{operation.id}.retained")
                elif mode == "remove_by":
                    # The nominal removal must account for the *full* affine input,
                    # not just its constant term (roots and preceding settings may
                    # themselves carry named nominal offsets).
                    require_nominal(setting, nominal_value(source[operation.axis]) - int(operation.retained) - int(operation.kerf), f"operations.{operation.id}.retained")
                    retained = source[operation.axis] - setting - kerf
                else:
                    unsupported.append({"code": "cut_semantics", "operation": operation.id, "message": "retained mode must be machine_to_target or remove_by"}); continue
                other = source[operation.axis] - retained - kerf
                for label, value in (("retained", retained), ("other_child", other), ("kerf", kerf)):
                    positive(value, f"{operation.id}.{label}")
                profile = _cut_profile(plan, operation)
                capacity(source, operation.id, profile)
                first = list(source); second = list(source); first[operation.axis] = retained; second[operation.axis] = other
                capacity(first, f"{operation.id}:retained")
                capacity(second, f"{operation.id}:other_child")
                if operation.axis == 0:
                    min_width, _ = retained.interval(variables)
                    if min_width < int(plan.shop.cutting.minimum_rip_width):
                        fail("minimum_rip_width", "retained rip can fall below declared minimum width", operation=operation.id, interval_um=_interval(retained, variables), minimum_um=int(plan.shop.cutting.minimum_rip_width))
                if profile is plan.shop.cutting.slicing:
                    retained_low, retained_high = retained.interval(variables)
                    reserve_low, _ = other.interval(variables)
                    if retained_low < int(plan.shop.cutting.slice_min) or retained_high > int(plan.shop.cutting.slice_max):
                        fail("slice_bounds", "slice target lies outside declared slicing bounds", operation=operation.id, interval_um=_interval(retained, variables), minimum_um=int(plan.shop.cutting.slice_min), maximum_um=int(plan.shop.cutting.slice_max))
                    if reserve_low < int(plan.shop.cutting.slicing_reserve):
                        fail("slicing_reserve", "remainder can fall below declared slicing reserve", operation=operation.id, interval_um=_interval(other, variables), minimum_um=int(plan.shop.cutting.slicing_reserve))
                parts[operation.outputs[0]] = first; parts[operation.outputs[1]] = second
            elif isinstance(operation, Surface):
                if set(spec) not in ({"mode", "variable"}, {"mode", "variable", "guard"}): raise ValueError("surface requires mode, variable, and target guard where applicable")
                source = parts[operation.input]; setting = _ref(spec.get("variable"), variables, errors, f"operations.{operation.id}.variable")
                if setting is None: continue
                mode = spec.get("mode")
                capacity(source, operation.id, _surface_profile(plan, operation))
                kept = list(source)
                if mode == "remove_by":
                    require_nominal(setting, int(operation.amount), f"operations.{operation.id}.variable")
                    kept[operation.axis] = source[operation.axis] - setting
                    positive(setting, f"{operation.id}.removed")
                elif mode == "machine_to_target":
                    guard = _ref(spec.get("guard"), variables, errors, f"operations.{operation.id}.guard")
                    if guard is None: continue
                    # A target setting must reproduce the nominal removal command;
                    # otherwise it can silently change the plan even at nominal values.
                    require_nominal(setting, nominal_value(source[operation.axis]) - int(operation.amount), f"operations.{operation.id}.variable")
                    require_nominal(guard, int(operation.amount), f"operations.{operation.id}.guard")
                    guard_low, guard_high = guard.interval(variables)
                    if guard_low <= 0:
                        fail("nonpositive_material_guard", "machine-to-target removal guard must remain positive", operation=operation.id, interval_um=_interval(guard, variables))
                    kept[operation.axis] = setting
                    lo, _ = source[operation.axis].interval(variables); _, target_hi = setting.interval(variables)
                    if lo < target_hi + guard_high: fail("insufficient_material_guard", "machine-to-target surface lacks material for target plus removal guard", operation=operation.id)
                else:
                    unsupported.append({"code": "surface_semantics", "operation": operation.id, "message": "surface mode must be remove_by or machine_to_target"}); continue
                positive(kept[operation.axis], f"{operation.id}.output")
                capacity(kept, f"{operation.id}:output")
                parts[operation.output] = kept
            elif isinstance(operation, Rotate):
                if spec != {"mode": "rigid"}: raise ValueError("rotate requires mode rigid")
                source = parts[operation.input]; rotated = [source[index] for index in operation.perm]
                capacity(rotated, f"{operation.id}:output")
                parts[operation.output] = rotated
            elif isinstance(operation, Glue):
                if spec != {"glue_line": "negligible"}: raise ValueError("glue requires explicit negligible glue_line")
                inputs = [parts[item] for item in operation.inputs]
                for axis in range(3):
                    if axis == operation.axis: continue
                    baseline = inputs[0][axis]
                    for item, candidate in zip(operation.inputs[1:], inputs[1:]):
                        difference = baseline - candidate[axis]
                        # Syntactically distinct zero-width settings are exact constants;
                        # otherwise require equality for every allowed realization, not
                        # merely overlapping independent intervals.
                        if not baseline.same(candidate[axis]) and difference.interval(variables) != (Fraction(0), Fraction(0)):
                            fail("uncertain_glue_mismatch", "non-glue extents must be identical affine expressions for all realizations", operation=operation.id, axis=axis, left=operation.inputs[0], right=item)
                combined = list(inputs[0]); combined[operation.axis] = sum((item[operation.axis] for item in inputs), Affine.number(0))
                capacity(combined, f"{operation.id}:output")
                parts[operation.output] = combined
            else: unsupported.append({"code": "operation_kind", "operation": operation.id})
        except KeyError:
            fail("missing_uncertainty_input", "operation input has no supported uncertainty state", operation=operation.id)
        except (ValueError, TypeError, AttributeError, IndexError, ZeroDivisionError) as exc:
            # Sidecars are user JSON. A malformed nested list/object must remain a
            # validation diagnostic, not escape as a Python exception.
            fail("invalid_operation_declaration", str(exc), operation=operation.id)
    terminal = parts.get(plan.finishing.terminal)
    if terminal is None: fail("missing_terminal_state", "terminal lacks uncertainty state")
    else:
        final_intervals = {axis: _interval(expr, variables) for axis, expr in zip("xyz", terminal)}
        tolerance = declaration.get("final_tolerance")
        if not isinstance(tolerance, dict) or set(tolerance) != {"x", "y", "z"}:
            fail("missing_declaration", "final_tolerance requires x, y, z closed bounds", where="final_tolerance")
        else:
            for axis, expr in zip("xyz", terminal):
                bound = tolerance[axis]
                try:
                    low, high = _as_fraction(bound[0]), _as_fraction(bound[1])
                    actual_low, actual_high = expr.interval(variables)
                    if actual_low < low or actual_high > high: fail("final_tolerance", "final interval lies outside declared tolerance", axis=axis, actual_um=_interval(expr, variables), allowed_um=[str(low), str(high)])
                except (TypeError, ValueError, ZeroDivisionError, IndexError, KeyError, AttributeError):
                    fail("invalid_final_tolerance", "tolerance must be a two-item [min, max]", axis=axis)
    return {"status": "dimensionally_valid" if not errors and not unsupported else "invalid", "dimensionally_valid": not errors and not unsupported, "nominal_valid": True, "contract": CONTRACT, "plan_digest": actual_digest, "final_intervals_um": final_intervals, "failed": errors, "unsupported": unsupported, "coverage": ["exact_affine_fraction_propagation", "shared_named_variables", "interval_enclosure", "positive_children_and_reserves", "actual_workpiece_capacity", "all_realizations_glue_equality", "final_tolerance"]}


def _cut_profile(plan: PlanV2, op: Cut):
    """Derive the V2 cut stage from topology, never from operation naming."""
    separation_ids = {segment.separation_operation for segment in plan.source_segments}
    if op.id in separation_ids:
        return plan.shop.cutting.separation
    producers: dict[str, object] = {}
    for candidate in plan.operations:
        outputs = list(candidate.outputs) if isinstance(candidate, Cut) else [candidate.output] + ([candidate.removed] if isinstance(candidate, Surface) else [])
        for output in outputs: producers[output] = candidate
    seen: set[str] = set()
    def has_glue_stage(part: str, stage: str, visiting: set[str] | None = None) -> bool:
        visiting = set() if visiting is None else visiting
        if part in visiting: return False
        visiting.add(part)
        producer = producers.get(part)
        if producer is None: return False
        if isinstance(producer, Glue):
            return producer.stage == stage or any(has_glue_stage(item, stage, visiting) for item in producer.inputs)
        if isinstance(producer, (Cut, Surface, Rotate)):
            return has_glue_stage(producer.input, stage, visiting)
        return False
    # A final trim is a trim descendant of the final glue. Source end cuts are
    # preparation even though nominally categorized as trim material losses.
    if op.category == "trim" and has_glue_stage(op.input, "final"):
        return plan.shop.cutting.final_trim
    # A slice is a Y cut of a first-stage panel descendant, retaining a row and
    # creating its terminal/remainder sibling. Other Y preparation cuts stay
    # preparation even if users rename operations.
    if op.axis == 1 and op.category == "other_offcuts" and has_glue_stage(op.input, "first"):
        return plan.shop.cutting.slicing
    return plan.shop.cutting.preparation


def _surface_profile(plan: PlanV2, op: Surface):
    matches = [profile for profile in plan.shop.surfacing if profile.process == op.process]
    if not matches: raise ValueError(f"unknown surfacing process {op.process!r}")
    return matches[0]


def illustrative_uncertainty(plan: PlanV2) -> dict[str, Any]:
    """Return a zero-width *illustrative* sidecar, not shop measurement data.

    It exists only to demonstrate the complete declaration shape.  Users must
    replace every setting with measured nonzero bounds before relying on F1.
    """
    variables: dict[str, dict[str, int]] = {}
    def add(name: str, value: int) -> str:
        variables[name] = {"nominal": value, "min": value, "max": value}; return name
    roots = {}
    types = {stock.id: stock for stock in plan.stock_types}
    for segment in plan.source_segments:
        stock = types[segment.stock_type]
        roots[segment.id] = {axis: add(f"root.{segment.id}.{axis}", value) for axis, value in zip("xyz", (int(stock.width), int(segment.length), int(stock.thickness)))}
    operations: dict[str, Any] = {}
    # Derived nominal input extents provide target settings only; this is intentionally
    # illustrative and has zero uncertainty, rather than pretending to be a profile.
    from .replay import replay
    result = replay(plan)
    for op in plan.operations:
        if isinstance(op, Cut): operations[op.id] = {"kerf": add(f"kerf.{op.id}", int(op.kerf)), "retained": {"mode": "machine_to_target", "variable": add(f"target.{op.id}", int(op.retained))}}
        elif isinstance(op, Surface): operations[op.id] = {"mode": "remove_by", "variable": add(f"remove.{op.id}", int(op.amount))}
        elif isinstance(op, Rotate): operations[op.id] = {"mode": "rigid"}
        elif isinstance(op, Glue): operations[op.id] = {"glue_line": "negligible"}
    return {"version": CONTRACT, "plan_digest": plan_digest(plan), "variables": variables, "roots": roots, "operations": operations, "final_tolerance": {axis: [size, size] for axis, size in zip("xyz", result.parts[result.terminal].size)}, "assumptions": ["Illustrative zero-width bounds only; replace with measured, nonzero process bounds."]}
