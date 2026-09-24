# Implementation roadmap

Status: proposed execution plan, not a claim of implemented functionality.

Baseline: `5ae7bb4` (nominal replay prototype).

Updated: 2026-09-24.

## 1. Outcome and scope

Build a usable local program that turns a binary target into a small set of two-species end-grain cutting-board plans. Every presented candidate must have explicit stock, cuts, glue-ups, rotations, finishing, material accounting, and a replay-derived preview.

The next three milestones are:

1. **N1 — Complete the nominal fabrication foundation:** rough-stock modeling, required shop constraints, one realistic reference plan, and continuous integration.
2. **N2 — Compile an exact binary grid into a plan:** deterministic recipes, strip production, panel batching, and stock allocation.
3. **N3 — Approximate under a recipe budget:** merge/reassign recipes and return independently validated trade-offs.

The N-prefix distinguishes these next milestones from the original M1–M4 outline. The existing implementation is a partial original M1. N1 completes more of that foundation; N2 corresponds to the original M2; N3 covers the approximation portion of original M3. Bitmap import and the local UI follow separately.

### Scope that stays fixed

- Two species, each with one fixed rough cross-section and unlimited available length.
- Finite actual stock segments and bounded machine/workpiece capacities.
- Orthogonal cuts and two glue-up stages.
- Every final row is an intact slice from a first-stage panel.
- A uniform rectangular grid; rectangular cells are allowed.
- Reversal only through supported proper rotations.
- Final trimming affects the actual rendered and scored pattern.
- No individual pixel rearrangement, row splicing, sideways offsets, borders, or arbitrary extra glue-and-recut stages.
- Independent replay is authoritative; planner assertions are not.

### Validation boundary

N1–N3 remain **nominal-only** until the separate bounded-tolerance milestone is complete. Exact arithmetic is not machining accuracy. Required checks must not silently default to safe values or disappear from reports. Generated plans are not machine-operation safety certificates.

See [problem specification](problem-specification.md), [fabrication model](fabrication-model.md), and [scope decision](decisions/0001-version-zero-scope.md) for the governing requirements.

## 2. Current baseline

Implemented at the baseline commit:

- Python package and `cbdesign validate` CLI.
- Strict versioned JSON input and integer-micrometre geometry.
- Cuts, face removals, proper rotations, and ordered full-face glue-ups.
- Material/grain/source provenance and source partition checks.
- Per-species ledger, terminal dispositions, and retained finishing lineage.
- Some construction-template and optional shop-profile checks.
- Two tiny prepared-strip fixtures, generated reports, and SVG/PNG previews.
- 26 passing tests, including focused regressions and basic property tests.

Not yet complete:

- Rough-stock-to-strip reference workflow and preparation allowance checks.
- Minimum handling dimensions and enforced slicing reserves.
- Full grid/physical-recipe validation and source cross-section consistency.
- Automatic plan generation, approximation, bitmap import, and UI.
- Bounded machining uncertainty and physical shop verification.

The existing checkerboard and asymmetric examples are useful regression fixtures, not evidence of a complete rough-lumber workflow or shop readiness.

Two schema details need particular care in N1: current `Recipe.sequence` is checked against physical material regions, not uniform visual grid cells; and template metadata is described/defaulted as optional although current row-bijection validation requires it. Make these contracts explicit in the next schema rather than treating them as a ready-made grid API. Previously fixed terminal-accounting, row-bijection, capacity, preparation-declaration, and retained-finishing bugs are not being listed as current defects.

## 3. Architecture and implementation rules

Retain a modular Python package, not a service platform.

```text
Design request / target
    → grid and recipe decisions
    → strip demand and panel batches
    → finite stock allocation
    → explicit fabrication operations
    → independent replay and constraint validation
    → metrics and final surface
    → JSON / SVG / human-readable instructions
```

### Existing components to preserve

