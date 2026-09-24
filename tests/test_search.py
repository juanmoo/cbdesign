from fractions import Fraction

import pytest

from cbdesign.design import DesignRequest
from cbdesign.search import SearchSettings, _score, search_design
from cbdesign.target import FrozenTarget


def _request():
    # A compact two-row request whose generous illustrative stock accepts the
    # small grids used by the score oracle.
    return DesignRequest(matrix=[list("AB"), list("BA")], species={"A": "maple", "B": "walnut"},
        final={"x": 202000, "y": 202000, "z": 30000}, stock_types=[
            {"id": "maple", "species": "maple", "width": 300000, "thickness": 114000, "available_lengths": [800000] * 16},
            {"id": "walnut", "species": "walnut", "width": 300000, "thickness": 114000, "available_lengths": [800000] * 16},
        ])


def test_exact_score_oracle_for_two_by_two_target():
    target = FrozenTarget(((1, 0), (0, 1)))
    from cbdesign.target import target_occupancy
    occupancy = target_occupancy(target, 2, 2)
    assert _score(((1, 0), (0, 1)), occupancy, Fraction(1, 4)) == Fraction(0)
    assert _score(((0, 0), (0, 0)), occupancy, Fraction(1, 4)) == Fraction(1, 2)
    assert _score(((1, 1), (1, 1)), occupancy, Fraction(1, 4)) == Fraction(1, 2)


def test_search_is_deterministic_and_all_incumbents_replay():
    settings = SearchSettings(grid_dimensions=((2, 2), (4, 4)), recipe_budget=4, work_budget=16, seed=99)
    target = FrozenTarget(((1, 0, 1), (0, 1, 0), (1, 0, 1)))
    first = search_design(_request(), target, settings)
    second = search_design(_request(), target, settings)
    assert [(item.label, item.score, item.recipes) for item in first.candidates] == [(item.label, item.score, item.recipes) for item in second.candidates]
    assert all(item.plan is not None and item.compile_result.replay is not None for item in first.candidates)
    assert all(item.metrics["saw_cuts"] > 0 and item.metrics["joint_count"] > 0 for item in first.candidates)


def test_default_grid_preserves_request_shape():
    result = search_design(_request(), FrozenTarget(((1, 0), (0, 1))), SearchSettings(recipe_budget=1, work_budget=4))
    assert result.attempted == 1
    assert all(candidate.grid == (2, 2) for candidate in result.candidates)


def test_budget_candidates_are_deduplicated_and_have_actual_metrics():
    result = search_design(
        _request(), FrozenTarget(((1, 0), (0, 1))),
        SearchSettings(grid_dimensions=((2, 2),), recipe_budget=4, work_budget=8),
    )
    matrices = [tuple(tuple(row) for row in candidate.request.matrix) for candidate in result.candidates]
    assert len(matrices) == len(set(matrices))
    assert result.candidates
    metrics = result.candidates[0].metrics
    # Compiler batching may reduce first-stage panels, but replay remains the
    # authority for both panel/glue-up and stage-specific joint metrics.
    assert metrics["panels"] >= 1 and metrics["glueups"] >= 2
    assert metrics["joints_by_stage"]["final"] == 1
    assert metrics["joints_by_stage"]["first"] >= 1
    assert metrics["saw_settings"] and metrics["loss_volume_by_category_um3"]
    assert len(metrics["max_workpiece_margin_um"]) == 3


def test_cancel_returns_no_incumbent_before_work():
    result = search_design(_request(), settings=SearchSettings(work_budget=4), cancel=lambda: True)
    assert result.termination == "cancelled"
    assert result.attempted == result.compiled == result.rejected == 0
    assert result.candidates == ()


@pytest.mark.parametrize("settings", [
    SearchSettings(recipe_budget=8, max_recipes=8),
    SearchSettings(grid_dimensions=((32, 32),), recipe_budget=1),
])
def test_settings_accept_documented_limits(settings):
    assert settings.recipe_budget <= 8


def test_settings_rejects_unbounded_contract_values():
    with pytest.raises(ValueError):
        SearchSettings(recipe_budget=9)
    with pytest.raises(ValueError):
        SearchSettings(grid_dimensions=((33, 2),))
