"""Independent N1 fixture goldens, not derived from the fixture's commands."""
import json
from pathlib import Path

import pytest

from cbdesign.geometry import Box
from cbdesign.models import load_plan
from cbdesign.validation import validate

ROOT = Path(__file__).parents[1]


def fixture():
    return json.loads((ROOT / 'examples/rough-stock-board.json').read_text())


def test_rough_stock_independent_volume_and_joint_goldens():
    report, result = validate(load_plan(fixture()))
    assert report['status'] == 'nominal_valid', report
    assert result.parts[result.terminal].size == (290000, 290000, 30000)
    expected = {
        'maple': dict(stock=8959896, finished=1698000, kerf=548856,
                      milling=1889400, trim=285240, other_offcuts=4538400, balance=0),
        'walnut': dict(stock=5146996, finished=825000, kerf=320256,
                       milling=1398000, trim=175340, other_offcuts=2428400, balance=0),
    }
    assert result.ledger()['species'] == {
        species: {category: volume * 10**9 for category, volume in categories.items()}
        for species, categories in expected.items()
    }
    # Ten source separations, twenty end trims, ten rips, twelve slices, two final trims.
    assert sum(op['kind'] == 'cut' for op in result.operations) == 10 + 20 + 10 + 12 + 2
    assert sum(joint['stage'] == 'first' for joint in result.joints) == 17
    assert sum(joint['stage'] == 'final' for joint in result.joints) == 11
    assert len(result.first_glue_panels) == 3


def test_trimmed_surface_matches_independent_cell_area_golden():
    report, result = validate(load_plan(fixture()))
    assert report['status'] == 'nominal_valid', report
    # Physical A50/A50 joins split a four-cell A run; they are not cell boundaries.
    r = 'AAAABBAAAABB'
    s = 'BBAAAABBAAAA'
    rows = [r, r[::-1], s, r, s[::-1], r[::-1], r, s, r[::-1], r, s[::-1], r[::-1]]
    board = result.parts[result.terminal]
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            box = Box((x * 25000, y * 25000, 0),
                      (min(25000, 290000 - x * 25000),
                       min(25000, 290000 - y * 25000), 30000))
            pieces = [(region.species, region.current.intersect(box)) for region in board.regions]
            expected_species = 'maple' if cell == 'A' else 'walnut'
            assert sum(hit.volume for species, hit in pieces if hit and species == expected_species) == box.volume
            assert not any(hit and species != expected_species for species, hit in pieces)


def test_v2_coverage_does_not_claim_physical_or_interval_validation():
    report, _ = validate(load_plan(fixture()))
    coverage = report['coverage']
    assert report['status'] == 'nominal_valid', report
    for check in ('rough_stock_preparation_allowances', 'minimum_handling_dimensions',
                  'terminal_slicing_reserve', 'visual_recipe_cells', 'source_separation'):
        assert check in coverage['passed']
        assert check not in coverage['not_evaluated']
    for check in ('physical_machine_safety', 'interval_uncertainty_propagation', 'joint_strength'):
        assert check in coverage['not_evaluated']
        assert check not in coverage['passed']


def test_v2_replay_and_reports_are_deterministic():
    plan = load_plan(fixture())
    left_report, left = validate(plan)
    right_report, right = validate(plan)
    assert left_report['status'] == 'nominal_valid', left_report
    assert left_report == right_report
    assert left.ledger() == right.ledger()


@pytest.mark.parametrize('index', [0, 1])
def test_v2_cut_children_cannot_alias(index):
    raw = fixture()
    cut = next(op for op in raw['operations'] if op['kind'] == 'cut')
    cut['outputs'][1 - index] = cut['outputs'][index]
    # Depending on cross-reference validation this may fail at schema or replay.
    try:
        plan = load_plan(raw)
    except ValueError:
        return
    report, _ = validate(plan)
    assert report['status'] == 'invalid'