- `src/cbdesign/dimensions.py`: exact dimensions and increment checks.
- `src/cbdesign/geometry.py`: boxes and proper rotations.
- `src/cbdesign/models.py`: versioned plan schemas.
- `src/cbdesign/replay.py`: operation execution, material provenance, and current checks.
- `src/cbdesign/validation.py`: report status and coverage.
- `src/cbdesign/render_svg.py`: diagrams derived from replay.
- `src/cbdesign/cli.py`: CLI and safe output behavior.

Split `replay.py` by responsibility as the new work requires it: operation geometry, construction validation, profile checks, and ledger computation. Preserve behavior with tests before extracting code; do not undertake a speculative framework rewrite.

### New boundaries

- **Design request:** target, finished dimensions, stock types, shop profile, grid, and search options. Separate from executable `Plan`.
- **Planning:** recipe extraction, strip demand, batching, allocation, and operation emission.
- **Scoring:** image error, replay-derived fabrication metrics, and nondominated selection.
- **Rendering:** renderer consumes validated/replayed geometry, never a separate planner bitmap.

Suggested modules are named below, but file names are not an API commitment. Add modules when responsibility warrants them, not as empty scaffolding.

### Common contracts

- Exact integer geometry; reject unrepresentable manufacturing settings instead of rounding silently.
- No solver-generated authoritative volume, joint, or final-size totals.
- Deterministic identifiers, tie-breaks, and explicit seeds for randomized search.
- Schema and algorithm versions in saved outputs.
- Existing files are not overwritten except under explicit, tested CLI behavior.
- Every milestone updates documentation and includes runnable examples.
- Public results distinguish malformed input, invalid plan, proved bounded infeasibility, search exhaustion, and a validated incumbent.

## 4. N1 — Complete the nominal fabrication foundation

### Goal

Replay a board-sized hand-authored plan from two rough stock types through the supported operations, rejecting geometric and declared-profile violations. Establish the contract the generator will depend on.

### N1.1 — Freeze the next schema and input boundary

Add a documented next plan schema version rather than silently changing the meaning of `cbdesign-plan/v1`.

Define:

- Stock type per species: rough width/thickness, longitudinal grain, and preparation requirements.
- Finite source segment: stock-type reference, length, and source-boundary convention.
- Prepared strip: actual dimensions and preparation state derived through operations.
- Common pitch, column count, panel thickness, slice length, and row assignments.
- Physical strips separately from visible cells/runs and recipe families.
- Required profile values for generated-plan validation and explicit coverage for legacy v1 plans.

Keep existing v1 examples readable as legacy nominal/prepared-strip plans. Do not invent missing rough-stock data when loading them. Use explicit version dispatch or a documented migration only when all required values are supplied.

**Deliverables:** schema examples; migration/version policy; updated `docs/plan-format.md`; a short decision record for the stock and profile conventions.

### N1.2 — Model rough-stock preparation

Use existing cut and surface primitives where possible. A finite source root must include modeled separation kerf and any terminal reserve; an existing source boundary is distinct from a new cut.

Represent:

1. Source separation and end preparation.
2. Face-specific thickness removal to the shared prepared thickness.
3. Edge preparation and rip production.
4. Residual material and all preparation losses.

Choose and document which preparation operations establish usable mating faces, and how that state survives cuts and rotations. A bare `prepared_faces: true` claim must not substitute for the new schema's preparation provenance.

Reject conflicting rough cross-sections within a species, insufficient preparation allowance, incompatible thicknesses, missing losses, and double-counted removal.

**Deliverables:** operation/provenance checks and total/per-species accounting tests from rough roots.

### N1.3 — Enforce operation-specific shop constraints

Required generated-plan profiles must contain the applicable limits; no universal safe presets.

At minimum model:

- Minimum rip-strip width.
- Minimum input workpiece length for each supported cutting stage.
- Minimum slice thickness where applicable.
- Maximum workpiece dimensions and process capacity.
- Remaining-stock reserve for repeated slicing.
- Supported final flattening method.

