import json
from pathlib import Path
import pytest
from cbdesign.cli import main

ROOT=Path(__file__).parents[1]

def test_cli_success_outputs_reports_and_svg(tmp_path):
    out=tmp_path/'output'
    assert main(['validate',str(ROOT/'examples/checkerboard.json'),'--output',str(out)])==0
    assert json.loads((out/'validation.json').read_text())['status']=='nominal_valid'
    assert 'xmlns="http://www.w3.org/2000/svg"' in (out/'board.svg').read_text()
    assert (out/'material-ledger.json').exists() and (out/'operations.txt').exists()
    assert main(['validate',str(ROOT/'examples/checkerboard.json'),'--output',str(out)])==2

def test_cli_failure_does_not_create_stale_output(tmp_path):
    raw=json.loads((ROOT/'examples/checkerboard.json').read_text()); raw['expected_final_size']=[1,1,1]
    p=tmp_path/'bad.json'; p.write_text(json.dumps(raw)); out=tmp_path/'out'
    assert main(['validate',str(p),'--output',str(out)])==1
    assert not out.exists()
    out.mkdir(); (out/'validation.json').write_text('old success')
    assert main(['validate',str(p),'--output',str(out),'--overwrite'])==1
    assert (out/'validation.json').read_text()=='old success'

def test_cli_overwrite_preserves_unrelated_files_and_replaces_only_reports(tmp_path):
    out=tmp_path/'reports'; out.mkdir()
    keep=out/'keep.txt'; keep.write_text('preserve me')
    old=out/'validation.json'; old.write_text('old report')
    assert main(['validate',str(ROOT/'examples/checkerboard.json'),'--output',str(out),'--overwrite'])==0
    assert keep.read_text()=='preserve me'
    assert json.loads(old.read_text())['status']=='nominal_valid'
    assert 'inputs=' in (out/'operations.txt').read_text()
    assert 'retained_um=' in (out/'operations.txt').read_text()

def test_cli_rejects_symlink_collisions_and_input_overlap(tmp_path):
    out=tmp_path/'reports'; out.mkdir()
    (out/'board.svg').symlink_to(ROOT/'README.md')
    assert main(['validate',str(ROOT/'examples/checkerboard.json'),'--output',str(out),'--overwrite'])==2
    assert (out/'board.svg').is_symlink()
    plan=tmp_path/'plan.json'; plan.write_text((ROOT/'examples/checkerboard.json').read_text())
    assert main(['validate',str(plan),'--output',str(tmp_path),'--overwrite'])==2

@pytest.mark.parametrize('name', ['stock.svg', 'board.svg', 'validation.json', 'replay.html'])
@pytest.mark.parametrize('collision', ['directory', 'symlink', 'dangling_symlink'])
def test_all_generated_collisions_are_rejected_without_modifying_outputs(tmp_path, name, collision):
    out = tmp_path / 'reports'; out.mkdir()
    keep = out / 'operations.txt'; keep.write_text('existing report')
    target = out / name
    if collision == 'directory':
        target.mkdir()
    elif collision == 'symlink':
        target.symlink_to(ROOT / 'README.md')
    else:
        target.symlink_to(tmp_path / 'missing-target')
    assert main(['validate', str(ROOT / 'examples/checkerboard.json'), '--output', str(out), '--overwrite']) == 2
    assert keep.read_text() == 'existing report'
    assert not (tmp_path / 'missing-target').exists()


def test_cli_v2_schema_dispatch_and_stock_output(tmp_path):
    out = tmp_path / 'v2'
    assert main(['validate', str(ROOT / 'examples/rough-stock-board.json'), '--output', str(out)]) == 0
    report = json.loads((out / 'validation.json').read_text())
    assert report['final']['size_um'] == [290000, 290000, 30000]
    assert 'rough_stock_preparation_allowances' in report['coverage']['passed']
    assert '<svg' in (out / 'stock.svg').read_text()


def test_cli_malformed_file(tmp_path):
    p=tmp_path/'bad.json'; p.write_text('{invalid')
    assert main(['validate',str(p),'--output',str(tmp_path/'out')])==2
