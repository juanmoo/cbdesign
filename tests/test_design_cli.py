import json
import zipfile
from pathlib import Path

from cbdesign.cli import main
from cbdesign.design import illustrative_request
from cbdesign.uncertainty import illustrative_uncertainty
from cbdesign.models import load_plan

ROOT = Path(__file__).parents[1]


def test_generate_and_search_real_outputs(tmp_path):
    source = tmp_path / 'design.json'
    source.write_text(illustrative_request().model_dump_json())
    out = tmp_path / 'exact'
    assert main(['generate', str(source), '--output', str(out)]) == 0
    assert json.loads((out / 'validation.json').read_text())['status'] == 'nominal_valid'
    assert (out / 'report.pdf').read_bytes().startswith(b'%PDF-')
    alternatives = tmp_path / 'search'
    assert main(['search', str(source), '--output', str(alternatives), '--work-budget', '4']) == 0
    result = json.loads((alternatives / 'search.json').read_text())
    assert result['candidates']
    with zipfile.ZipFile(alternatives / result['candidates'][0]['file']) as archive:
        assert json.loads(archive.read('validation.json'))['status'] == 'nominal_valid'


def test_generate_preserves_inputs_and_rejects_new_report_symlinks(tmp_path):
    source = tmp_path / 'design.json'
    source.write_text(illustrative_request().model_dump_json())
    out = tmp_path / 'out'; out.mkdir()
    (out / 'report.pdf').symlink_to(tmp_path / 'absent')
    assert main(['generate', str(source), '--output', str(out), '--overwrite']) == 2
    assert not (tmp_path / 'absent').exists()
    assert (out / 'report.pdf').is_symlink()


def test_uncertainty_cli_reports_separately(tmp_path):
    source = ROOT / 'examples/rough-stock-board.json'
    plan = load_plan(json.loads(source.read_text()))
    sidecar = tmp_path / 'bounds.json'
    sidecar.write_text(json.dumps(illustrative_uncertainty(plan)))
    out = tmp_path / 'out'
    assert main(['validate', str(source), '--uncertainty', str(sidecar), '--output', str(out)]) == 0
    assert json.loads((out / 'validation.json').read_text())['status'] == 'nominal_valid'
    assert json.loads((out / 'uncertainty.json').read_text())['status'] == 'dimensionally_valid'


def test_demo_is_a_valid_request(capsys):
    from cbdesign.design import DesignRequest
    assert main(['demo', '--pattern', 'mouse_head']) == 0
    request = DesignRequest.model_validate(json.loads(capsys.readouterr().out))
    assert len(request.matrix) == 12