Check limits in the operation's documented local frame, on the workpiece actually handled at that stage. Distinguish reusable stock pieces from removed dust/shavings; do not impose feed-size limits on every discarded geometric region. Validate the initial slicing workpiece and its successive remainders, not just the last terminal.

Distinguish a first-stage longitudinal strip from a final exposed cell. Do not reject an embedded cell merely because it would be too small to handle independently.

**Deliverables:** structured diagnostics with operation, part, bound, and measured value; tests immediately below/at/above each limit.

### N1.4 — Validate grid and construction semantics

The validator must reconstruct rather than trust these claims:

- All recipe strips have compatible length and prepared thickness.
- Strip widths are integer multiples of common pitch and fit the relevant source geometry.
- Physical same-species subdivisions remain distinct even when the visible run is merged.
- First-panel thickness maps to final row height; slice length maps to final thickness.
- Only full-width longitudinal panel slices form final rows.
- Every row assignment maps exactly once to the actual final assembly input.
- Recipe labels, reversal claims, and cell occupancy agree with replayed spatial boundaries.
- Final trim follows retained outputs, with explicit saw kerf and residuals.

Reject a post-panel side rip disguised as an intact row, not merely recuts performed after rotation. Check the permitted operation chain and cut axes between first glue and row rotation.

### N1.5 — Realistic reference, diagrams, and CI

Add one board-sized synthetic example using:

- Two species with different rough cross-sections.
- Explicit preparation and rip cuts.
- Two recipe families and more than one physical panel instance.
- Repeated and reversed rows.
- A same-species run assembled from multiple strips.
- Explicit slicing reserves, final flattening, and edge trim.

Select numerical dimensions after deriving the complete allowance chain. Label shop values illustrative; obtain human review before describing them as suitable operating limits.

Produce final-board, panel, and stock-breakdown diagrams with dimensions in readable millimetres, part IDs, species legend, grain direction, and clearly distinguished kerf/offcuts. Preserve exact values in JSON. Add a deterministic preview regeneration command and reference it from the README.

Add `.github/workflows/tests.yml` to install the package and run tests on Python 3.12 and 3.13. Include CLI smoke tests, package build/import checks, and deterministic fixture/report consistency checks. Do not compare PNG bytes across unrelated rendering environments.

### Critical files

Modify domain/schema/replay/validation/CLI/rendering modules above. Add focused modules such as `construction.py` or `shop_constraints.py` when extracting actual responsibilities. Add `examples/rough-stock-board.json`, focused tests, preview outputs, and the CI workflow.

### N1 acceptance gate

- Legacy fixtures still work with their narrower coverage clearly reported.
- New rough-stock fixture reconciles every source root and loss category exactly.
- All required limits and grid claims have valid and invalid tests.
- Missing required profile values cannot produce a fully profile-checked result.
- Diagrams are visually inspected; displayed dimensions match replay.
- CI passes and the CLI reproduces the checked-in example reports.
- Tolerance propagation and physical safety remain explicitly not evaluated.

## 5. N2 — Exact binary-grid-to-plan compiler

**Depends on:** N1 schema, preparation, grid validation, profile checks, and reference workflow.

### Goal

Replace hand-authored operations with a design request. Produce one deterministic feasible plan for a supplied binary matrix and explicit grid, or an honest diagnostic.

Proposed interface (not available yet):

```bash
cbdesign generate examples/designs/block-letter.json --output out/exact
```

### N2.1 — Define a design-request schema

Inputs include:

- Rectangular binary matrix and explicit A/B species mapping.
- Finished width/length/thickness and face-specific allowances.
- Two rough stock types and complete shop profile.
- Explicit row/column count implied by the matrix and manufacturing increment.

No crop search, bitmap decoding, approximation, or arbitrary variable cell boundaries.

