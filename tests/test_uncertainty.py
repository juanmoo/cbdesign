import json
from fractions import Fraction
from pathlib import Path

from cbdesign.models import load_plan
from cbdesign.uncertainty import Affine, illustrative_uncertainty, plan_digest, validate_uncertainty


ROOT = Path(__file__).parents[1]


def plan():
    return load_plan(json.loads((ROOT / "examples/rough-stock-board.json").read_text()))


def declaration():
    return illustrative_uncertainty(plan())


def test_illustrative_sidecar_is_complete_but_explicitly_zero_width():
    result = validate_uncertainty(plan(), declaration())
    assert result["dimensionally_valid"]
    assert result["final_intervals_um"]["x"] == ["290000", "290000"]
    assert "zero-width" in declaration()["assumptions"][0]


def test_nonzero_shared_setting_is_accepted_when_shared_across_glue_faces():
    p = plan(); sidecar = illustrative_uncertainty(p)
    # Make every strip's longitudinal root a shared stock-length setting. All
    # resulting mating faces move together, so correlation is preserved exactly.
    shared = "shared.length"
    sidecar["variables"][shared] = {"nominal": 419000, "min": 418900, "max": 419100}
    for root in sidecar["roots"].values(): root["y"] = shared
    result = validate_uncertainty(p, sidecar)
    assert result["dimensionally_valid"]


def test_independent_root_errors_block_all_realizations_glue_compatibility():
    p = plan(); sidecar = illustrative_uncertainty(p)
    for name, root in sidecar["roots"].items():
        stock_is_maple = name.startswith("maple")
        nominal = 33000 if stock_is_maple else 37000
        variable = f"independent.{name}.z"
        sidecar["variables"][variable] = {"nominal": nominal, "min": nominal - 1, "max": nominal + 1}
        root["z"] = variable
    result = validate_uncertainty(p, sidecar)
    assert not result["dimensionally_valid"]
    assert any(item["code"] == "uncertain_glue_mismatch" for item in result["failed"])


def test_digest_and_missing_bounds_block_without_changing_nominal_plan():
    p = plan(); sidecar = declaration(); sidecar["plan_digest"] = "not-the-plan"
    del sidecar["operations"]["final-y-trim"]
    result = validate_uncertainty(p, sidecar)
    assert not result["dimensionally_valid"]
    assert {item["code"] for item in result["failed"]} >= {"digest_mismatch", "missing_declaration"}
    assert plan_digest(p) != "not-the-plan"


def test_nominally_valid_plan_can_fail_conservative_material_guard():
    p = plan(); sidecar = declaration()
    operation = "final-z-min"
    target = "target.final-z-min"; guard = "guard.final-z-min"
    sidecar["variables"][target] = {"nominal": 31000, "min": 31000, "max": 31000}
    # Nominal source is 32 mm: target plus a 2 mm guard exceeds it.
    sidecar["variables"][guard] = {"nominal": 2000, "min": 2000, "max": 2000}
    sidecar["operations"][operation] = {"mode": "machine_to_target", "variable": target, "guard": guard}
    result = validate_uncertainty(p, sidecar)
    assert not result["dimensionally_valid"]
    assert any(item["code"] == "insufficient_material_guard" for item in result["failed"])


def test_machine_to_target_accepts_sufficient_material_for_every_endpoint():
    p = plan(); sidecar = declaration()
    operation = "final-z-min"
    target = "target.final-z-min"; guard = "guard.final-z-min"
    # Input is fixed 32 mm. The target/guard endpoint sum is at most 32 mm.
    sidecar["variables"][target] = {"nominal": 31000, "min": 30000, "max": 31000}
    sidecar["variables"][guard] = {"nominal": 1000, "min": 500, "max": 1000}
    sidecar["operations"][operation] = {"mode": "machine_to_target", "variable": target, "guard": guard}
    # The subsequent 1 mm finish removal remains remove-by; declare the
    # resulting supported final tolerance explicitly.
    sidecar["final_tolerance"]["z"] = [29000, 30000]
    result = validate_uncertainty(p, sidecar)
    assert result["dimensionally_valid"]
    assert result["final_intervals_um"]["z"] == ["29000", "30000"]


