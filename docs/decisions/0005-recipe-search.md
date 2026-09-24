# 0005 — Bounded recipe-grid search

## Status

Accepted for N3.

## Decision

Search is a bounded, deterministic approximation over binary recipe grids.  It
accepts a strict `DesignRequest`, an optional immutable `FrozenTarget`, and
`SearchSettings`; `search_design` returns a finite archive of plans that were
compiled and independently replayed successfully.

A **recipe family** is a row's binary sequence modulo reversal.  It is not a
panel, joint, source board, or a fabrication operation.  Rows may select either
orientation of a family to preserve the target's fixed physical left-to-right
layout.  The compiler remains authoritative for panels, source allocation, saw
operations, and joints.

The default grid is the request matrix's own shape, preserving its established
pitch and finite-stock compatibility. Explicit grids are limited to dimensions
2 through 32. Recipe budgets and `max_recipes` are limited to eight; the
search considers every budget from 1 through the requested limit. Work, time,
cancellation, and archive capacities are all bounded. Identical achieved
matrices are compiled once and emitted once per search invocation; no cache is
retained across requests.

The target spans the finished board rectangle exactly. Scoring uses
`target_occupancy` and exact `Fraction` retained-area mismatch. There is no
crop, rotation, species relabeling, or target-orientation optimization.  Search
can therefore compare candidates without silently changing the requested
physical target.

Candidates are non-dominated over mismatch, actual source volume, actual joint
count, and actual saw-cut count. Those fabrication metrics are measured from
the compiled plan and independent replay, not inferred from a recipe estimate.

## Consequences

- Results are reproducible and can return `exhausted`, `work_budget`,
  `time_limit`, or `cancelled`, including a valid empty archive.
- A search incumbent is nominally replay-valid only; it does not establish
  physical manufacturability, uncertainty tolerance, or joint certification.
- The deliberately small search is an approximation facility, not a claim of
  global optimality or a general panel/joint optimizer.