For an untrimmed matrix request, matrix values describe the pre-trim grid; output must disclose the resulting edge cropping. Include that mapping in the request contract so “exact” never implies an unchanged bitmap after trim. Exact generation means exact reproduction of the specified grid geometry, not zero error against any later bitmap input.

Back-propagate dimensions using the documented equations. Reject input combinations that do not produce representable, source-compatible dimensions. Different feasible grids are a later bounded enumeration around this compiler, not hidden rounding inside it.

### N2.2 — Extract and realize recipes

- Extract row sequences and canonicalize under permitted reversal.
- Preserve original row order and orientation assignments.
- Run-length encode visible species sequences.
- Split wide runs into legal integer-cell physical strips.
- Try a bounded set of decompositions, preferring fewer joints with deterministic tie-breaks.

Do not confuse recipe families with actual panel glue-ups. Validate recipe identity against cell boundaries, not the number of physical material regions.

### N2.3 — Batch slices and allocate stock

For each recipe, enumerate panel lengths and slice counts within the shop profile. Include every separating cut and the required reserve.

Construct strip demand by species, width, prepared thickness, and required length. Allocate to finite source segments using rip patterns compatible with the supported preparation/cutting sequence. Start with a deterministic feasible method; reuse a real remnant only by emitting operations that consume it.

Use a small pattern enumeration or dynamic program where useful. Do not add general 2D nesting or CP-SAT until a measured bottleneck justifies it.

Unlimited source length removes purchasing scarcity, not handling limits or waste. Report exact allocated length/volume by species; do not claim minimum consumption.

### N2.4 — Emit and independently validate operations

Emit stock roots, preparation, rips, panel glues, slicing, rotations, final glue, and finishing. All generated candidates pass through the same replay validator as manually written plans.

Output:

- The executable plan and immutable design request.
- Validation and material reports.
- Board, stock, and panel diagrams.
- Operation list and raw fabrication metrics.
- Generator version and deterministic settings.

Never render an unvalidated planner layout as the achieved result.

### N2.5 — Diagnostics and reference corpus

Keep these outcomes separate:

- Invalid input.
- Demonstrably infeasible dimensions/constraints for the supplied model.
- Allocation/search limit reached without a plan.
- Nominally validated generated plan.

Preserve stage-specific diagnostics rather than returning only “no solution.” Only recommend a changed parameter when a concrete violated bound supports that suggestion.

Test checkerboards, stripes, a block letter, an asymmetric icon, multiple panels, wide runs, unequal stock dimensions, and near-limit cases. Compare tiny strip/batch subproblems with exhaustive enumeration. Assert geometry and objective bounds, not one incidental plan when alternatives are equivalent.

### Critical files

Add `design_models.py`, a `planning/` package with recipe/batching/allocation/emission responsibilities, generation CLI support, design fixtures, and integration/property tests. Reuse domain geometry and replay without making replay depend on planner internals.

### N2 acceptance gate

- A user supplies a binary matrix, not operation JSON.
- The corpus generates complete replay-valid plans deterministically.
- Generated cell pattern and row order match the requested mapping after documented trim.
- Stock and losses reconcile per species.
- Infeasibility claims are supported; heuristic failure is labeled unknown/search-limited.
- One command produces inspectable diagrams and operation reports.

## 6. N3 — Recipe-budget approximation and trade-offs

**Depends on:** N2 exact compiler and reliable replay-derived metrics.

### Goal

Find better fabrication/likeness trade-offs by intentionally sharing approximate recipes, rather than only lowering image resolution.

Proposed interface (not available yet):

```bash
cbdesign approximate examples/designs/block-letter.json \
  --max-recipes 4 --time-limit 30 --seed 0 --output out/alternatives
```

### N3.1 — Freeze target and metric semantics

Interpret the binary target as physical area on the finished board. For each retained cell region compute the target fraction occupied by species B. Assigning A incurs that B area; assigning B incurs the complement. Normalize total mismatch by finished surface area.