def test_nominal_pass_but_nonzero_cut_kerf_exhausts_final_reserve():
    p = plan(); sidecar = declaration()
    variable = "kerf.final-y-trim.nonzero"
    sidecar["variables"][variable] = {"nominal": 3000, "min": 3000, "max": 10000}
    sidecar["operations"]["final-y-trim"]["kerf"] = variable
    # Machine-to-target retained length is independent of kerf, but the other
    # child must remain positive. Its nominal 7 mm offcut becomes zero at 10 mm.
    result = validate_uncertainty(p, sidecar)
    assert not result["dimensionally_valid"]
    assert any(item["code"] == "nonpositive_dimension" for item in result["failed"])


def test_malformed_nested_sidecars_always_return_structured_invalid_report():
    p = plan()
    malformed = [
        None,
        [],
        {"version": "cbdesign-uncertainty/v1", "plan_digest": plan_digest(p), "variables": [], "roots": None, "operations": [], "final_tolerance": None},
        {"version": "cbdesign-uncertainty/v1", "plan_digest": plan_digest(p), "variables": {"bad": None}, "roots": {p.source_segments[0].id: []}, "operations": {p.operations[0].id: []}, "final_tolerance": {"x": None, "y": {}, "z": [1]}},
    ]
    for sidecar in malformed:
        result = validate_uncertainty(p, sidecar)
        assert result["status"] in {"invalid", "unsupported"}
        assert result["dimensionally_valid"] is False
        assert isinstance(result["failed"], list)


def test_uncertainty_never_labels_a_nominal_replay_failure_valid():
    p = plan()
    invalid = p.model_copy(update={"expected_final_size": [1, 1, 1]})
    result = validate_uncertainty(invalid, illustrative_uncertainty(p))
    assert result["dimensionally_valid"] is False
    assert result["nominal_valid"] is False
    assert result["failed"][0]["code"] == "nominal_replay_invalid"


def test_machine_target_requires_nominal_target_and_positive_guard():
    p = plan(); sidecar = declaration()
    operation = "final-z-min"
    sidecar["variables"]["target.bad"] = {"nominal": 30000, "min": 30000, "max": 30000}
    sidecar["variables"]["guard.bad"] = {"nominal": 1000, "min": -1, "max": 1000}
    sidecar["operations"][operation] = {"mode": "machine_to_target", "variable": "target.bad", "guard": "guard.bad"}
    result = validate_uncertainty(p, sidecar)
    codes = {item["code"] for item in result["failed"]}
    assert {"nominal_binding", "nonpositive_material_guard"} <= codes


def test_slicing_limits_are_topological_not_operation_name_dependent():
    p = plan(); sidecar = declaration()
    # Renaming must not turn a panel-descendant Y cut into preparation.
    operation = next(op for op in p.operations if op.id == "R1-slice-cut-4")
    renamed = p.model_copy(update={"operations": [op.model_copy(update={"id": "ordinary-y-cut"}) if op.id == operation.id else op for op in p.operations]})
    # Sidecar binds the original digest/ID on purpose: rebuild its complete binding
    # then widen the renamed slice target beyond its declared 32 mm bound.
    changed = illustrative_uncertainty(renamed)
    target = "target.ordinary-y-cut.wide"
    changed["variables"][target] = {"nominal": 32000, "min": 32000, "max": 33000}
    changed["operations"]["ordinary-y-cut"]["retained"]["variable"] = target
    result = validate_uncertainty(renamed, changed)
    assert any(item["code"] == "slice_bounds" for item in result["failed"])


def test_affine_endpoint_oracle_and_shared_correlation():
    expression = Affine.variable("x").scale(2) - Affine.variable("y") + Affine.number(7)
    bounds = {"x": (Fraction(-2), Fraction(3)), "y": (Fraction(1), Fraction(5))}
    assert expression.interval(bounds) == (Fraction(-2), Fraction(12))
    endpoints = [2 * x - y + 7 for x in (-2, 3) for y in (1, 5)]
    assert (min(endpoints), max(endpoints)) == expression.interval(bounds)
    shared = Affine.variable("x") - Affine.variable("x")
    assert shared.interval(bounds) == (0, 0)
