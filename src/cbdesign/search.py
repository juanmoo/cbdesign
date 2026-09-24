"""Bounded deterministic N3 search over binary end-grain recipe grids.

This is intentionally a recipe search, not a panel/joint optimizer.  A recipe is
one canonical row pattern (a pattern and its reversal are one family); compiled
plans still contain their own panels, glue joints, source allocation, and saw
operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from time import monotonic
from typing import Any, Callable, Sequence

from .compiler import CompileResult, compile_design
from .design import DesignRequest
from .metrics import plan_metrics
from .replay import ReplayError, replay
from .target import FrozenTarget, target_occupancy


CancelCallback = Callable[[], bool]
ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class SearchSettings:
    """Finite search limits.  ``grid_dimensions`` is an optional explicit grid list."""

    recipe_budget: int = 4
    max_recipes: int = 8
    grid_dimensions: tuple[tuple[int, int], ...] | None = None
    work_budget: int = 96
    time_limit_seconds: float | None = None
    archive_limit: int = 12
    seed: int = 0

    def __post_init__(self) -> None:
        for name, value, low, high in (
            ("recipe_budget", self.recipe_budget, 1, 8),
            ("max_recipes", self.max_recipes, 1, 8),
            ("work_budget", self.work_budget, 1, 100_000),
            ("archive_limit", self.archive_limit, 1, 256),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"{name} must be an integer from {low} through {high}")
        if self.recipe_budget > self.max_recipes:
            raise ValueError("recipe_budget cannot exceed max_recipes")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an integer")
        if self.time_limit_seconds is not None and (isinstance(self.time_limit_seconds, bool) or self.time_limit_seconds <= 0):
            raise ValueError("time_limit_seconds must be positive when supplied")
        if self.grid_dimensions is not None:
            grids = tuple(tuple(item) for item in self.grid_dimensions)
            if not grids:
                raise ValueError("grid_dimensions must not be empty")
            for rows, columns in grids:
                if any(isinstance(value, bool) or not isinstance(value, int) or not 2 <= value <= 32 for value in (rows, columns)):
                    raise ValueError("explicit grid dimensions must be integers from 2 through 32")
            object.__setattr__(self, "grid_dimensions", grids)


@dataclass(frozen=True)
class SearchCandidate:
    label: str
    request: DesignRequest
    compile_result: CompileResult
    score: Fraction
    mismatch_area: Fraction
    target_area: Fraction
    recipes: tuple[tuple[int, ...], ...]
    recipe_families: int
    grid: tuple[int, int]
    metrics: dict[str, Any]

    @property
    def plan(self):
        return self.compile_result.plan


@dataclass(frozen=True)
class SearchResult:
    candidates: tuple[SearchCandidate, ...]
    attempted: int
    compiled: int
    rejected: int
    termination: str
    settings: SearchSettings
    target: FrozenTarget

    @property
    def complete(self) -> bool:
        return self.termination == "exhausted"


def _target_for_request(request: DesignRequest) -> FrozenTarget:
    symbols = tuple(sorted(request.species))
    if len(symbols) != 2:
        raise ValueError("search supports exactly two matrix symbols")
    return FrozenTarget(tuple(tuple(int(cell == symbols[1]) for cell in row) for row in request.matrix))


def _canonical(bits: tuple[int, ...]) -> tuple[int, ...]:
    return min(bits, bits[::-1])


def _row_distance(bits: tuple[int, ...], occupancies: Sequence[Fraction], area: Fraction) -> Fraction:
    return sum((abs(Fraction(bit) - occupancy) * area for bit, occupancy in zip(bits, occupancies)), Fraction(0))


def _family_error(families: Sequence[tuple[int, ...]], occupancies: tuple[tuple[Fraction, ...], ...], area: Fraction) -> Fraction:
    return sum((min(_row_distance(oriented, weights, area) for family in families for oriented in (family, family[::-1])) for weights in occupancies), Fraction(0))


def _representatives(rows: tuple[tuple[int, ...], ...], occupancies: tuple[tuple[Fraction, ...], ...], count: int, area: Fraction) -> tuple[tuple[int, ...], ...]:
    """Choose deterministic weighted representative recipe families.

    The first family is a weighted medoid, not a lexicographic row. Each later
    family gives the best whole-target error reduction; this makes a one-recipe
    silhouette meaningful and produces a bounded quality/complexity trade-off.
    """
    unique = tuple(sorted({_canonical(row) for row in rows}))
    selected = [min(unique, key=lambda item: (_family_error((item,), occupancies, area), item))]
    while len(selected) < min(count, len(unique)):
        selected.append(min(
            (item for item in unique if item not in selected),
            key=lambda item: (_family_error((*selected, item), occupancies, area), item),
        ))
    return tuple(selected)


def _matrix_for_grid(target: FrozenTarget, rows: int, columns: int, budget: int) -> tuple[tuple[int, ...], tuple[tuple[int, ...], ...], Fraction]:
    occupancy = target_occupancy(target, rows, columns)
    binary = tuple(tuple(int(value >= Fraction(1, 2)) for value in row) for row in occupancy)
    area = Fraction(1, rows * columns)
    # Families are canonical under reversal.  The actual chosen orientation is the
    # lower mismatch one, preserving a target's physical left-to-right position.
    families = _representatives(binary, occupancy, budget, area)
    output = []
    for actual, weights in zip(binary, occupancy):
        choices = []
        for family in families:
            for oriented in {family, family[::-1]}:
                choices.append((_row_distance(oriented, weights, area), oriented))
        output.append(min(choices, key=lambda item: (item[0], item[1]))[1])
    return tuple(output), families, area


def _score(matrix: Sequence[Sequence[int]], occupancy: Sequence[Sequence[Fraction]], cell_area: Fraction) -> Fraction:
    """Score an abstract grid; production candidates use ``_replay_score``."""
    return sum((abs(Fraction(bit) - wanted) * cell_area for row, wanted_row in zip(matrix, occupancy) for bit, wanted in zip(row, wanted_row)), Fraction(0))


def _target_one_runs(target: FrozenTarget) -> tuple[tuple[tuple[int, int], ...], ...]:
    """Compress 1-valued target pixels into horizontal half-open runs."""
    runs = []
    for row in target.rows:
        row_runs = []
        start = None
        for index, value in enumerate((*row, 0)):
            if value and start is None:
                start = index
            elif not value and start is not None:
                row_runs.append((start, index))
                start = None
        runs.append(tuple(row_runs))
    return tuple(runs)


def _replay_score(result: CompileResult, target: FrozenTarget, one_species: str) -> tuple[Fraction, Fraction, Fraction]:
    """Return normalized mismatch, physical mismatch area, and board area.

    Regions are final replay geometry after rotation and trimming, so the score
    observes the compiler's actual orientation and retained physical rectangle.
    """
    assert result.replay is not None
    terminal = result.replay.parts[result.replay.terminal]
    width, height = terminal.size[:2]
    board_area = Fraction(width * height)
    target_one_area = board_area * sum(sum(row) for row in target.rows) / (target.width * target.height)
    actual_one_area = Fraction(0)
    overlap_one_area = Fraction(0)
    runs = _target_one_runs(target)
    for region in terminal.regions:
        if region.species != one_species:
            continue
        left, top = region.current.origin[:2]
        region_width, region_height = region.current.size[:2]
        right, bottom = left + region_width, top + region_height
        actual_one_area += region_width * region_height
        # Target pixel bounds are fixed partitions of the finished rectangle.
        first_y = max(0, (top * target.height) // height)
        last_y = min(target.height - 1, ((bottom * target.height - 1) // height))
        first_x = max(0, (left * target.width) // width)
        last_x = min(target.width - 1, ((right * target.width - 1) // width))
        for pixel_y in range(first_y, last_y + 1):
            pixel_top = Fraction(pixel_y * height, target.height)
            pixel_bottom = Fraction((pixel_y + 1) * height, target.height)
            overlap_y = max(Fraction(0), min(bottom, pixel_bottom) - max(top, pixel_top))
            if not overlap_y:
                continue
            for run_start, run_end in runs[pixel_y]:
                if run_end <= first_x or run_start > last_x:
                    continue
                start, end = max(run_start, first_x), min(run_end - 1, last_x)
                for pixel_x in range(start, end + 1):
                    pixel_left = Fraction(pixel_x * width, target.width)
                    pixel_right = Fraction((pixel_x + 1) * width, target.width)
                    overlap_x = max(Fraction(0), min(right, pixel_right) - max(left, pixel_left))
                    overlap_one_area += overlap_x * overlap_y
    mismatch = actual_one_area + target_one_area - 2 * overlap_one_area
    return mismatch / board_area, mismatch, board_area


def _nondominated(items: list[SearchCandidate], limit: int) -> tuple[SearchCandidate, ...]:
    # Better mismatch, then fewer physical sources/joints/saw cuts.  A retained
    # candidate must be non-dominated on all measured axes.
    def vector(item: SearchCandidate) -> tuple[Any, ...]:
        return (item.score, item.metrics["source_volume_um3"], item.metrics["joint_count"], item.metrics["saw_cuts"])
    kept = [
        item for item in items
        if not any(
            all(left <= right for left, right in zip(vector(other), vector(item)))
            and any(left < right for left, right in zip(vector(other), vector(item)))
            for other in items
        )
    ]
    kept.sort(key=lambda item: (vector(item), item.label))
    return tuple(kept[:limit])


def search_design(
    request: DesignRequest | dict[str, Any],
    target: FrozenTarget | None = None,
    settings: SearchSettings | None = None,
    *,
    cancel: CancelCallback | None = None,
    progress: ProgressCallback | None = None,
) -> SearchResult:
    """Search a finite grid/recipe space and return replay-validated incumbents.

    Target physical bounds are always the immutable finished rectangle.  The score
    is exact retained-area mismatch, so this routine never crops, reorients,
    chooses species labels, or otherwise optimizes the target itself.
    """
    req = request if isinstance(request, DesignRequest) else DesignRequest.model_validate(request)
    target = target or _target_for_request(req)
    settings = settings or SearchSettings()
    symbols = tuple(sorted(req.species))
    if len(symbols) != 2:
        raise ValueError("search supports exactly two matrix symbols")
    # A default search preserves the request's established pitch/grid.  This
    # avoids generating coarser grids whose pitch can exceed finite stock width;
    # callers requesting approximation alternatives supply explicit dimensions.
    grids = settings.grid_dimensions or ((len(req.matrix), len(req.matrix[0])),)
    # Search every bounded budget, not merely powers of two, so callers can make
    # a genuine recipe-complexity choice.
    budgets = tuple(range(1, settings.recipe_budget + 1))
    work = compiled = rejected = 0
    candidates: list[SearchCandidate] = []
    # This cache is intentionally per invocation: it avoids recompiling matrices
    # repeated by different budgets without retaining inputs across requests.
    compiled_matrices: dict[tuple[tuple[str, ...], ...], tuple[CompileResult, dict[str, Any]] | None] = {}
    emitted_matrices: set[tuple[tuple[str, ...], ...]] = set()
    started = monotonic()
    termination = "exhausted"
    for rows, columns in grids:
        for budget in budgets:
            if work >= settings.work_budget:
                termination = "work_budget"; break
            if cancel is not None and cancel():
                termination = "cancelled"; break
            if settings.time_limit_seconds is not None and monotonic() - started >= settings.time_limit_seconds:
                termination = "time_limit"; break
            matrix, families, area = _matrix_for_grid(target, rows, columns, budget)
            occupancy = target_occupancy(target, rows, columns)
            named = [[symbols[value] for value in row] for row in matrix]
            # Revalidation makes a search-generated model copy follow the same
            # strict request boundary as externally supplied data.
            candidate_request = DesignRequest.model_validate(req.model_dump() | {"matrix": named})
            matrix_key = tuple(tuple(row) for row in named)
            work += 1
            cached = compiled_matrices.get(matrix_key, "missing")
            if cached == "missing":
                result = compile_design(candidate_request)
                if result.plan is None or result.replay is None:
                    compiled_matrices[matrix_key] = None
                else:
                    try:
                        independent = replay(result.plan)
                        compiled_matrices[matrix_key] = (result, plan_metrics(result.plan, independent))
                    except ReplayError:
                        compiled_matrices[matrix_key] = None
                cached = compiled_matrices[matrix_key]
            if cached is None:
                rejected += 1
            elif matrix_key not in emitted_matrices:
                result, measured = cached
                compiled += 1
                score, mismatch_area, target_area = _replay_score(result, target, req.species[symbols[1]])
                label = f"{rows}x{columns} · " + (f"{len(families)} recipe family" if len(families) == 1 else f"{len(families)} recipe families")
                candidates.append(SearchCandidate(label, candidate_request, result, score, mismatch_area, target_area, families, len(families), (rows, columns), measured))
                emitted_matrices.add(matrix_key)
            if progress is not None:
                progress({"attempted": work, "compiled": compiled, "rejected": rejected, "grid": (rows, columns), "recipe_budget": budget})
        if termination != "exhausted":
            break
    return SearchResult(_nondominated(candidates, settings.archive_limit), work, compiled, rejected, termination, settings, target)