Use exact overlap arithmetic or a documented numerically bounded implementation; do not silently use nearest-neighbor sampling. Only retained post-trim area contributes. A matrix target can supply this piecewise-constant target without bitmap dependencies.

Store the frozen target mapping with the run. No solver-controlled crop, stretching, species swap, or image rotation.

### N3.2 — Implement bounded recipe search

For each recipe budget up to Kmax:

1. Initialize from exact target-row recipes and deterministic alternative groupings.
2. Canonicalize reversal-compatible families.
3. Assign each target row to a family and allowed orientation.
4. Recompute representative bits using area-weighted choices.
4a. Repair or reject physical strip realizations that violate the model.
5. Try merges, splits, replacements, and local bit changes.
6. Compile promising candidates through N2 and validate them.
7. Retain validated incumbents before continuing search.

Majority updates optimize only the additive image term for fixed assignments. Use actual compiled cost to assess manufacturing consequences; recipe count alone is not panel count or labor.

Bound candidate count, restarts, grid choices, and elapsed time. Cache deterministic recipe realizations/compilations by complete input keys, including shop and stock specifications. Fixed seed plus fixed evaluation budget is the reproducibility contract; wall-clock deadlines may yield different incumbent counts across machines.

### N3.3 — Enumerate physical grids conservatively

Begin with the fixed grid supported by N2. Then add an explicitly bounded enumeration of row/column counts using the fabrication equations, with the same frozen physical target.

Discard infeasible grids early; never stretch the target to fit them. Proposed initial caps remain 32 × 32 cells and 8 recipe families, subject to measured runtime. These are software limits, not a statement that all such plans are practical.

### N3.4 — Select understandable alternatives

Compute from expanded/replayed plans:

- Physical-area pattern error.
- First-stage panel/glue-up count.
- Physical joints, including same-species joints.
- Saw passes and documented distinct-setting keys.
- Consumed stock volume and length by species.
- Loss breakdown and available constraint margins.

Keep a bounded nondominated archive. Return distinct representatives such as best match, fewest glue-ups, least stock, and an intermediate compromise. State the archive dimensions and any selection/pruning rules.

No universal safety score, uncalibrated labor estimate, or claim of a global Pareto frontier. A time-limited run with valid incumbents should return them and identify the termination reason; no incumbents means no plan found, not infeasible.

### N3.5 — Benchmark usefulness

Compare exact generation and budgets of 1, 2, 4, and up to 8 recipes on:

- Checkerboard and stripes.
- Stepped diamond.
- Block letter.
- Asymmetric icon.
- Deliberately difficult unrelated-row target.

Record raw metrics, duration, evaluated/validated candidate counts, seed, and termination reason. Use hand-verified tiny optima to test scoring and search behavior. Do not require a heuristic to improve monotonically with extra wall-clock time unless its incumbent archive guarantees that property under the same objective.

### Critical files

Add target-area scoring, recipe search, metrics, and archive modules under appropriate `image/`, `planning/`, or `scoring/` packages. Extend CLI, request/run schemas, and comparison output. Keep optimizer data structures out of replay.

### N3 acceptance gate

- At least one nontrivial fixture shows reduced recipe/panel complexity with correctly measured increased image error.
- Every returned alternative independently validates.
- Tiny scoring and recipe instances match exhaustive reference calculations.
- Budget/termination status is accurate and reproducible under fixed work budgets.
- Alternatives are visibly meaningful, not duplicate plans with different IDs.
- Benchmarks show where the method is useful and where it fails.

## 7. Future work and release gates

### F1 — Conservative tolerance validation (required before dimensional-feasibility claims)

Can be designed alongside N1, but must not be implied by N1–N3 nominal success.

- Distinguish remove-by-amount from machine-to-target operations.
- Propagate conservative bounds through preparation, glue, slicing, rotation, and trim.
- Model accumulated row-height error and sufficient final-sizing allowance.
- Specify correlations for shared machine settings; do not invent independence.
- Return final dimension intervals, constraint margins, and explicit unsupported checks.
- Test cases where nominal geometry passes but the declared uncertainty makes the plan unacceptable.

