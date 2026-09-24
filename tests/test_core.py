import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from cbdesign.geometry import Box, Rotation, PROPER_ROTATIONS
from cbdesign.models import Plan
from cbdesign.validation import validate
from cbdesign.render_svg import board_svg, panels_svg, species_colors
from hypothesis import given, strategies as st

ROOT=Path(__file__).parents[1]

def plan(name): return Plan.from_json_obj(json.loads((ROOT/'examples'/name).read_text()))

def test_all_24_proper_rotations_and_inverse():
    assert len(PROPER_ROTATIONS)==24
    v=(2,3,5)
    for r in PROPER_ROTATIONS:
        assert r.determinant==1
        assert r.inverse().apply_vector(r.apply_vector(v))==v

def test_half_open_intersection_and_cut_volume():
    a=Box((0,0,0),(10,10,10)); b=Box((10,0,0),(1,1,1))
    assert a.intersect(b) is None
    one, kerf, two=a.cut(0,4,1)
    assert one.volume+kerf.volume+two.volume==a.volume

def test_reflection_rejected():
    with pytest.raises(ValueError): Rotation((0,1,2),(-1,1,1))

@given(st.integers(2, 1000), st.integers(1, 998), st.integers(1, 999))
def test_cut_partitions_box_volume_property(length, retained, kerf):
    from hypothesis import assume
    assume(retained + kerf < length)
    box = Box((0, 0, 0), (length, 7, 11))
    left, waste, right = box.cut(0, retained, kerf)
    assert left.volume + waste.volume + right.volume == box.volume
    assert left.intersect(waste) is None and left.intersect(right) is None and waste.intersect(right) is None

@given(st.sampled_from(PROPER_ROTATIONS), st.tuples(st.integers(-99, 99), st.integers(-99, 99), st.integers(-99, 99)))
def test_rotation_inverse_source_vector_property(rotation, vector):
    assert rotation.inverse().apply_vector(rotation.apply_vector(vector)) == vector

def test_checkerboard_golden_dimensions_volumes_and_joints():
    report, result=validate(plan('checkerboard.json'))
    assert report['status']=='nominal_valid'
    assert result.parts[result.terminal].size==(20000,64000,18000)
    assert report['final']['species_volumes']=={'maple':11520000000000,'walnut':11520000000000}
    assert len(result.joints)==2

def test_asymmetric_has_hidden_same_species_joint_and_reversed_row():
    report,result=validate(plan('asymmetric-board.json'))
    assert report['status']=='nominal_valid'
    assert result.parts[result.terminal].size==(15000,64000,18000)
    assert result.joints[0]['left']=='maple-wide' and result.joints[0]['right']=='maple-narrow'

def test_svg_renders_only_first_glue_outputs_with_stable_colours_and_labels():
    report, result = validate(plan('asymmetric-board.json'))
    assert report['status'] == 'nominal_valid'
    panels = panels_svg(result)
    board = board_svg(result)
    # The original panel is snapshot at its first glue output, rather than descendant
    # slices, rows, final board, or retained/lost inventory parts.
    assert 'asym-panel-glue' in result.first_glue_panels['asym-panel'].history
    assert 'asym-panel — 17000 × 60000 × 32000 µm' in panels
    assert 'asym-row-normal' not in panels
    assert 'asym-finished' not in panels
    assert 'asym-finished — 15000 × 64000 × 18000 µm' in board
    colours = species_colors(result)
    for species, colour in colours.items():
        if species in {'maple', 'walnut'}:
            assert f'{species}: {colour}' in panels
            assert f'{species}: {colour}' in board
    assert colours['maple'] == '#c9975b'
    assert colours['walnut'] == '#4a2d1b'

def test_strict_schema_rejects_float_and_bool_dimension():
    raw=json.loads((ROOT/'examples/checkerboard.json').read_text()); raw['stock'][0]['size'][0]=True
    with pytest.raises(ValidationError): Plan.from_json_obj(raw)
    raw=json.loads((ROOT/'examples/checkerboard.json').read_text()); raw['stock'][0]['size'][0]=1.5
    with pytest.raises(ValidationError): Plan.from_json_obj(raw)

def test_fault_injection_kerf_and_missing_disposition():
    raw=json.loads((ROOT/'examples/checkerboard.json').read_text()); raw['operations'][1]['kerf']=2000
    report,_=validate(Plan.from_json_obj(raw)); assert report['status']=='invalid'
    raw=json.loads((ROOT/'examples/checkerboard.json').read_text()); raw['dispositions']=[]
    report,_=validate(Plan.from_json_obj(raw)); assert report['coverage']['failed'][0]['code']=='terminal_disposition'

def test_fault_injection_long_grain_and_consumer_reuse():
    raw=json.loads((ROOT/'examples/checkerboard.json').read_text()); raw['operations'][3]['perm']=[0,1,2]; raw['operations'][3]['sign']=[1,1,1]
    report,_=validate(Plan.from_json_obj(raw)); assert report['status']=='invalid'
    raw=json.loads((ROOT/'examples/checkerboard.json').read_text()); raw['operations'][4]['input']='slice-one-raw'
    report,_=validate(Plan.from_json_obj(raw)); assert report['coverage']['failed'][0]['code']=='multiple_consumers'

def test_reference_fixtures_model_saw_kerfs_and_real_checker_reversal():
    checker = json.loads((ROOT/'examples/checkerboard.json').read_text())
    assert [operation['kind'] for operation in checker['operations'][:3]] == ['glue', 'cut', 'cut']
    assert checker['operations'][4]['sign'] == [-1, 1, 1]
    assert checker['template']['rows'][1]['reversed'] is True
    asymmetric = json.loads((ROOT/'examples/asymmetric-board.json').read_text())
    assert [operation['kind'] for operation in asymmetric['operations'][1:3]] == ['cut', 'cut']
    assert asymmetric['operations'][-1]['kind'] == 'cut'
    assert asymmetric['operations'][-1]['category'] == 'trim'

