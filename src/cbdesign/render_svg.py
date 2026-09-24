"""Accessible, dimensioned SVG views derived solely from replayed geometry.

The stock view uses source-coordinate provenance rather than the current coordinate
system.  It intentionally renders only final material and ``Replay.losses``: live
intermediate parts are ancestors of those regions and must not be counted twice.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape
from typing import Iterable

from .geometry import Box
from .replay import Part, Region, Replay

COLORS = ("#c9975b", "#4a2d1b", "#618a61", "#527a9b", "#a85e6d")
CATEGORY_COLORS = {
    "finished": "#2f855a",
    "kerf": "#9b2c2c",
    "milling": "#805ad5",
    "trim": "#dd6b20",
    "other_offcuts": "#4a5568",
}
CATEGORY_LABELS = {
    "finished": "finished",
    "kerf": "kerf",
    "milling": "milling",
    "trim": "trim",
    "other_offcuts": "other offcuts",
}


def species_colors(replay: Replay) -> dict[str, str]:
    """Return a stable species-to-colour mapping independent of encounter order."""
    species = sorted(
        {region.species for part in replay.parts.values() for region in part.regions}
        | set(replay.source_species.values())
    )
    return {name: COLORS[index % len(COLORS)] for index, name in enumerate(species)}


def _mm(value_um: int) -> str:
    """Format an integer micrometre length as a compact, readable millimetre value."""
    whole, fraction = divmod(int(value_um), 1000)
    if not fraction:
        return f"{whole} mm"
    return f"{whole}.{fraction:03d}".rstrip("0") + " mm"


def _size_label(size: tuple[int, int, int]) -> str:
    """Keep the machine-unit label for existing consumers and accessible text."""
    return f"{size[0]} × {size[1]} × {size[2]} µm (X × Y × Z)"


def _size_mm_label(size: tuple[int, int, int]) -> str:
    return " × ".join(_mm(value) for value in size) + " (X × Y × Z)"


def _grain_arrow(region: Region, x: float, y: float, w: float, h: float) -> str:
    """Draw grain direction in the displayed XY plane where it is meaningful."""
    gx, gy = region.grain[:2]
    if min(w, h) < 10:
        return ""
    if gx == gy == 0:
        # A circled dot/cross denotes out-of-plane grain, never a diagonal XY arrow.
        cx, cy = x + w / 2, y + h / 2
        mark = (f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="1.2" fill="#1a202c"/>'
                if region.grain[2] > 0 else
                f'<path d="M {cx - 2:.2f} {cy - 2:.2f} l 4 4 m -4 0 l 4 -4" class="grain"/>')
        return f'<g><title>grain normal to displayed face: {region.grain[2]:+d}Z</title><circle class="grain" cx="{cx:.2f}" cy="{cy:.2f}" r="4" fill="none"/>{mark}</g>'
    if abs(gx) >= abs(gy):
        start, end = (x + w * 0.2, x + w * 0.8) if gx > 0 else (x + w * 0.8, x + w * 0.2)
        return f'<line class="grain" x1="{start:.2f}" y1="{y + h / 2:.2f}" x2="{end:.2f}" y2="{y + h / 2:.2f}" marker-end="url(#arrow)"/>'
    start, end = (y + h * 0.2, y + h * 0.8) if gy > 0 else (y + h * 0.8, y + h * 0.2)
    return f'<line class="grain" x1="{x + w / 2:.2f}" y1="{start:.2f}" x2="{x + w / 2:.2f}" y2="{end:.2f}" marker-end="url(#arrow)"/>'


def _svg_shell(title: str, description: str, width: float, height: float, body: str) -> str:
    """Produce self-contained, escaped SVG with a consistent accessible style."""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}" role="img" aria-labelledby="svg-title svg-description">
  <title id="svg-title">{escape(title)}</title>
  <desc id="svg-description">{escape(description)}</desc>
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#1a202c"/></marker>
  </defs>
  <style>
    text {{ font-family: sans-serif; fill: #1a202c; }} .heading {{ font-size: 16px; font-weight: 700; }} .label {{ font-size: 12px; }} .small {{ font-size: 10px; }}
    .outline {{ stroke: #1a202c; stroke-width: 1.2; vector-effect: non-scaling-stroke; }} .grain {{ stroke: #1a202c; stroke-width: 1.5; vector-effect: non-scaling-stroke; }}
    .dimension {{ stroke: #4a5568; stroke-width: 1; vector-effect: non-scaling-stroke; }} .dim-label {{ font-size: 11px; fill: #2d3748; }}
  </style>
  <rect width="100%" height="100%" fill="white"/>
  {body}
</svg>'''


def _dimensioned_parts_svg(parts: list[Part], title: str, colors: dict[str, str]) -> str:
    """Render current-coordinate board or first-panel views with visible mm dimensions."""
    if not parts:
        return _svg_shell(title, "No first-stage panels were produced by the replay.", 720, 120, '<text class="heading" x="20" y="38">No panels to display</text>')
    max_x = max(part.size[0] for part in parts)
    total_y = sum(part.size[1] for part in parts) + max(1, sum(part.size[1] for part in parts) // 20) * (len(parts) - 1)
    scale = min(620 / max(max_x, 1), 500 / max(total_y, 1))
    legend = "".join(
        f'<rect class="outline" x="{20 + index * 125}" y="24" width="14" height="14" fill="{color}"><title>{escape(species)}: {color}</title></rect><text class="label" x="{40 + index * 125}" y="36">{escape(species)}</text>'
        for index, (species, color) in enumerate(colors.items())
    )
    body = [f'<text class="heading" x="20" y="18">{escape(title)}</text>', legend]
    body.append('<text class="small" x="20" y="54">Grain: arrows follow XY coordinates (Y down); circled dot/cross = +Z/−Z, normal to the face.</text>')
    y_offset = 68
    for part in parts:
        x0, y0 = 90.0, float(y_offset + 30)
        w, h = part.size[0] * scale, part.size[1] * scale
        body.append(f'<text class="label" x="{x0:.2f}" y="{y0 - 16:.2f}">{escape(part.id)} — {escape(_size_mm_label(part.size))}</text>')
        # The original µm wording remains in SVG text for stable API/legacy consumers.
        body.append(f'<title>{escape(part.id)} — {escape(_size_label(part.size))}</title>')
        body.append(f'<rect class="outline" x="{x0:.2f}" y="{y0:.2f}" width="{w:.2f}" height="{h:.2f}" fill="#f7fafc"/>')
        for region in part.regions:
            x = x0 + region.current.origin[0] * scale
            y = y0 + region.current.origin[1] * scale
            rw, rh = region.current.size[0] * scale, region.current.size[1] * scale
            detail = f"{region.species}; source {region.source_id}; grain {region.grain}; region {_size_mm_label(region.current.size)}"
            body.append(f'<rect class="outline" x="{x:.2f}" y="{y:.2f}" width="{rw:.2f}" height="{rh:.2f}" fill="{colors[region.species]}"><title>{escape(detail)}</title></rect>')
            body.append(_grain_arrow(region, x, y, rw, rh))
        # Width and length dimension lines make units visible in the drawing itself.
        body.append(f'<line class="dimension" x1="{x0:.2f}" y1="{y0 + h + 12:.2f}" x2="{x0 + w:.2f}" y2="{y0 + h + 12:.2f}"/><text class="dim-label" text-anchor="middle" x="{x0 + w / 2:.2f}" y="{y0 + h + 25:.2f}">X {_mm(part.size[0])}</text>')
        body.append(f'<line class="dimension" x1="{x0 - 14:.2f}" y1="{y0:.2f}" x2="{x0 - 14:.2f}" y2="{y0 + h:.2f}"/><text class="dim-label" text-anchor="end" x="{x0 - 18:.2f}" y="{y0 + h / 2:.2f}">Y {_mm(part.size[1])}</text>')
        body.append(f'<text class="small" x="{x0 + w + 14:.2f}" y="{y0 + 13:.2f}">Z {_mm(part.size[2])}</text>')
        y_offset += int(h + 78)
    height = max(150, y_offset + 15)
    description = "Dimensioned nominal replay geometry. Region outlines preserve physical boundaries, including same-species joints; arrows show grain direction in the displayed plane."
    return _svg_shell(title, description, 820, height, "".join(body))


def board_svg(replay: Replay) -> str:
    return _dimensioned_parts_svg([replay.parts[replay.terminal]], "Finished nominal board", species_colors(replay))


def panels_svg(replay: Replay) -> str:
    return _dimensioned_parts_svg(list(replay.first_glue_panels.values()), "First-stage panels from nominal replay", species_colors(replay))


def _stock_regions(replay: Replay) -> dict[str, list[tuple[str, Region]]]:
    """Return the one source partition represented by finished material plus losses."""
    grouped: dict[str, list[tuple[str, Region]]] = defaultdict(list)
    for region in replay.parts[replay.terminal].regions:
        grouped[region.source_id].append(("finished", region))
    for category, regions in replay.losses.items():
        if category not in CATEGORY_COLORS:
            continue
        for region in regions:
            grouped[region.source_id].append((category, region))
    return grouped


def _z_layers(regions: Iterable[tuple[str, Region]], source_size: tuple[int, int, int]) -> list[tuple[int, int]]:
    endpoints = {0, source_size[2]}
    for _, region in regions:
        endpoints.add(region.source.origin[2])
        endpoints.add(region.source.origin[2] + region.source.size[2])
    ordered = sorted(endpoints)
    return [(lower, upper) for lower, upper in zip(ordered, ordered[1:]) if lower < upper]


def stock_svg(replay: Replay) -> str:
    """Render source-coordinate material accounting in exploded Z slabs.

    Each source root is shown independently.  Z slabs are split at provenance box
    endpoints, so source boxes that overlap in X/Y at different Z values never hide
    one another.  Within every slab, category-coloured outlined regions are the exact
    final/loss partition used by ``Replay.ledger``.
    """
    grouped = _stock_regions(replay)
    scale = min(300 / max((size[0] for size in replay.source_sizes.values()), default=1), 220 / max((size[1] for size in replay.source_sizes.values()), default=1))
    y_cursor = 86.0
    body = [
        '<text class="heading" x="20" y="20">Source-coordinate stock breakdown</text>',
        '<text class="small" x="20" y="40">Exploded Z slabs show separate depths. Colours identify disposition; outlines preserve source-region boundaries.</text>',
    ]
    for index, category in enumerate(("finished", "kerf", "milling", "trim", "other_offcuts")):
        x = 20 + index * 145
        body.append(f'<rect class="outline" x="{x}" y="52" width="14" height="14" fill="{CATEGORY_COLORS[category]}"/><text class="label" x="{x + 20}" y="64">{CATEGORY_LABELS[category]}</text>')
    for source_id in sorted(replay.source_sizes):
        source_size = replay.source_sizes[source_id]
        regions = grouped.get(source_id, [])
        body.append(f'<text class="heading" x="20" y="{y_cursor:.2f}">Source {escape(source_id)} — {escape(replay.source_species[source_id])} — {escape(_size_mm_label(source_size))}</text>')
        body.append(f'<title>Source {escape(source_id)} — {escape(_size_label(source_size))}</title>')
        y_cursor += 22
        layers = _z_layers(regions, source_size)
        for z_min, z_max in layers:
            x0, y0 = 125.0, y_cursor + 18
            w, h = source_size[0] * scale, source_size[1] * scale
            body.append(f'<text class="label" x="20" y="{y0 + 12:.2f}">Z {_mm(z_min)}–{_mm(z_max)}</text>')
            body.append(f'<rect class="outline" x="{x0:.2f}" y="{y0:.2f}" width="{w:.2f}" height="{h:.2f}" fill="#f7fafc"><title>{escape(source_id)} source X/Y extent, Z {_mm(z_min)} to {_mm(z_max)}</title></rect>')
            slab = Box((0, 0, z_min), (source_size[0], source_size[1], z_max - z_min))
            for category, region in regions:
                hit = region.source.intersect(slab)
                if hit is None:
                    continue
                x, y = x0 + hit.origin[0] * scale, y0 + hit.origin[1] * scale
                rw, rh = hit.size[0] * scale, hit.size[1] * scale
                label = f"{source_id}; {region.species}; {CATEGORY_LABELS[category]}; source X {_mm(hit.origin[0])}–{_mm(hit.origin[0] + hit.size[0])}, Y {_mm(hit.origin[1])}–{_mm(hit.origin[1] + hit.size[1])}, Z {_mm(hit.origin[2])}–{_mm(hit.origin[2] + hit.size[2])}"
                body.append(f'<rect class="outline" x="{x:.2f}" y="{y:.2f}" width="{rw:.2f}" height="{rh:.2f}" fill="{CATEGORY_COLORS[category]}"><title>{escape(label)}</title></rect>')
            body.append(f'<line class="dimension" x1="{x0:.2f}" y1="{y0 + h + 10:.2f}" x2="{x0 + w:.2f}" y2="{y0 + h + 10:.2f}"/><text class="dim-label" text-anchor="middle" x="{x0 + w / 2:.2f}" y="{y0 + h + 22:.2f}">X {_mm(source_size[0])}</text>')
            body.append(f'<text class="small" x="{x0 + w + 10:.2f}" y="{y0 + 12:.2f}">Y {_mm(source_size[1])}</text>')
            y_cursor += h + 40
        y_cursor += 16
    height = max(140, y_cursor + 15)
    description = "Source-coordinate material ledger projection. Finished material and the kerf, milling, trim, and other-offcut losses are shown once only; live intermediate parts are excluded."
    return _svg_shell("Source-coordinate stock breakdown", description, 900, height, "".join(body))
