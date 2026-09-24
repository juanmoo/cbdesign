"""Deterministic finite stock allocation primitives used by the N2 compiler."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Allocation:
    stock_id: str
    length: int
    required: int
    residual: int


def allocate_lengths(stock_id: str, lengths: list[int], required: int, reserve: int) -> list[Allocation] | None:
    """First-fit, shortest-first finite allocation with a strictly positive residual."""
    remaining = sorted((length, index) for index, length in enumerate(lengths))
    out: list[Allocation] = []
    for _ in range(required):
        found = next(((length, index) for length, index in remaining if length > reserve), None)
        if found is None: return None
        remaining.remove(found)
        length, index = found
        out.append(Allocation(f"{stock_id}-{index + 1}", length, length - reserve, reserve))
    return out


def split_pitch_run(width: int, pitch: int, kerf: int, joint: int) -> list[int] | None:
    """Split a source width into legal pitch-multiple strip widths.

    Returns final strip widths.  Every internal saw boundary reserves kerf plus a
    fresh-face joint allowance on the child that needs it.
    """
    if width < pitch: return None
    count = width // pitch
    while count:
        usable = width - (count - 1) * (kerf + joint)
        if usable >= count * pitch:
            return [pitch] * count
        count -= 1
    return None
