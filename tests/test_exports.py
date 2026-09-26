import csv
import io
import json
import zipfile
from pathlib import Path

import pytest

from cbdesign.bundle import plan_bundle, zip_bundle
from cbdesign.exports import material_csv, operations_csv
from cbdesign.models import load_plan
from cbdesign.validation import validate

ROOT = Path(__file__).parents[1]


@pytest.fixture
def reference():
    plan = load_plan(json.loads((ROOT / 'examples/checkerboard.json').read_text()))
    report, replay = validate(plan)
    return plan, report, replay


def test_common_bundle_is_deterministic_and_replay_derived(reference):
    plan, report, replay = reference
    first = plan_bundle(plan, report, replay)
    assert first == plan_bundle(plan, report, replay)
    assert first['report.pdf'].startswith(b'%PDF-')
    assert b'id="replay-data"' in first['replay.html']
    assert b'fetch(' not in first['replay.html']
    assert json.loads(first['plan.json']) == plan.model_dump(mode='json')
    operations = list(csv.DictReader(io.StringIO(first['operations.csv'].decode())))
    assert len(operations) == len(replay.operations)
    assert json.loads(operations[0]['output_dimensions_um']) == replay.operations[0]['output_sizes_um']
    material = list(csv.DictReader(io.StringIO(first['material.csv'].decode())))
    assert all(int(row['balance_um3']) == 0 for row in material)
    assert sum(int(row['stock_um3']) for row in material) == sum(row['stock'] for row in replay.ledger()['species'].values())
    archive = zip_bundle(first)
    assert archive == zip_bundle(first)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert set(z.namelist()) == set(first)
        assert z.read('report.pdf') == first['report.pdf']


def test_formula_identifiers_are_escaped(reference):
    _, _, replay = reference
    replay.operations[0]['id'] = '=HYPERLINK("https://example.test")'
    row = next(csv.DictReader(io.StringIO(operations_csv(replay))))
    assert row['operation'].startswith("'=")


def test_invalid_report_is_not_exported(reference):
    plan, _, replay = reference
    with pytest.raises(ValueError):
        plan_bundle(plan, {'status': 'invalid'}, replay)
