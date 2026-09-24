"""Immutable binary image targets and exact area resampling.

Coordinates use an image convention: column ``x`` increases left-to-right and row
``y`` increases top-to-bottom.  A target always covers its entire finished
rectangle; decoding never trims it, and resampling never crops it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from io import BytesIO
import json
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Sequence

from PIL import Image, ImageOps, UnidentifiedImageError

DEFAULT_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_PIXELS = 16_000_000
DEFAULT_MAX_FRAMES = 1
DEFAULT_FORMATS = frozenset({"PNG"})
JsonValue = str | int | float | bool | None | tuple["JsonValue", ...] | tuple[tuple[str, "JsonValue"], ...]


class TargetDecodeError(ValueError):
    """Raised when an image is not within the deterministic target contract."""


def _freeze_json(value: Any) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("target metadata keys must be strings")
        return tuple(sorted((key, _freeze_json(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise ValueError("target metadata must contain JSON values")


@dataclass(frozen=True)
class FrozenTarget:
    """An immutable rectangular binary target; 1 and 0 are configurable labels."""

    rows: tuple[tuple[int, ...], ...]
    metadata: JsonValue = field(default_factory=tuple)

    def __post_init__(self) -> None:
        normalized = tuple(tuple(row) for row in self.rows)
        if not normalized or not normalized[0]:
            raise ValueError("target must have at least one row and column")
        if any(len(row) != len(normalized[0]) for row in normalized):
            raise ValueError("target rows must be rectangular")
        if any(cell not in (0, 1) or isinstance(cell, bool) for row in normalized for cell in row):
            raise ValueError("target cells must be integer 0 or 1")
        object.__setattr__(self, "rows", normalized)
        object.__setattr__(self, "metadata", _freeze_json(self.metadata))

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def width(self) -> int:
        return len(self.rows[0])

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation with ordinary lists."""
        return {"rows": [list(row) for row in self.rows], "metadata": _thaw_json(self.metadata)}


def _thaw_json(value: JsonValue) -> Any:
    # Metadata mappings are represented by pairs, while JSON arrays are tuples.
    if isinstance(value, tuple):
        if all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value):
            return {key: _thaw_json(item) for key, item in value}
        return [_thaw_json(item) for item in value]
    return value


def decode_png(
    data: bytes | bytearray | memoryview | BinaryIO | str | Path,
    *,
    crop: tuple[int, int, int, int] | None = None,
    threshold: int = 128,
    one_for_dark: bool = True,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_pixels: int = DEFAULT_MAX_PIXELS,
    max_frames: int = DEFAULT_MAX_FRAMES,
    formats: Sequence[str] = tuple(DEFAULT_FORMATS),
    metadata: Mapping[str, Any] | None = None,
) -> FrozenTarget:
    """Decode a constrained PNG deterministically.

    EXIF orientation is applied first. ``crop`` is then a half-open pixel box in
    that oriented image. Transparent pixels are composited over white before an
    integer BT.601 luminance (``(299R + 587G + 114B) // 1000``) is thresholded.
    Values below ``threshold`` are dark.  No automatic crop, trim, scaling, or
    palette-dependent conversion is performed.
    """
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 0 <= threshold <= 256:
        raise ValueError("threshold must be an integer from 0 through 256")
    if not isinstance(one_for_dark, bool):
        raise ValueError("one_for_dark must be boolean")
    for name, value in (("max_bytes", max_bytes), ("max_pixels", max_pixels), ("max_frames", max_frames)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    accepted = {item.upper() for item in formats}
    if not accepted:
        raise ValueError("formats must not be empty")
    raw: bytes
    if isinstance(data, (str, Path)):
        raw = Path(data).read_bytes()
    elif isinstance(data, (bytes, bytearray, memoryview)):
        raw = bytes(data)
    else:
        raw = data.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise TargetDecodeError("image exceeds byte limit")
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format is None or source.format.upper() not in accepted:
                raise TargetDecodeError("image format is not allowed")
            frames = getattr(source, "n_frames", 1)
            if frames > max_frames:
                raise TargetDecodeError("image exceeds frame limit")
            if source.width < 1 or source.height < 1 or source.width * source.height > max_pixels:
                raise TargetDecodeError("image exceeds pixel limit")
            source.seek(0)
            image = ImageOps.exif_transpose(source)
            if image.width * image.height > max_pixels:
                raise TargetDecodeError("oriented image exceeds pixel limit")
            if crop is not None:
                if len(crop) != 4 or any(isinstance(v, bool) or not isinstance(v, int) for v in crop):
                    raise ValueError("crop must be four integer pixel coordinates")
                left, top, right, bottom = crop
                if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
                    raise ValueError("crop must be nonempty and inside the oriented image")
                image = image.crop(crop)
            rgba = image.convert("RGBA")
            rows = []
            for y in range(rgba.height):
                row = []
                for x in range(rgba.width):
                    red, green, blue, alpha = rgba.getpixel((x, y))
                    # Integer alpha composite over white, rounded down deterministically.
                    red = (red * alpha + 255 * (255 - alpha)) // 255
                    green = (green * alpha + 255 * (255 - alpha)) // 255
                    blue = (blue * alpha + 255 * (255 - alpha)) // 255
                    dark = (299 * red + 587 * green + 114 * blue) // 1000 < threshold
                    row.append(int(dark if one_for_dark else not dark))
                rows.append(tuple(row))
    except TargetDecodeError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise TargetDecodeError("invalid image data") from error
    info = {"format": "PNG", "source_width": len(rows[0]), "source_height": len(rows),
            "threshold": threshold, "one_for_dark": one_for_dark}
    if crop is not None:
        info["crop"] = list(crop)
    if metadata:
        info.update(metadata)
    return FrozenTarget(tuple(rows), info)


target_from_png = decode_png


def _as_fraction(value: int | Fraction) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, Fraction)):
        raise ValueError("physical bounds must be integers or Fractions")
    return Fraction(value)


