import json
from pathlib import Path
from cbdesign.models import Plan
from cbdesign.render_replay import build_walkthrough, walkthrough_manifest, walkthrough_step, REPLAY_CSS

ROOT = Path(__file__).parents[1]
def _plan(): return Plan.from_json_obj(json.loads((ROOT / 'examples' / 'asymmetric-board.json').read_text()))

def test_manifest_and_step_html_cover_operations_and_planes():
    p = _plan(); result = build_walkthrough(p); manifest = walkthrough_manifest(p, result)
    assert manifest['operation_count'] == len(p.operations)
    assert len(manifest['steps']) == len(p.operations) + 2
    assert manifest['total_saw_cuts'] == sum(op.kind == 'cut' for op in p.operations)
    assert 'replay-step' in REPLAY_CSS
    kinds = set()
    for index in range(len(manifest['steps'])):
        step = walkthrough_step(p, result, index); kinds.add(step['kind'])
        assert all(f'{plane}:' in step['html'] for plane in ('XY', 'XZ', 'YZ'))
        assert 'viewBox="0 0 230 165"' in step['html']
        assert 'mm mm' not in step['html']
    assert {'stock', 'final', 'cut', 'surface', 'rotate', 'glue'} <= kinds

def test_exposed_faces_do_not_paint_hidden_regions():
    from cbdesign.geometry import Box
    from cbdesign.replay import Part, Region
    from cbdesign.render_replay import _part_svg
    a = Box((0, 0, 0), (10, 10, 5)); b = Box((0, 0, 5), (10, 10, 5))
    part = Part('layered', (10, 10, 10), (Region('a', 'maple', a, a, (0, 1, 0)), Region('b', 'walnut', b, b, (0, 1, 0))))
    html = _part_svg(part, (1, 1, 1), {'maple': '#aaa', 'walnut': '#bbb'})
    xy = html.split('</svg>')[0]
    assert 'fill="#aaa"' in xy
    assert 'fill="#bbb"' not in xy
    assert 'fill="#bbb"' in html


def test_stock_type_overview_and_cumulative_saw_count():
    from cbdesign.models import load_plan
    p = load_plan(json.loads((ROOT / 'examples/gallery/stripes/selected-plan.json').read_text()))
    result = build_walkthrough(p)
    stock = walkthrough_step(p, result, 0)
    assert '2 fixed-cross-section stock types; 24 allocated source segments' in stock['html']
    assert stock['saw_cuts_so_far'] == 0
    assert walkthrough_step(p, result, 1)['saw_cuts_so_far'] == 1
    assert walkthrough_step(p, result, 252)['saw_cuts_so_far'] == 110


def test_operation_html_has_actual_loss_rotation_glue_and_links():
    p = _plan(); result = build_walkthrough(p)
    content = [walkthrough_step(p, result, i)['html'] for i in range(1, len(p.operations)+1)]
    assert any('kerf' in x and 'Retained child' in x for x in content)
    assert any('Removed material' in x for x in content)
    assert any('Net signed-axis rotation' in x and '←' in x for x in content)
    assert any('in the assembled output' in x for x in content)
    assert any('data-step=' in x for x in content)
