"""HTML/SVG walkthrough of exact, validated operation snapshots."""
from __future__ import annotations

from html import escape
from .replay import replay
from .replay_trace import ReplayTrace, TraceLimitError
from .render_svg import species_colors, _mm as _mm_label


def _mm(value):
    return _mm_label(value).removesuffix(' mm')

REPLAY_CSS = """.replay-step{font:14px/1.5 system-ui,sans-serif;color:#20323f;background:#fff;padding:12px;overflow-wrap:anywhere}.replay-step svg{display:block;width:100%;height:auto;border:1px solid #b8c9d2;background:#fff}.replay-step .links a{color:#176483;text-decoration:underline}.replay-step .meta{color:#526673}.replay-step .diagrams{display:grid;gap:12px}.replay-step .part{padding-block:8px}.replay-step h3{margin-block:12px 6px}.replay-step li{margin-block:4px}.replay-step summary{cursor:pointer}.replay-step .legend{display:flex;gap:16px;flex-wrap:wrap}.replay-step .swatch{display:inline-block;width:14px;height:14px;border:1px solid #20323f;margin-right:5px}.replay-step .planes{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}.replay-step table{display:block;overflow-x:auto;border-collapse:collapse;max-width:100%}@media(max-width:600px){.replay-step .planes{grid-template-columns:1fr}}.replay-step td,.replay-step th{padding:6px;border-bottom:1px solid #b8c9d2;text-align:left}"""
MAX_RENDER_BYTES = 2_000_000
PLANES = (((0, 1), "XY"), ((0, 2), "XZ"), ((1, 2), "YZ"))


def _dims(part):
    return " × ".join(_mm(x) for x in part.size) + " mm (X × Y × Z)"


def _trace(result) -> ReplayTrace:
    trace = getattr(result, 'trace', None)
    if trace is None:
        raise ValueError('walkthrough requires a result from build_walkthrough(plan)')
    return trace


def build_walkthrough(plan):
    return replay(plan, trace=True)


def walkthrough_manifest(plan, result):
    trace = _trace(result)
    grouped = {item.id: {'id': item.id, 'species': item.species,
                        'cross_section_um': [int(item.width), int(item.thickness)], 'source_ids': []}
               for item in getattr(plan, 'stock_types', ())}
    for segment in getattr(plan, 'source_segments', ()):
        grouped[segment.stock_type]['source_ids'].append(segment.id)
    labels = ['Stock inventory', *[f'{s.index}. {s.kind}: {s.operation_id}' for s in trace.steps], 'Finished board']
    return {'operation_count': len(trace.steps), 'total_saw_cuts': sum(s.kind == 'cut' for s in trace.steps),
            'roots': [{'id': p.id, 'species': p.regions[0].species, 'size_um': list(p.size)} for p in trace.roots],
            'stock_groups': list(grouped.values()),
            'steps': [{'index': i, 'label': label} for i, label in enumerate(labels)]}


def _links(part, trace, dispositions):
    links = []
    if part.id in trace.producers:
        i = trace.producers[part.id]
        links.append(f'<a href="#step-{i}" data-step="{i}">Made at operation {i}</a>')
    else:
        links.append('<a href="#step-0" data-step="0">Starting stock</a>')
    if part.id in trace.consumers:
        i = trace.consumers[part.id]
        links.append(f'<a href="#step-{i}" data-step="{i}">Next used at operation {i}</a>')
    elif part.id == trace.terminal.id:
        links.append('Finished board')
    else:
        disposition = dispositions[part.id]
        links.append('Terminal ' + escape(disposition.category.replace('_', ' ')) +
                     ('; marked reusable, not reused in this plan' if disposition.reusable else '; not reused'))
    return ' · '.join(links)


def _grain(region, axes, x, y, w, h):
    gx, gy = region.grain[axes[0]], region.grain[axes[1]]
    cx, cy = x + w / 2, y + h / 2
    if min(w, h) < 5:
        return ''  # Exact direction remains in the part's textual grain label.
    if gx or gy:
        length = min((w if gx else h) * .28, 20)
        dx, dy = gx * length, gy * length
        # Arrowhead uses explicit coordinates, avoiding duplicated SVG marker IDs.
        tipx, tipy = cx + dx, cy + dy
        bx, by = tipx - gx * 3, tipy - gy * 3
        return (f'<path d="M{cx-dx:.3f},{cy-dy:.3f} L{tipx:.3f},{tipy:.3f} '
                f'M{bx-gy*2:.3f},{by+gx*2:.3f} L{tipx:.3f},{tipy:.3f} '
                f'L{bx+gy*2:.3f},{by-gx*2:.3f}" fill="none" stroke="#20323f"/>')
    normal = next(i for i in range(3) if i not in axes)
    return f'<text x="{cx:.3f}" y="{cy+4:.3f}" text-anchor="middle" font-size="12">{"⊙" if region.grain[normal] > 0 else "⊗"}</text>'


