import json
from pathlib import Path

from cbdesign.models import Plan
from cbdesign.render_svg import board_svg, panels_svg, stock_svg
from cbdesign.validation import validate

ROOT = Path(__file__).parents[1]


def _replay(name="checkerboard.json"):
    raw = json.loads((ROOT / "examples" / name).read_text())
    report, replay = validate(Plan.from_json_obj(raw))
    assert report["status"] == "nominal_valid"
    return replay


def test_board_and_panels_show_visible_mm_dimensions_and_grain_arrows():
    replay = _replay()
    board = board_svg(replay)
    panels = panels_svg(replay)
    assert "20 mm" in board
    assert "64 mm" in board
    assert 'grain normal to displayed face: +1Z' in board
    assert 'marker-end="url(#arrow)"' not in board
    assert 'marker-end="url(#arrow)"' in panels
    assert "20 mm" in panels
    # Both rectangles remain despite a future same-species adjacent panel boundary.
    assert panels.count('<rect class="outline"') >= 3


def test_svg_escapes_untrusted_part_species_and_source_names():
    replay = _replay()
    final = replay.parts[replay.terminal]
    region = final.regions[0]
    # Frozen dataclasses make this a direct proof that renderer text is escaped,
    # without changing the validation fixture's semantic identity.
    from dataclasses import replace

    escaped_region = replace(region, species='maple & <unsafe>')
    escaped_part = replace(final, id='final & <unsafe>', regions=(escaped_region, *final.regions[1:]))
    escaped_replay = replace(replay, parts={**replay.parts, replay.terminal: escaped_part})
    svg = board_svg(escaped_replay)
    assert "final &amp; &lt;unsafe&gt;" in svg
    assert "maple &amp; &lt;unsafe&gt;" in svg
    assert "<unsafe>" not in svg


def test_stock_svg_is_deterministic_and_exactly_categorises_source_partition():
    replay = _replay("asymmetric-board.json")
    first = stock_svg(replay)
    assert first == stock_svg(replay)
    for label in ("finished", "kerf", "milling", "trim", "other offcuts"):
        assert label in first
    for source in replay.source_sizes:
        assert f"Source {source}" in first
    # A source slab is rendered once per distinct provenance Z interval, allowing
    # regions that overlap in source X/Y to remain explicit rather than occluded.
    assert "Exploded Z slabs" in first
    assert 'aria-labelledby="svg-title svg-description"' in first
