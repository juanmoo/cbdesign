# Implementation approach

Status: M1 executable fabrication-model prototype is implemented: strict JSON schema, exact nominal replay, provenance/ledger checks, CLI reports, SVG views, hand-authored fixtures, and regression tests. This document retains the planned architecture for later milestones; M2–M4 and optimization are not implemented or benchmarked.

## 1. Build a thin end-to-end system

Start with Python, exact dimension arithmetic, typed domain objects, JSON, and SVG. Add a local browser interface after a valid end-to-end plan can be generated. Do not build hosting infrastructure first.

Proposed dependencies when implementation starts:

- NumPy and Pillow for target processing.
- Pydantic or equivalent typed serialization/validation.
- pytest and Hypothesis for tests.
- OR-Tools only after a concrete allocation/search bottleneck justifies it.
- FastAPI and a small React interface later, if appropriate.

No database, queue, cloud storage, learned model, general geometric DSL, or viewer dependency is required for the first technical milestone. Do not add unused dependencies or empty framework scaffolding in advance.

## 2. Intended boundaries

- **Domain:** dimensions, stock, mixed-material parts, orientations, operations, recipes, plans, and ledgers.
- **Image:** frozen preprocessing, physical target placement, and cell-area integration.
- **Planning:** feasible grids, recipe search, strip decomposition, panel batching, and stock allocation.
- **Validation:** independent operation replay and invariant checks.
- **Rendering:** final board, panel, stock, and operation diagrams derived from canonical plans.
- **Interface:** CLI first; local browser adapter later.

Keep the domain independent of API frameworks, persistence, OR-Tools, and visualization libraries.

## 3. Search pipeline

### A. Enumerate feasible physical grids

Enumerate bounded integer row/column counts. Derive panel thickness, strip thickness, pitch, and slice thickness from the fabrication equations. Reject unrepresentable dimensions and violations of stock or shop constraints.

Integrate the frozen binary target over each cell's retained physical area. Preserve fractional occupancy rather than thresholding away information prematurely.

### B. Construct an exact-grid baseline

Choose the minimum-area-error class per cell independently, then extract row recipes and reversal equivalences. This is the exact reproduction of that selected binary grid, not necessarily zero error against the original bitmap.

If recipe demand exceeds Kmax, retain it as an internal comparison, not a compliant final result. Physical feasibility still requires strip realization, batching, and full replay.

### C. Approximate through recipe reuse

Use deterministic multi-start local search over recipe libraries and row assignments:

- Merge similar recipe families.
- Assign rows to recipes with allowed reversal.
- Recompute representatives using physical-area-weighted binary choices.
- Try bit changes, recipe replacement, or splits.
- Retain candidates across recipe budgets.

For fixed assignments and orientation, weighted majority is an image-only representative. It is not automatically optimal once joint, strip, or stock costs are included. Re-evaluate actual manufacturing implications for promising candidates.

Canonicalize reversal-equivalent recipes and deduplicate candidates. Fix seeds and tie-break rules for reproducibility. Avoid premature claims of global optimality.

### D. Realize recipes physically

Split same-species runs into legal integer-cell strip widths. Enumerate a bounded set of decompositions. Different decompositions may trade joint count against stock use.

Batch slice demand into finite first-stage panels with explicit reserves and cuts. Allocate strip demand to finite rough stock segments using a deterministic feasible allocator initially. All stock use and losses are computed from the resulting plan.

Greedy allocation is acceptable initially, but its utilization is a property of the found plan, not an optimum or proof of impossibility. Introduce dynamic programming or CP-SAT after measuring where it helps.

### E. Expand, replay, and select

Generate the operation graph, validate independently, render final trimmed geometry, and compute raw metrics from the replayed plan. Retain a bounded nondominated archive and choose distinct representative results.

Only validated candidates may appear as feasible. Preserve the distinction between proved model infeasibility and search exhaustion.

## 4. Delivery milestones

### M1 — Executable fabrication model

- Define serialization and exact dimensions.
- Represent a hand-authored plan and its physical transforms.
- Replay cuts, glue-ups, rotation, removal, and trim.
- Reconcile total and per-species volume.
- Export JSON plus basic final-board/panel SVGs.

Exit: checkerboard and asymmetric reference plans validate; intentionally corrupted variants fail.

### M2 — Deterministic plan generation

- Accept a binary matrix and physical input specification.
- Enumerate feasible grids or accept an explicit feasible grid for testing.
- Generate exact recipes, strip decompositions, panel batches, and stock segments.
- Produce a cut/assembly list with stable part identifiers.

Exit: the exact-grid reference corpus produces complete validated plans without hand-editing operations.

### M3 — Approximation and usable local interface

- Implement bounded recipe-library search.
- Compare recipe budgets and raw metrics.
- Add bitmap threshold/crop preview and input forms.
- Display plan, difference view, and clear failure reasons.

Exit: a user can turn a simple bitmap into multiple complete plans without editing JSON.

### M4 — Documentation and physical pilot

- Improve dimensioned diagrams and printable output.
- Review a generated plan with an experienced woodworker.
- Build at least one reference board and compare predicted dimensions and material use.
- Correct model or instruction ambiguities before calling outputs shop-ready.

## 5. Decisions to resolve before coding the relevant layer

These details are not yet frozen; use focused decisions rather than reopening the whole scope:

- Exact dimension unit/increment representation and handling of imperial fractions.
- Versioned JSON schema and proper-rotation representation.
- Shop-profile fields, operation-specific limits, and tolerance-bound propagation.
- Source segment crosscut accounting convention, including initial boundary and trim handling.
- Supported finishing process profiles and their assumptions.
- Rip-layout allocation heuristic and batching tie-break rules.
- Precise metric keys for distinct settings and nondominated archive limits.
- Deterministic approximation initializations and search budget defaults.

A brief search for existing viewers may occur later. Reuse is worthwhile only if the viewer can consume plan-derived geometry and preserve part identity, dimensions, and operations. It must not become the authority on manufacturing feasibility.

## 6. Benchmarking

Compare exact-grid reproduction and small recipe budgets on checkerboards, stripes, stepped diamonds, block letters, asymmetric icons, and unrelated-row patterns. Measure error, recipes, panel instances, cuts, joints, stock consumed, search time, and validator outcome.

The key early question is whether a small recipe library preserves useful visual structure while materially simplifying fabrication. Infrastructure and advanced optimization should follow evidence from that experiment.
