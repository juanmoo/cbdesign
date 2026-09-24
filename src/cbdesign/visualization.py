"""Small self-contained SVG views for immutable target comparison."""
from __future__ import annotations
from html import escape
from .target import FrozenTarget


def _shell(title: str, body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 530" role="img"><title>{escape(title)}</title><rect width="100%" height="100%" fill="white"/><text x="20" y="18" font-family="sans-serif" font-size="14" font-weight="bold">{escape(title)}</text>{body}</svg>'


def target_svg(target: FrozenTarget, title: str = "Immutable target") -> str:
    """Render exact binary target pixels without crop or interpolation."""
    size, pad = 480, 20
    cw, ch = size / target.width, size / target.height
    cells = ''.join(f'<rect x="{pad+x*cw:.3f}" y="{pad+y*ch:.3f}" width="{cw:.3f}" height="{ch:.3f}" fill="{"#242424" if value else "#f6f2e8"}"/>' for y,row in enumerate(target.rows) for x,value in enumerate(row))
    return _shell(title, f'{cells}<rect x="20" y="20" width="480" height="480" fill="none" stroke="#111"/>')


def difference_svg(replay, target: FrozenTarget, species_mapping: dict[str, str] | None = None, title: str = "Mismatch: target versus achieved") -> str:
    """Render actual-only red and target-only blue regions after final trimming.

    ``species_mapping`` explicitly maps binary labels (``A``/``B``) to species;
    no alphabetical species ordering is inferred.
    """
    terminal = replay.parts[replay.terminal]
    target_species = (species_mapping or {}).get("B")
    size, pad = 480, 20
    sx, sy = size / terminal.size[0], size / terminal.size[1]
    target_cells = ''.join(f'<rect x="{pad+x*size/target.width:.3f}" y="{pad+y*size/target.height:.3f}" width="{size/target.width:.3f}" height="{size/target.height:.3f}" fill="#2d6ea3" fill-opacity=".74"/>' for y,row in enumerate(target.rows) for x,value in enumerate(row) if value)
    actual = ''.join(f'<rect x="{pad+r.current.origin[0]*sx:.3f}" y="{pad+r.current.origin[1]*sy:.3f}" width="{r.current.size[0]*sx:.3f}" height="{r.current.size[1]*sy:.3f}" fill="#d1493f" fill-opacity=".82"/>' for r in terminal.regions if r.species == target_species)
    # Blue lays down desired B pixels. Red then marks physical B material; overlapping
    # areas are deliberately dark purple, making agreement and either mismatch visible.
    legend = '<rect x="20" y="508" width="12" height="12" fill="#2d6ea3"/><text x="37" y="519" font-family="sans-serif" font-size="11">target B</text><rect x="115" y="508" width="12" height="12" fill="#d1493f"/><text x="132" y="519" font-family="sans-serif" font-size="11">achieved B; overlap = purple</text>'
    return _shell(title, f'{target_cells}{actual}<rect x="20" y="20" width="480" height="480" fill="none" stroke="#111"/>{legend}')
