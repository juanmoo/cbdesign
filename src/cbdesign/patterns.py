"""Small deterministic binary target patterns.

Every factory returns a :class:`FrozenTarget` whose rows are directly usable as a
binary compiler matrix (top-to-bottom rows, left-to-right columns).
"""
from __future__ import annotations

from .target import FrozenTarget


def _dimensions(rows: int, columns: int) -> None:
    if isinstance(rows, bool) or isinstance(columns, bool) or not isinstance(rows, int) or not isinstance(columns, int) or rows < 1 or columns < 1:
        raise ValueError("rows and columns must be positive integers")


def _target(kind: str, rows: int, columns: int, cell) -> FrozenTarget:
    _dimensions(rows, columns)
    return FrozenTarget(tuple(tuple(int(bool(cell(y, x))) for x in range(columns)) for y in range(rows)),
                        {"pattern": kind})


def checkerboard(rows: int = 8, columns: int = 8) -> FrozenTarget:
    return _target("checkerboard", rows, columns, lambda y, x: (x + y) % 2)


def stripes(rows: int = 8, columns: int = 8, *, vertical: bool = True, stripe_width: int = 1) -> FrozenTarget:
    _dimensions(rows, columns)
    if isinstance(stripe_width, bool) or not isinstance(stripe_width, int) or stripe_width < 1:
        raise ValueError("stripe_width must be a positive integer")
    return _target("vertical_stripes" if vertical else "horizontal_stripes", rows, columns,
                   lambda y, x: ((x if vertical else y) // stripe_width) % 2)


def basket_weave(rows: int = 8, columns: int = 8, *, block: int = 2) -> FrozenTarget:
    _dimensions(rows, columns)
    if isinstance(block, bool) or not isinstance(block, int) or block < 1:
        raise ValueError("block must be a positive integer")
    return _target("basket_weave", rows, columns,
                   lambda y, x: ((x // block) % 2) ^ ((y // block) % 2) ^ ((y % block) < block // 2))


def diamond(rows: int = 9, columns: int = 9) -> FrozenTarget:
    _dimensions(rows, columns)
    cy, cx = (rows - 1) / 2, (columns - 1) / 2
    return _target("diamond", rows, columns, lambda y, x: abs(y - cy) / max(cy, .5) + abs(x - cx) / max(cx, .5) <= 1)


def letter(rows: int = 7, columns: int = 5, *, glyph: str = "A") -> FrozenTarget:
    """Return a compact block-letter target (currently A, H, I, or X)."""
    _dimensions(rows, columns)
    glyph = glyph.upper()
    if glyph not in {"A", "H", "I", "X"}:
        raise ValueError("glyph must be one of A, H, I, or X")
    def pixel(y: int, x: int) -> bool:
        top, bottom = y == 0, y == rows - 1
        left, right, middle = x == 0, x == columns - 1, y == rows // 2
        if glyph == "A": return top or left or right or middle
        if glyph == "H": return left or right or middle
        if glyph == "I": return top or bottom or x == columns // 2
        return x * (rows - 1) == y * (columns - 1) or (columns - 1 - x) * (rows - 1) == y * (columns - 1)
    return _target(f"letter_{glyph}", rows, columns, pixel)


def asymmetric(rows: int = 7, columns: int = 9) -> FrozenTarget:
    """An intentionally non-reflection-symmetric stepped motif."""
    return _target("asymmetric", rows, columns,
                   lambda y, x: (x < columns // 3 and y >= rows // 3) or
                                (x >= columns // 3 and y < rows // 2) or
                                (x == columns - 2 and y == rows - 1))


def unrelated(rows: int = 7, columns: int = 9) -> FrozenTarget:
    """A deterministic motif unlike the common geometric reference patterns."""
    return _target("unrelated", rows, columns,
                   lambda y, x: (x * 3 + y * 5 + x * y) % 7 in {0, 1})


def mouse_head(rows: int = 15, columns: int = 15) -> FrozenTarget:
    """Three-circle mouse-head silhouette, 1 for the silhouette."""
    _dimensions(rows, columns)
    # Work in doubled coordinates so circle inclusion is entirely integral.
    def circle(y: int, x: int, cy: int, cx: int, radius: int) -> bool:
        return (2 * y - cy) ** 2 + (2 * x - cx) ** 2 <= radius ** 2
    cy, cx = rows - 1, columns - 1
    radius = min(rows, columns) * 2 // 5
    ear = max(2, radius * 3 // 5)
    return _target("mouse_head", rows, columns,
                   lambda y, x: circle(y, x, cy, cx, radius) or
                                circle(y, x, cy - radius, cx - radius, ear) or
                                circle(y, x, cy - radius, cx + radius, ear))
