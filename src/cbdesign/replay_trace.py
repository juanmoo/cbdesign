"""Immutable, bounded records captured by :func:`cbdesign.replay.replay`.

The records intentionally retain the authoritative frozen ``Part`` objects rather
than serialising a copy of the inventory for each operation.
"""
from __future__ import annotations
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from .geometry import Box
    from .replay import Part


class TraceLimitError(ValueError):
    """The complete replay cannot be represented within configured limits."""


# Deliberately conservative; callers may lower these for untrusted exports.
MAX_TRACE_OPERATIONS = 2_000
MAX_TRACE_REGIONS = 100_000


@dataclass(frozen=True)
class TraceStep:
    index: int
    operation_id: str
    kind: str
    inputs: tuple["Part", ...]
    outputs: tuple["Part", ...]
    input_ids: tuple[str, ...]
    output_ids: tuple[str, ...]
    # Geometry is in the input coordinate system, and is absent where inapplicable.
    cut_boxes: tuple["Box", "Box", "Box"] | None = None  # retained, kerf, remainder
    surface_boxes: tuple["Box", "Box"] | None = None       # kept, removed
    rotation_perm: tuple[int, int, int] | None = None
    rotation_sign: tuple[int, int, int] | None = None
    glue_offsets: tuple[int, ...] = ()
    axis: int | None = None
    retained_side: str | None = None


@dataclass(frozen=True)
class ReplayTrace:
    roots: tuple["Part", ...]
    steps: tuple[TraceStep, ...]
    producers: Mapping[str, int]
    consumers: Mapping[str, int]
    terminal: "Part"


def require_operation_budget(operation_count: int) -> None:
    """Fail before replay allocates trace history."""
    if operation_count > MAX_TRACE_OPERATIONS:
        raise TraceLimitError(f"replay trace has {operation_count} operations; limit is {MAX_TRACE_OPERATIONS}")


def require_region_budget(recorded_regions: int, parts) -> int:
    """Check a candidate snapshot before retaining its immutable references."""
    next_total = recorded_regions + sum(len(part.regions) for part in parts)
    if next_total > MAX_TRACE_REGIONS:
        raise TraceLimitError(f"replay trace has {next_total} recorded regions; limit is {MAX_TRACE_REGIONS}")
    return next_total


def build_trace(roots, steps, terminal) -> ReplayTrace:
    require_operation_budget(len(steps))
    regions = sum(len(p.regions) for p in roots)
    for step in steps:
        regions = require_region_budget(regions, (*step.inputs, *step.outputs))
    producers: dict[str, int] = {}
    consumers: dict[str, int] = {}
    for step in steps:
        for part_id in step.output_ids:
            producers[part_id] = step.index
        for part_id in step.input_ids:
            consumers[part_id] = step.index
    return ReplayTrace(tuple(roots), tuple(steps), MappingProxyType(producers), MappingProxyType(consumers), terminal)
