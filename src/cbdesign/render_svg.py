"""Escaped, dimensioned SVG views derived solely from replayed geometry."""
from __future__ import annotations
from html import escape
from .replay import Replay, Part

COLORS = ("#c9975b", "#4a2d1b", "#618a61", "#527a9b", "#a85e6d")


def species_colors(replay: Replay) -> dict[str, str]:
    """Stable species-to-colour mapping, independent of view or region encounter order."""
    species = sorted({region.species for part in replay.parts.values() for region in part.regions} | set(replay.source_species.values()))
    return {name: COLORS[index % len(COLORS)] for index, name in enumerate(species)}


def _size_label(size: tuple[int, int, int]) -> str:
    return f"{size[0]} × {size[1]} × {size[2]} µm (X × Y × Z)"


def _svg(parts: list[Part], title: str, colors: dict[str, str]) -> str:
    width = max(part.size[0] for part in parts)
    height = sum(part.size[1] for part in parts)
    gutter = max(1, height // 30)
    scale = 700 / max(width, height, 1)
    y_offset = 0
    body = []
    labels = []
    for part in parts:
        part_y = y_offset
        for region in part.regions:
            x = region.current.origin[0] * scale
            y = (part_y + region.current.origin[1]) * scale
            w = region.current.size[0] * scale
            h = region.current.size[1] * scale
            body.append(
                f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" '
                f'fill="{colors[region.species]}" stroke="#202020" stroke-width="1">'
                f'<title>{escape(region.species)}; grain={escape(str(region.grain))}; source={escape(region.source_id)}</title></rect>'
            )
        labels.append(f'<text x="0" y="{(part_y - max(1, height // 80)) * scale:.3f}">{escape(part.id)} — {escape(_size_label(part.size))}</text>')
        y_offset += part.size[1] + gutter
    legend = "".join(f'<text x="10" y="{25 + index * 18}">{escape(species)}: {color}</text>' for index, (species, color) in enumerate(colors.items()))
    view_width = max(720, width * scale + 20)
    view_height = max(135, (y_offset + gutter) * scale + 80)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view_width:.1f} {view_height:.1f}" role="img" aria-label="{escape(title)}">'
        f'<title>{escape(title)}</title><g font-family="sans-serif" font-size="14">{legend}</g>'
        f'<g transform="translate(10 80)" font-family="sans-serif" font-size="13">{"".join(labels)}{"".join(body)}</g></svg>'
    )


def board_svg(replay: Replay) -> str:
    return _svg([replay.parts[replay.terminal]], "Finished nominal board; regions and grain derive from replay", species_colors(replay))


def panels_svg(replay: Replay) -> str:
    panels = list(replay.first_glue_panels.values())
    return _svg(panels, "First-stage panels from nominal replay", species_colors(replay))
