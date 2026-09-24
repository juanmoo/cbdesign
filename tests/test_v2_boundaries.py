"""Boundary and fault-injection checks against the public v2 validation API."""
import json
from pathlib import Path

import pytest

from cbdesign.models import load_plan
from cbdesign.validation import validate

ROOT = Path(__file__).parents[1]


def fixture():
    return json.loads((ROOT / 'examples/rough-stock-board.json').read_text())


def status(raw):
    return validate(load_plan(raw))[0]


@pytest.mark.parametrize('reserve,valid', [(159000, True), (160000, True), (161000, False)])
def test_last_slice_reserve_boundary(reserve, valid):
    raw = fixture()
    raw['shop']['cutting']['slicing_reserve'] = reserve
    report = status(raw)
    assert (report['status'] == 'nominal_valid') == valid
    if not valid:
        assert report['coverage']['failed'][0]['code'] == 'slicing_reserve'


@pytest.mark.parametrize('minimum,valid', [(194000, True), (195000, True), (196000, False)])
def test_successive_slicing_input_not_only_first_panel(minimum, valid):
    raw = fixture()
    raw['shop']['cutting']['slicing']['min_input'][1] = minimum
    report = status(raw)
    assert (report['status'] == 'nominal_valid') == valid
    if not valid:
        assert report['coverage']['failed'][0]['code'] == 'min_input'


@pytest.mark.parametrize('maximum,valid', [(299000, False), (300000, True), (301000, True)])
def test_slicing_capacity_boundary(maximum, valid):
    raw = fixture()
    raw['shop']['cutting']['slicing']['max_input'][0] = maximum
    report = status(raw)
    assert (report['status'] == 'nominal_valid') == valid


@pytest.mark.parametrize('bound,value,valid', [
    ('slice_min', 31000, True), ('slice_min', 32000, True),
    ('slice_max', 32000, True), ('slice_max', 33000, True),
])
def test_slice_thickness_inclusive_bounds(bound, value, valid):
    raw = fixture()
    raw['shop']['cutting'][bound] = value
    assert (status(raw)['status'] == 'nominal_valid') == valid


@pytest.mark.parametrize('minimum,maximum', [(33000, 34000), (30000, 31000)])
def test_slice_outside_declared_range(minimum, maximum):
    raw = fixture()
    raw['shop']['cutting']['slice_min'] = minimum
    raw['shop']['cutting']['slice_max'] = maximum
    report = status(raw)
    assert report['status'] == 'invalid'
    assert report['coverage']['failed'][0]['code'] == 'slice_range'


@pytest.mark.parametrize('profile', ['separation', 'preparation', 'slicing', 'final_trim'])
def test_each_stage_enforces_its_own_kerf(profile):
    raw = fixture()
    raw['shop']['cutting'][profile]['kerf'] = 4000
    report = status(raw)
    assert report['status'] == 'invalid'
    assert report['coverage']['failed'][0]['code'] == 'kerf_profile_mismatch'


@pytest.mark.parametrize('change', ['side_rip', 'wrong_recipe', 'wrong_panel', 'row_order', 'unprepared', 'wrong_surface'])
def test_construction_faults_are_not_accepted_as_nominal(change):
    raw = fixture()
    if change == 'side_rip':
        next(op for op in raw['operations'] if op['kind'] == 'cut' and op['retained'] == 32000)['axis'] = 0
    elif change == 'wrong_recipe':
        raw['template']['recipes'][0]['cells'][0] = 'walnut'
    elif change == 'wrong_panel':
        raw['template']['rows'][0]['panel'] = raw['template']['panels'][-1]['id']
    elif change == 'row_order':
        raw['template']['rows'][0], raw['template']['rows'][1] = raw['template']['rows'][1], raw['template']['rows'][0]
    elif change == 'unprepared':
        next(op for op in raw['operations'] if op['kind'] == 'glue')['prepared_faces'] = False
    else:
        next(op for op in raw['operations'] if op['kind'] == 'surface' and op['process'] == 'jointer')['process'] = 'thickness_planer'
    report = status(raw)
    assert report['status'] == 'invalid', change


@pytest.mark.parametrize('face', ['x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max'])
def test_each_raw_face_allowance_is_independently_enforced(face):
    raw = fixture()
    raw['stock_types'][0]['preparation'][face] = 20000
    assert status(raw)['status'] == 'invalid'


@pytest.mark.parametrize('process', ['jointer', 'thickness_planer', 'drum_sander'])
def test_nonqualifying_surfacing_cannot_establish_preparation(process):
    raw = fixture()
    next(p for p in raw['shop']['surfacing'] if p['process'] == process)['glue_ready'] = False
    assert status(raw)['status'] == 'invalid'


def test_final_trim_can_retain_either_child_without_stock_rotation():
    raw = fixture()
    for operation in raw['operations'][-2:]:
        operation['retained_side'] = 'max'
    report, result = validate(load_plan(raw))
    assert report['status'] == 'nominal_valid', report
    assert result.parts[result.terminal].size == (290000, 290000, 30000)
    assert all(s['balance'] == 0 for s in result.ledger()['species'].values())


def test_end_grain_support_must_be_in_actual_process_profile():
    raw = fixture()
    next(p for p in raw['shop']['surfacing'] if p['process'] == 'drum_sander')['end_grain_supported'] = False
    report = status(raw)
    assert report['status'] == 'invalid'
    assert report['coverage']['failed'][0]['code'] == 'end_grain_process'
