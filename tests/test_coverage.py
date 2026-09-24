import json
from pathlib import Path

from cbdesign.models import Plan
from cbdesign.validation import validate


def test_missing_shop_constraints_are_not_reported_as_passed():
    path = Path(__file__).parents[1] / "examples/checkerboard.json"
    raw = json.loads(path.read_text())
    raw["shop"] = {"manufacturing_increment": 1000}
    report, _ = validate(Plan.from_json_obj(raw))
    assert report["status"] == "nominal_valid"
    coverage = report["coverage"]
    for check in ("declared_saw_kerf", "declared_workpiece_capacity", "declared_slice_length_limit"):
        assert check not in coverage["passed"]
        assert check in coverage["not_evaluated"]
    assert "minimum_handling_dimensions" in coverage["not_evaluated"]
    assert "terminal_slicing_reserve" in coverage["not_evaluated"]


def test_supplied_shop_constraints_are_reported_as_checked():
    path = Path(__file__).parents[1] / "examples/checkerboard.json"
    report, _ = validate(Plan.from_json_obj(json.loads(path.read_text())))
    assert report["status"] == "nominal_valid"
    for check in ("declared_saw_kerf", "declared_workpiece_capacity", "declared_slice_length_limit"):
        assert check in report["coverage"]["passed"]
        assert check not in report["coverage"]["not_evaluated"]