def _part_svg(part, scales, colors, highlights=()):
    views = []
    for col, (axes, name) in enumerate(PLANES):
        start = len(views)
        scale = scales[col]
        normal = next(i for i in range(3) if i not in axes)
        x, y = 16, 44
        width, height = part.size[axes[0]] * scale, part.size[axes[1]] * scale
        views.append(f'<text x="{x}" y="17" font-weight="700">{name}: +{"XYZ"[axes[0]]} → +{"XYZ"[axes[1]]} ↓</text>'
                     f'<text x="{x}" y="32" font-size="10">Face at {"XYZ"[normal]} = 0; 1 px = {1/scale/1000:.3g} mm</text>')
        for region in part.regions:
            # A half-open region meets the displayed minimum face iff origin is zero.
            if region.current.origin[normal] != 0:
                continue
            rx, ry = x + region.current.origin[axes[0]] * scale, y + region.current.origin[axes[1]] * scale
            rw, rh = region.current.size[axes[0]] * scale, region.current.size[axes[1]] * scale
            views.append(f'<rect x="{rx:.3f}" y="{ry:.3f}" width="{rw:.3f}" height="{rh:.3f}" fill="{colors[region.species]}" stroke="#20323f" stroke-width=".6"><title>{escape(region.species)}; source {escape(region.source_id)}; grain {region.grain}</title></rect>')
            views.append(_grain(region, axes, rx, ry, rw, rh))
        views.append(f'<rect x="{x}" y="{y}" width="{width:.3f}" height="{height:.3f}" fill="none" stroke="#20323f"/>')
        for box, label in highlights:
            # Dashed translucent projection intentionally shows the operation slab,
            # even if it lies behind the exposed face in this orthographic view.
            bx, by = x + box.origin[axes[0]] * scale, y + box.origin[axes[1]] * scale
            bw, bh = box.size[axes[0]] * scale, box.size[axes[1]] * scale
            views.append(f'<rect x="{bx:.3f}" y="{by:.3f}" width="{bw:.3f}" height="{bh:.3f}" fill="#d1493f" fill-opacity=".32" stroke="#b52d24" stroke-dasharray="3 2" stroke-width="1"><title>{escape(label)}; projected operation slab</title></rect>')
        views.append(f'<text x="{x}" y="{y+height+16:.3f}" font-size="11">{"XYZ"[axes[0]]} {_mm(part.size[axes[0]])} mm × {"XYZ"[axes[1]]} {_mm(part.size[axes[1]])} mm</text>')
        plane = ''.join(views[start:])
        views[start:] = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 230 165" role="img"><title>{escape(part.id)}: {name} exposed face</title><g font-family="system-ui,sans-serif" font-size="12" fill="#20323f">{plane}</g></svg>']
    return '<div class="planes">' + ''.join(views) + '</div>'


def _part_html(part, trace, dispositions, scales, colors, highlights=(), role=''):
    grain = ', '.join(str(g) for g in sorted({r.grain for r in part.regions}))
    return (f'<div class="part"><h3>{escape(role)} {escape(part.id)}</h3><p>{escape(_dims(part))}<br>'
            f'Grain vector(s): {escape(grain)}<br>{_links(part, trace, dispositions)}</p>'
            f'{_part_svg(part, scales, colors, highlights)}</div>')


