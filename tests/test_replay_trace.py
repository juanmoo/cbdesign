import json
from pathlib import Path
import pytest
from cbdesign.models import Plan
from cbdesign.replay import replay
from cbdesign.replay_trace import TraceLimitError

ROOT = Path(__file__).parents[1]
def plan(name='asymmetric-board.json'):
    return Plan.from_json_obj(json.loads((ROOT / 'examples' / name).read_text()))

def test_trace_is_opt_in_immutable_and_replay_equivalent():
    source = plan(); plain = replay(source); traced = replay(source, trace=True)
    assert not hasattr(plain, 'trace')
    assert plain.ledger() == traced.ledger()
    assert plain.parts[plain.terminal] == traced.parts[traced.terminal]
    step = traced.trace.steps[0]
    with pytest.raises((AttributeError, TypeError)):
        traced.trace.producers['x'] = 4
    assert step.inputs[0].id == step.input_ids[0]

def test_trace_captures_every_kind_and_exact_boxes():
    traced = replay(plan(), trace=True); steps = {s.kind: s for s in traced.trace.steps}
    assert set(steps) == {'cut', 'surface', 'rotate', 'glue'}
    cut = steps['cut']; retained, kerf, remainder = cut.cut_boxes
    assert retained.size[cut.axis] + kerf.size[cut.axis] + remainder.size[cut.axis] == cut.inputs[0].size[cut.axis]
    assert kerf.size[cut.axis] > 0
    surface = steps['surface']; kept, removed = surface.surface_boxes
    assert kept.size[surface.axis] + removed.size[surface.axis] == surface.inputs[0].size[surface.axis]
    assert steps['rotate'].rotation_perm and steps['rotate'].rotation_sign
    assert steps['glue'].glue_offsets[0] == 0

def test_v2_stripes_have_exact_cut_origins_and_continuity():
    from cbdesign.models import load_plan
    source = load_plan(json.loads((ROOT / 'examples/gallery/stripes/selected-plan.json').read_text()))
    plain = replay(source); traced = replay(source, trace=True)
    assert traced.ledger() == plain.ledger()
    assert traced.operations == plain.operations
    assert len(traced.trace.roots) == 24
    assert len(traced.trace.steps) == 251
    assert sum(s.kind == 'cut' for s in traced.trace.steps) == 110
    registry = {p.id: p for p in traced.trace.roots}
    for step in traced.trace.steps:
        assert all(registry[p.id] is p for p in step.inputs)
        registry.update({p.id: p for p in step.outputs})
        assert sum(p.volume for p in step.inputs) == sum(p.volume for p in step.outputs) + (step.cut_boxes[1].volume if step.cut_boxes else 0)
        if step.cut_boxes and step.retained_side == 'max':
            kept, kerf, other = step.cut_boxes
            assert kept.origin[step.axis] == other.size[step.axis] + kerf.size[step.axis]
            assert other.origin == (0, 0, 0)


def test_region_limit_remains_trace_error(monkeypatch):
    monkeypatch.setattr('cbdesign.replay_trace.MAX_TRACE_REGIONS', 15)
    with pytest.raises(TraceLimitError):
        replay(plan(), trace=True)


def test_trace_limit_is_explicit(monkeypatch):
    monkeypatch.setattr('cbdesign.replay_trace.MAX_TRACE_OPERATIONS', 1)
    with pytest.raises(TraceLimitError): replay(plan(), trace=True)
