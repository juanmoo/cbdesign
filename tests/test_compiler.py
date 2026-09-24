from cbdesign.design import illustrative_request
from cbdesign.compiler import compile_design
from cbdesign.allocation import split_pitch_run
from cbdesign.replay import replay


def test_compiler_generates_independently_replayable_plan():
    result = compile_design(illustrative_request())
    assert result.error is None
    independent = replay(result.plan)
    assert independent.parts[independent.terminal].size == (290000, 290000, 30000)


def test_compiler_is_deterministic_and_reverses_rows():
    request = illustrative_request()
    left, right = compile_design(request), compile_design(request)
    assert left.plan.model_dump() == right.plan.model_dump()
    assert left.report["status"] == "nominal_valid"
    assert any(row.reversed for row in left.plan.template.rows)


def test_asymmetric_rectangular_rows_survive_reversal_and_replay():
    request = illustrative_request([list("AAB"), list("ABA")]).model_copy(update={"final": {"x": 180000, "y": 40000, "z": 30000}, "shop": {"final_x_trim": 6000, "final_y_trim": 4000}})
    result = compile_design(request)
    assert result.error is None
    board = result.replay.parts[result.replay.terminal]
    assert board.size == (180000, 40000, 30000)


def test_repeat_row_families_batch_into_fewer_panels_and_sources():
    result = compile_design(illustrative_request())
    assert result.error is None
    # Twelve rows form two canonical reversal families; each six-row panel fits.
    assert result.metrics["panels"] == 2
    assert result.metrics["source_segments"] == 24
    assert len(result.plan.template.rows) == 12


def test_depleted_stock_across_distinct_families_is_structured_failure():
    request = illustrative_request([list("AAB"), list("ABA"), list("BAA"), list("ABB")]).model_copy(update={
        "final": {"x": 180000, "y": 80000, "z": 30000},
        "shop": {"final_x_trim": 6000, "final_y_trim": 4000},
        "stock_types": [
            {"id":"maple","species":"maple","width":108000,"thickness":43000,"available_lengths":[419000] * 3},
            {"id":"walnut","species":"walnut","width":83000,"thickness":43000,"available_lengths":[419000] * 3},
        ],
    })
    result = compile_design(request)
    assert result.error and result.error.code == "allocation_failed"


def test_single_column_panel_uses_no_first_stage_glue():
    request = illustrative_request([["A"], ["B"]]).model_copy(update={"final": {"x": 50000, "y": 50000, "z": 30000}, "shop": {"final_x_trim": 10000, "final_y_trim": 10000}, "stock_types": [{"id":"maple","species":"maple","width":300000,"thickness":43000,"available_lengths":[419000]*2},{"id":"walnut","species":"walnut","width":300000,"thickness":43000,"available_lengths":[419000]*2}]})
    result = compile_design(request)
    assert result.error is None
    assert not any(op.stage == "first" for op in result.plan.operations if op.kind == "glue")


def test_finite_inventory_is_not_recycled():
    request = illustrative_request().model_copy(update={"stock_types": [
        {"id":"maple","species":"maple","width":108000,"thickness":33000,"available_lengths":[419000]},
        {"id":"walnut","species":"walnut","width":83000,"thickness":37000,"available_lengths":[419000]}]})
    result = compile_design(request)
    assert result.error and result.error.code == "allocation_failed"


def test_bounded_impossible_stock_failure():
    request = illustrative_request().model_copy(update={"stock_types": [
        {"id":"maple","species":"maple","width":30000,"thickness":33000,"available_lengths":[100000]},
        {"id":"walnut","species":"walnut","width":30000,"thickness":37000,"available_lengths":[100000]}]})
    result = compile_design(request)
    assert result.error and result.error.code in {"stock_length", "stock_cross_section"}


def test_tiny_strip_splitting_oracle():
    assert split_pitch_run(53, 25, 2, 1) == [25, 25]
    assert split_pitch_run(49, 25, 2, 1) == [25]
    assert split_pitch_run(24, 25, 2, 1) is None