def test_terminal_dispositions_are_unique_and_operation_derived():
    raw=json.loads((ROOT/'examples/checkerboard.json').read_text())
    raw['dispositions'].append(dict(raw['dispositions'][0]))
    report, _ = validate(Plan.from_json_obj(raw))
    assert report['coverage']['failed'][0]['code'] == 'duplicate_disposition'
    raw=json.loads((ROOT/'examples/checkerboard.json').read_text())
    raw['dispositions'][0]['category'] = 'kerf'
    report, _ = validate(Plan.from_json_obj(raw))
    assert report['coverage']['failed'][0]['code'] == 'disposition_category_mismatch'

def test_row_assignments_bijectively_cover_final_glue_inputs():
    raw = json.loads((ROOT/'examples/checkerboard.json').read_text())
    raw['template']['rows'] = [
        {'rotated_part': 'row-one', 'recipe': 'ab'},
        {'rotated_part': 'row-one', 'recipe': 'ab'},
    ]
    report, _ = validate(Plan.from_json_obj(raw))
    assert report['coverage']['failed'][0]['code'] == 'row_assignment_mismatch'

def test_prepared_faces_and_actual_finishing_process_are_enforced():
    raw=json.loads((ROOT/'examples/checkerboard.json').read_text())
    raw['operations'][0]['prepared_faces'] = False
    report, _ = validate(Plan.from_json_obj(raw))
    assert report['coverage']['failed'][0]['code'] == 'unprepared_glue_faces'
    raw=json.loads((ROOT/'examples/checkerboard.json').read_text())
    raw['operations'][-1]['process'] = 'thickness_planer'
    report, _ = validate(Plan.from_json_obj(raw))
    assert report['coverage']['failed'][0]['code'] == 'finishing_process_mismatch'

def test_consuming_surface_removed_milling_material_is_rejected():
    raw = json.loads((ROOT/'examples/checkerboard.json').read_text())
    raw['operations'][-1]['removed'] = 'milling-pre-rotate'
    raw['dispositions'][1]['part'] = 'final-flattening'
    raw['operations'].append({'kind':'rotate','id':'illicit-milling-rotate','input':'milling-pre-rotate','output':'final-flattening','perm':[0,1,2],'sign':[-1,1,-1]})
    report, _ = validate(Plan.from_json_obj(raw))
    assert report['coverage']['failed'][0]['code'] == 'consumed_removal_output'

def test_generated_output_capacity_is_enforced():
    raw = json.loads((ROOT/'examples/checkerboard.json').read_text())
    # All source/panel inputs fit Y=60000, but final glue output is Y=64000.
    raw['shop']['max_workpiece'] = [100000,60000,100000]
    report, _ = validate(Plan.from_json_obj(raw))
    assert report['coverage']['failed'][0]['code'] == 'shop_capacity'

def test_final_trim_follows_retained_cut_output_not_removed_surface():
    raw = json.loads((ROOT/'examples/checkerboard.json').read_text())
    surface = raw['operations'].pop()
    raw['operations'].append(surface)
    raw['operations'].append({'kind':'cut','id':'final-edge-trim','input':'finished-board','outputs':['trimmed-board','trim-offcut'],'axis':0,'retained':18000,'kerf':1000,'tool':'saw','category':'trim'})
    raw['finishing']['terminal'] = 'trimmed-board'
    raw['dispositions'].append({'part':'trim-offcut','category':'trim','reusable':False})
    raw['expected_final_size'] = [18000,64000,18000]
    report, _ = validate(Plan.from_json_obj(raw))
    assert report['status'] == 'nominal_valid'
    # A removed surface slab cannot be designated as finished.
    raw['finishing']['terminal'] = 'final-flattening'
    raw['dispositions'] = [d for d in raw['dispositions'] if d['part'] != 'final-flattening']
    raw['dispositions'].append({'part':'trimmed-board','category':'other_offcuts','reusable':False})
    raw['expected_final_size'] = [20000,64000,2000]
    report, _ = validate(Plan.from_json_obj(raw))
    assert report['coverage']['failed'][0]['code'] == 'finishing_lineage'

def test_recut_or_spliced_rotated_row_fails_lineage_validation():
    raw=json.loads((ROOT/'examples/checkerboard.json').read_text())
    # Replace the second final-row input with a recut then re-glued rotated row.
    raw['operations'][4]['output'] = 'row-two-pre'
    raw['operations'][5]['inputs'] = ['row-one', 'row-two']
    raw['operations'][5]['output'] = 'rough-board'
    raw['operations'][5]['axis'] = 1
    raw['operations'][5]['stage'] = 'final'
    raw['operations'][5]['prepared_faces'] = True
    raw['operations'][5]['negligible_glue_line'] = True
    splice = [
        {'kind':'cut','id':'recut-rotated-row','input':'row-two-pre','outputs':['row-two-a','row-two-b'],'axis':1,'retained':10000,'kerf':1000},
        {'kind':'glue','id':'splice-rotated-row','inputs':['row-two-a','row-two-b'],'output':'row-two','axis':1,'stage':'first','prepared_faces':True,'negligible_glue_line':True},
    ]
    raw['operations'][5:5] = splice
    raw['expected_final_size'] = [20000, 63000, 18000]
    report, _ = validate(Plan.from_json_obj(raw))
    assert report['coverage']['failed'][0]['code'] in {'first_glue_orientation', 'first_glue_lineage', 'row_lineage'}
