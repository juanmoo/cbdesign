"""Portable operation/material exports derived from independent replay."""
from __future__ import annotations

import csv
import io
import json
from html import escape


def _cell(value):
    text = str(value)
    # Spreadsheet programs may interpret identifiers as formulas even when quoted.
    return "'" + text if text.startswith(('=', '+', '-', '@', '\t', '\r')) else text


def operations_csv(replay) -> str:
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['operation', 'kind', 'inputs', 'outputs', 'input_dimensions_um', 'output_dimensions_um', 'settings_json'])
    for op in replay.operations:
        settings = {k: v for k, v in op.items() if k not in {'id', 'kind', 'inputs', 'outputs', 'input_size_um', 'input_sizes_um', 'output_sizes_um'}}
        writer.writerow([_cell(op['id']), op['kind'], _cell(';'.join(op['inputs'])),
                         _cell(';'.join(op['outputs'])),
                         json.dumps(op.get('input_sizes_um', op.get('input_size_um')), sort_keys=True),
                         json.dumps(op['output_sizes_um'], sort_keys=True), json.dumps(settings, sort_keys=True)])
    return stream.getvalue()


def material_csv(replay) -> str:
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    fields = ['stock', 'finished', 'kerf', 'milling', 'trim', 'other_offcuts', 'balance']
    writer.writerow(['species', *[f'{field}_um3' for field in fields]])
    for species, row in replay.ledger()['species'].items():
        writer.writerow([_cell(species), *[row[field] for field in fields]])
    return stream.getvalue()


def report_pdf(plan, report, replay, uncertainty=None) -> bytes:
    """Build deterministic paginated text/tables, without treating them as machine instructions."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, LongTable, TableStyle, KeepTogether

    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    story = []

    def para(text, style='BodyText'):
        return Paragraph(escape(str(text)), styles[style])

    story.extend([para(plan.title, 'Title'), para('Nominal fabrication report', 'Heading2'),
                  para('Illustrative planning output. Not a machine program, safety assessment, joint-strength certificate or shop-ready instruction.'),
                  para(f"Validation: {report['status']}"),
                  para('Finished X / Y / Z: ' + ' / '.join(f'{v / 1000:g} mm' for v in replay.parts[replay.terminal].size))])
    for assumption in plan.assumptions:
        story.append(para(assumption))
    story.append(para('Validation coverage', 'Heading2'))
    story.append(para('Passed: ' + ', '.join(report['coverage']['passed'])))
    story.append(para('Not evaluated: ' + ', '.join(report['coverage']['not_evaluated'])))
    if uncertainty is not None:
        story.append(para('Dimensional bounds (nominal ledger unchanged)', 'Heading2'))
        story.append(para(json.dumps(uncertainty, sort_keys=True)))
    story.append(para('Material accounting', 'Heading2'))
    fields = ['stock', 'finished', 'kerf', 'milling', 'trim', 'other_offcuts']
    rows = [[para('Species'), para('Material category'), para('Volume (mm3)')]]
    for species, data in replay.ledger()['species'].items():
        for field in fields:
            rows.append([para(species), para(field.replace('_', ' ')), para(f'{data[field] / 10**9:,.3f}')])
    table = LongTable(rows, colWidths=[110, 180, 180], repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('GRID', (0, 0), (-1, -1), .3, colors.grey), ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke)]))
    story.extend([table, Spacer(1, 12), para('Recorded operation sequence', 'Heading2')])
    for index, op in enumerate(replay.operations, 1):
        block = [para(f"{index}. {op['id']} — {op['kind']}", 'Heading3'),
                 para('Inputs: ' + ', '.join(op['inputs'])),
                 para('Outputs: ' + ', '.join(op['outputs']))]
        for part, size in op['output_sizes_um'].items():
            block.append(para(f"{part}: " + ' × '.join(f'{v / 1000:g}' for v in size) + ' mm (X × Y × Z)'))
        details = {k: v for k, v in op.items() if k not in {'id', 'kind', 'inputs', 'outputs', 'output_sizes_um'}}
        block.append(para(json.dumps(details, sort_keys=True)))
        story.append(KeepTogether(block))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.drawString(36, 20, 'cbdesign • nominal planning only • dimensions in mm unless marked um')
        canvas.drawRightString(A4[0] - 36, 20, str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(stream, pagesize=A4, leftMargin=36, rightMargin=36,
                            topMargin=36, bottomMargin=36, invariant=1, title=plan.title)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
