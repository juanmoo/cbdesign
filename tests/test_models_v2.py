import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cbdesign.models import Plan, load_plan
from cbdesign.models_v2 import PlanV2


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "examples" / "rough-stock-board.json"


def fixture_obj():
    return json.loads(FIXTURE.read_text())


def test_loads_reference_fixture_and_derives_replay_stock():
    plan = load_plan(fixture_obj())
    assert isinstance(plan, PlanV2)
    assert [(root.id, root.species, list(root.size)) for root in plan.stock[:2]] == [
        ("maple-1", "maple", [108000, 419000, 33000]),
        ("maple-2", "maple", [108000, 419000, 33000]),
    ]
    assert len(plan.stock) == 10
    assert plan.shop.saw_kerf is None
    assert plan.shop.max_slice_length is None


def test_load_plan_keeps_v1_dispatch():
    plan = load_plan(json.loads((ROOT / "examples" / "checkerboard.json").read_text()))
    assert isinstance(plan, Plan)


def test_v2_requires_unique_types_and_source_references():
    obj = fixture_obj()
    obj["stock_types"][1]["id"] = "maple"
    with pytest.raises(ValidationError, match="stock type IDs must be unique"):
        PlanV2.model_validate(obj)

    obj = fixture_obj()
    obj["source_segments"][0]["stock_type"] = "not-a-type"
    with pytest.raises(ValidationError, match="unknown stock type"):
        PlanV2.model_validate(obj)


def test_v2_rejects_nonrepresentable_geometry_and_bad_source_cut():
    obj = fixture_obj()
    obj["grid"]["pitch"] = 500
    with pytest.raises(ValidationError, match="not representable"):
        PlanV2.model_validate(obj)

    obj = fixture_obj()
    cut = next(op for op in obj["operations"] if op["id"] == "maple-1-separate")
    cut["axis"] = 0
    with pytest.raises(ValidationError, match="along Y"):
        PlanV2.model_validate(obj)

    obj = fixture_obj()
    cut = next(op for op in obj["operations"] if op["id"] == "maple-1-separate")
    cut["retained"] = obj["source_segments"][0]["length"] - cut["kerf"]
    with pytest.raises(ValidationError, match="positive terminal reserve"):
        PlanV2.model_validate(obj)


def test_v2_required_and_strict_shape_negatives():
    obj = fixture_obj()
    del obj["shop"]["cutting"]["slicing"]
    with pytest.raises(ValidationError, match="slicing"):
        PlanV2.model_validate(obj)

    obj = fixture_obj()
    obj["source_segments"][0]["width"] = 108000
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PlanV2.model_validate(obj)

    obj = fixture_obj()
    obj["stock_types"][0]["width"] = True
    with pytest.raises(ValidationError, match="integer"):
        PlanV2.model_validate(obj)

    obj = fixture_obj()
    obj["stock_types"][0]["width"] = 108000.0
    with pytest.raises(ValidationError, match="integer"):
        PlanV2.model_validate(obj)

    obj = fixture_obj()
    del next(op for op in obj["operations"] if op["kind"] == "cut")["retained_side"]
    with pytest.raises(ValidationError, match="retained_side"):
        PlanV2.model_validate(obj)


def test_v2_rejects_duplicate_cut_outputs_and_bad_recipe_cells():
    obj = fixture_obj()
    cut = next(op for op in obj["operations"] if op["kind"] == "cut")
    cut["outputs"][1] = cut["outputs"][0]
    with pytest.raises(ValidationError, match="repeats an output"):
        PlanV2.model_validate(obj)

    obj = fixture_obj()
    obj["template"]["recipes"][0]["cells"].pop()
    with pytest.raises(ValidationError, match="cell count"):
        PlanV2.model_validate(obj)

    obj = fixture_obj()
    obj["template"]["recipes"][1]["cells"][0] = "cherry"
    with pytest.raises(ValidationError, match="unknown species"):
        PlanV2.model_validate(obj)


def test_v2_schema_file_is_valid_and_names_required_contract_fields():
    schema = json.loads((ROOT / "docs" / "plan-v2.schema.json").read_text())
    props = schema["properties"]
    assert {"stock_types", "source_segments", "shop", "grid", "template"} <= set(props)
    shop = schema["$defs"]["ShopV2"]
    assert "max_workpiece" in shop["required"]