def _equal_bounds(count: int, extent: Fraction) -> tuple[Fraction, ...]:
    return tuple(extent * index / count for index in range(count + 1))


def _bounds(bounds: Sequence[int | Fraction], name: str, extent: Fraction) -> tuple[Fraction, ...]:
    out = tuple(_as_fraction(value) for value in bounds)
    if len(out) < 2 or out[0] != 0 or out[-1] != extent or any(a >= b for a, b in zip(out, out[1:])):
        raise ValueError(f"{name} must strictly partition [0, {extent}]")
    return out


def target_occupancy(
    matrix: FrozenTarget | Sequence[Sequence[int]],
    rows: int | None = None,
    columns: int | None = None,
    *,
    row_bounds: Sequence[int | Fraction] | None = None,
    column_bounds: Sequence[int | Fraction] | None = None,
    finished_width: int | Fraction = 1,
    finished_height: int | Fraction = 1,
) -> tuple[tuple[Fraction, ...], ...]:
    """Return exact 1-occupancy for cells partitioning a finished rectangle.

    The source grid spans ``[0, finished_width] × [0, finished_height]`` without
    cropping. Output rows are top-to-bottom. Each result is occupied overlap area
    divided by that output cell's area, represented exactly as ``Fraction``.
    Specify either ``rows``/``columns`` for equal cells or physical boundary lists.
    """
    source = matrix.rows if isinstance(matrix, FrozenTarget) else tuple(tuple(row) for row in matrix)
    frozen = FrozenTarget(source)  # validates arbitrary input
    width, height = _as_fraction(finished_width), _as_fraction(finished_height)
    if width <= 0 or height <= 0:
        raise ValueError("finished dimensions must be positive")
    if (row_bounds is None) != (column_bounds is None):
        raise ValueError("row_bounds and column_bounds must be supplied together")
    if row_bounds is not None:
        if rows is not None or columns is not None:
            raise ValueError("use either counts or physical bounds, not both")
        ys, xs = _bounds(row_bounds, "row_bounds", height), _bounds(column_bounds, "column_bounds", width)
    else:
        if isinstance(rows, bool) or isinstance(columns, bool) or not isinstance(rows, int) or not isinstance(columns, int) or rows < 1 or columns < 1:
            raise ValueError("rows and columns must be positive integers")
        ys, xs = _equal_bounds(rows, height), _equal_bounds(columns, width)
    source_x = _equal_bounds(frozen.width, width)
    source_y = _equal_bounds(frozen.height, height)
    output = []
    for top, bottom in zip(ys, ys[1:]):
        row = []
        for left, right in zip(xs, xs[1:]):
            occupied = Fraction(0)
            for sy in range(frozen.height):
                overlap_y = max(Fraction(0), min(bottom, source_y[sy + 1]) - max(top, source_y[sy]))
                if not overlap_y:
                    continue
                for sx in range(frozen.width):
                    if frozen.rows[sy][sx]:
                        overlap_x = max(Fraction(0), min(right, source_x[sx + 1]) - max(left, source_x[sx]))
                        occupied += overlap_x * overlap_y
            row.append(occupied / ((right - left) * (bottom - top)))
        output.append(tuple(row))
    return tuple(output)


# A cheap guard that documents the serialization contract at import-time.
json.dumps(FrozenTarget(((0,),), {"kind": "binary"}).as_dict())
