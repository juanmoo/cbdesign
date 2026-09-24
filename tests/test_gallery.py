import json
import runpy
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "regenerate_gallery.py"


def gallery_module():
    return runpy.run_path(str(SCRIPT), run_name="gallery_regenerate_test")


def test_gallery_fixture_factories_are_deterministic_and_cover_requested_patterns(tmp_path):
    module = gallery_module()
    module["write_fixtures"].__globals__["DESIGNS"] = tmp_path / "designs"
    module["write_fixtures"]()
    names = ("checkerboard", "stripes", "diamond", "basket_weave", "letter", "asymmetric", "unrelated", "mouse_head")
    for name in names:
        target = json.loads((tmp_path / "designs" / f"{name}.target.json").read_text())
        request = json.loads((tmp_path / "designs" / f"{name}.request.json").read_text())
        assert request["schema_version"] == "cbdesign-design/v1"
        assert len(request["matrix"]) == 12
        assert len(request["matrix"][0]) == 12
        assert all(len(stock["available_lengths"]) == 192 for stock in request["stock_types"])
    mouse = json.loads((tmp_path / "designs" / "mouse_head.target.json").read_text())
    assert (len(mouse["rows"]), len(mouse["rows"][0])) == (64, 64)
    mouse_request = json.loads((tmp_path / "designs" / "mouse_head.request.json").read_text())
    assert (len(mouse_request["matrix"]), len(mouse_request["matrix"][0])) == (12, 12)


def test_regeneration_loads_frozen_target_snapshot_not_pattern_factory(tmp_path):
    module = gallery_module()
    fixture = tmp_path / "designs"; fixture.mkdir()
    (fixture / "checkerboard.request.json").write_text(json.dumps(module["_request"](module["_target"]("checkerboard"), "checkerboard")))
    frozen = {"rows": [[1]], "metadata": {"frozen": True}}
    (fixture / "checkerboard.target.json").write_text(json.dumps(frozen))
    module["_fixture_target"].__globals__["DESIGNS"] = fixture
    target = module["_fixture_target"]("checkerboard")
    assert target.rows == ((1,),)
    assert target.as_dict()["metadata"]["frozen"] is True


def test_gallery_svg_overlay_uses_target_pixels_and_replay_rectangles():
    module = gallery_module()
    target = module["_target"]("checkerboard")
    svg = module["_pixel_svg"](target, "test target")
    assert "test target" in svg and "#242424" in svg and "viewBox" in svg
