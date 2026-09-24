"""Common in-memory reports for the CLI and local browser downloads."""
from __future__ import annotations

import io
import json
import zipfile

from .exports import material_csv, operations_csv, report_pdf
from .render_svg import board_svg, panels_svg, stock_svg

REPORT_FILES = frozenset({'plan.json', 'validation.json', 'material-ledger.json',
                          'board.svg', 'panels.svg', 'stock.svg', 'operations.txt',
                          'operations.csv', 'material.csv', 'report.pdf', 'uncertainty.json'})


def json_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def operations_text(operations: list[dict]) -> str:
    lines = ['Nominal replay operation report (dimensions are integer micrometres).']
    for op in operations:
        common = f"{op['id']} [{op['kind']}]: inputs={','.join(op['inputs'])}; outputs={','.join(op['outputs'])}"
        details = '; '.join(f'{key}={value}' for key, value in op.items() if key not in {'id', 'kind', 'inputs', 'outputs'})
        lines.append(f'{common}; {details}' if details else common)
    return '\n'.join(lines) + '\n'


def plan_bundle(plan, report, replay, uncertainty=None) -> dict[str, bytes]:
    if report['status'] != 'nominal_valid' or replay is None:
        raise ValueError('reports require an independently nominal-valid plan')
    files = {
        'plan.json': json_bytes(plan.model_dump(mode='json')),
        'validation.json': json_bytes(report),
        'material-ledger.json': json_bytes(replay.ledger()),
        'board.svg': board_svg(replay).encode(),
        'panels.svg': panels_svg(replay).encode(),
        'stock.svg': stock_svg(replay).encode(),
        'operations.txt': operations_text(replay.operations).encode(),
        'operations.csv': operations_csv(replay).encode(),
        'material.csv': material_csv(replay).encode(),
        'report.pdf': report_pdf(plan, report, replay, uncertainty),
    }
    if uncertainty is not None:
        files['uncertainty.json'] = json_bytes(uncertainty)
    return files


def zip_bundle(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, content)
    return stream.getvalue()