def walkthrough_step(plan, result, index):
    trace = _trace(result)
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= len(trace.steps) + 1:
        raise IndexError('walkthrough step index out of range')
    manifest = walkthrough_manifest(plan, result)
    colors = species_colors(result)
    dispositions = {d.part: d for d in plan.dispositions}
    inputs, outputs, highlights = (), (), ()
    detail = ''
    if index == 0:
        title, kind, outputs = 'Stock inventory', 'stock', trace.roots
        groups = manifest['stock_groups']
        detail = (f'<p><b>{len(groups)} fixed-cross-section stock types; {len(outputs)} allocated source segments.</b> '
                  'Each segment starts with its own finite length. No cutting from unmodeled parent boards is implied.</p>') if groups else '<p>Legacy plan: individual starting stock pieces (no stock-type declarations).</p>'
        for group in groups:
            width, thickness = group['cross_section_um']
            detail += f'<p><b>{escape(group["id"])} — {escape(group["species"])}</b>: X width {_mm(width)} mm × Z thickness {_mm(thickness)} mm; {len(group["source_ids"])} allocated segments.</p>'
    elif index == len(trace.steps) + 1:
        title, kind, outputs = 'Finished board', 'final', (trace.terminal,)
        detail = '<p>Final replay-validated geometry. All other terminal material is accounted for as declared losses/offcuts.</p>'
    else:
        step = trace.steps[index - 1]
        inputs, outputs, kind = step.inputs, step.outputs, step.kind
        title = f'Operation {index} of {len(trace.steps)}: {kind}'
        operation = result.operations[index - 1]
        detail = f'<p><b>{escape(step.operation_id)}</b></p>'
        if kind == 'cut':
            kept, kerf, remainder = step.cut_boxes
            detail += (f'<p>Saw normal to {"XYZ"[step.axis]}. Cut starts {_mm(kerf.origin[step.axis])} mm from the minimum face; '
                       f'kerf {_mm(kerf.size[step.axis])} mm. Retain the {escape(step.retained_side or "min")} child '
                       f'({escape(outputs[0].id)}); retained length {_mm(kept.size[step.axis])} mm. '
                       'The other child may be used later; follow its link. Kerf is a loss, not an output piece.</p>')
            highlights = ((kerf, 'Kerf'),)
        elif kind == 'surface':
            detail += (f'<p>{escape(operation["process"])}: remove {_mm(operation["amount_um"])} mm from '
                       f'{"XYZ"[step.axis]} {escape(operation["side"])} face. The removed slab is a diagram of '
                       'material loss, not a reusable board.</p>')
            highlights = ((step.surface_boxes[1], 'Removed material'),)
        elif kind == 'rotate':
            mapping = ', '.join(f'{"XYZ"[i]} ← {"+" if step.rotation_sign[i] > 0 else "−"}{"XYZ"[step.rotation_perm[i]]}' for i in range(3))
            detail += f'<p>Net signed-axis rotation: {mapping}. Follow the species pattern and grain arrows before/after. No material is removed.</p>'
        else:
            detail += f'<p>{escape(operation["stage"])} glue-up along {"XYZ"[step.axis]}. Join each preceding maximum face to the next minimum face, in this order; glue-line thickness is modeled as negligible.</p><ol>'
            detail += ''.join(f'<li>{escape(p.id)} starts at {"XYZ"[step.axis]} = {_mm(offset)} mm in the assembled output.</li>' for p, offset in zip(inputs, step.glue_offsets)) + '</ol>'
    parts = inputs + outputs
    scales = tuple(min(195 / max(p.size[a] for p in parts), 90 / max(p.size[b] for p in parts)) for (a, b), _ in PLANES)
    saw = sum(s.kind == 'cut' for s in trace.steps[:min(index, len(trace.steps))])
    legend = '<div class="legend">' + ''.join(f'<span><i class="swatch" style="background:{color}"></i>{escape(species)}</span>' for species, color in colors.items()) + '</div>'
    detail += f'<p class="meta">Saw passes completed: {saw} / {manifest["total_saw_cuts"]}. Total operations: {len(trace.steps)}. Arrows show in-plane grain; ⊙/⊗ show positive/negative normal-axis grain.</p>{legend}'
    detail += '<p class="meta">Each plane uses the same scale before and after; scales differ between planes. Dashed red overlays project the cut/removal slab; thin outlines are emphasized without changing dimensions.</p>'
    if inputs:
        detail += '<h2>Before</h2><div class="diagrams">' + ''.join(_part_html(p, trace, dispositions, scales, colors, highlights) for p in inputs) + '</div>'
    detail += f'<h2>{"Starting pieces" if kind == "stock" else "After"}</h2><div class="diagrams">'
    for i, part in enumerate(outputs):
        role = ('Retained child' if i == 0 else 'Other child') if kind == 'cut' else ('Retained part' if i == 0 else 'Removed material') if kind == 'surface' else ''
        piece = _part_html(part, trace, dispositions, scales, colors, role=role)
        if kind == 'stock':
            piece = f'<details><summary>{escape(part.id)} — {escape(_dims(part))}</summary>{piece}</details>'
        detail += piece
    detail += '</div>'
    html = f'<style>{REPLAY_CSS}</style><section class="replay-step" id="step-{index}"><h2>{escape(title)}</h2>{detail}</section>'
    if len(html.encode()) > MAX_RENDER_BYTES:
        raise TraceLimitError('walkthrough step exceeds render byte limit')
    return {'index': index, 'label': title, 'kind': kind, 'saw_cuts_so_far': saw, 'html': html}