Exit: plans labeled dimensionally validated satisfy the declared worst-case model. This still does not certify safe machine use or wood behavior.

### F2 — Bitmap input and a local interface (required for the intended usable product)

After the compiler/search contract is stable:

- Pillow-based image decoding with file-size/pixel-count limits.
- User-controlled crop, threshold, mapping, and frozen target preview.
- Local workflow for target → wood → board → shop → alternatives.
- Cancellation, progress, clear unsupported checks, and plan inspection.
- JSON project files first; add a database only for a demonstrated need.

Briefly evaluate existing viewers at this stage, as originally requested. Reuse only if they preserve plan-derived geometry, IDs, dimensions, and useful interactions. A generic image viewer is not a manufacturing validator. No external viewer research is required for N1–N3.

### F3 — Build documentation and physical pilot (required before shop-ready language)

- Dimensioned stock layouts and per-operation diagrams.
- Readable units, part labels, process assumptions, and printable PDF/CSV.
- Review with an experienced woodworker; revise ambiguous or impractical steps.
- Build selected boards and record actual dimensions, removals, material use, and deviations.
- Turn each discrepancy into a documented assumption or regression test.

Do not call the output shop-ready solely because the software test suite passes.

### F4 — Targeted optimization improvements (evidence-driven)

Only after profiling and benchmark comparison:

- Dynamic programming/CP-SAT for stock patterns or panel batching.
- More effective candidate initialization and bounded local search.
- Multi-scale or salience-aware scoring when area mismatch visibly misranks patterns.
- Variable row heights or additional fabrication templates, each with a separate scope decision.
- Finite inventory and cross-project remnant management with explicit consumption accounting.

Defer arbitrary fabrication synthesis, learned optimizers, defect maps, more species, hosted multi-user infrastructure, and purchasing catalogs until there is a specific validated need.

## 8. Delivery and verification discipline

### Recommended reviewable increments

1. N1 schema/profile decision and tests.
2. N1 rough preparation, grid/lineage checks, and realistic fixture.
3. N1 diagrams, CI, and acceptance review.
4. N2 design requests and recipe realization.
5. N2 batching/allocation/emission and end-to-end corpus.
6. N3 scoring and recipe search on a fixed grid.
7. N3 bounded grid enumeration, alternatives, and benchmark report.

No calendar estimate is promised before N1 resolves the fabrication contracts. Evaluate each increment against its acceptance gate rather than counting files or passing tests alone.

### Verification layers

- **Unit:** exact geometry, rotations, dimension chains, target-area integration.
- **Property:** conservation, provenance, deterministic mappings, and legal transformations.
- **Adversarial:** duplicate/missing assignments, wrong axes, forged metadata, misclassified losses, incompatible joins, skipped kerfs, and hidden capacity failures.
- **Integration:** actual CLI commands, complete report bundles, malformed input, safe overwrite behavior.
- **Visual:** inspect generated images and dimensions; retain golden reference geometry, not only image snapshots.
- **Benchmark:** tiny exhaustive comparisons and representative structured/difficult targets.
- **Physical:** F3 review/build evidence, tracked independently from software validation.

### Definition of done for every increment

- Executable example and regression tests cover the intended behavior.
- All returned claims match actual validation coverage.
- Canonical data, diagrams, ledger, and instructions agree.
- Documentation states limitations and schema changes.
- No new silent fallback, implicit safety default, or unsupported optimality claim.
- Changes are reviewable, tests pass, and publication is explicitly requested.

## 9. Immediate next action

Begin **N1.1**: write the next-schema/profile decision with concrete JSON examples and a hand-calculated rough-stock dimension chain. Review that contract before implementing dependent geometry checks. Then complete the realistic reference plan and its negative tests before starting N2 generation.
