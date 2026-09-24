# Problem specification

Status: agreed version-0 scope, recorded 2026-09-24. Implementation choices are identified separately from requirements. Changes to these boundaries should be explicit and reflected in the scope decision record.

## 1. General problem

Given a target bitmap T representing the desired visible pattern of a rectangular cutting board, construct an approximation using two wood species supplied as rectangular stock with fixed widths and thicknesses and arbitrary available length. The stock cross-sections may differ.

A feasible fabrication plan P must produce the required final dimensions within tolerance, use only permitted operations, and account for kerf, machining and finishing removal, dimensional variation, grain orientation, joint compatibility, and shop-specific handling limits.

The general objective is:

J(P) = λE E(T, Render(P)) + λC C(P) + λW W(P) + λG G(P) + λS S(P) + λR R(P) + λF F(P)

where E is pattern error, C cutting cost, W waste, G glue complexity, S setup complexity, R manufacturing difficulty/risk, and F finishing effort. Weights are nonnegative and terms must have documented, comparable scales. Alternatively, return trade-offs across these terms.

Version 0 deliberately solves only a restricted subset of feasible plans. It does not implement all seven weighted terms, search arbitrary operation sequences, or claim a globally optimal result.

## 2. Version-0 problem

Find an approximate library of at most Kmax strip-panel recipe families, assign one recipe and permitted orientation to each final row, generate the required stock breakdown and two-stage assembly operations, and retain useful independently validated trade-off plans.

The solver may alter the pattern to reuse recipes. Exact grid reproduction is a baseline, not a requirement.

### Supported operations

1. Crosscut source stock into manageable rough blanks.
2. Prepare blanks to compatible rectangular dimensions and a common strip thickness.
3. Rip longitudinal strips.
4. Arrange, glue, and flatten first-stage strip panels.
5. Crosscut panels into slices of a common nominal length.
6. Rotate slices to expose end grain; optionally reverse the visible left-to-right sequence through a valid rigid rotation.
7. Arrange whole slices as rows and perform the final glue-up.
8. Flatten using a supported method, trim, and finish.

Each final row is one intact slice. All finished visible grain is end grain. The orientation system must distinguish actual rigid rotations from image reflections.

### Explicit exclusions

- Angled or curved cuts; inlays and arbitrary polygons.
- Separating and rearranging individual cells after slicing.
- Sideways row offsets or joining slices end to end within one row.
- Additional glue-and-recut stages; borders and frames.
- Mixed exposed grain modes.
- More than two species; finite inventory and vendor purchasing optimization.
- Defect maps, color/figure matching, quantitative moisture or movement models.
- Automatic machine safety certification or structural joint analysis.
- General fabrication-program synthesis, learned search, and photorealistic rendering.

## 3. Inputs

### Target

- Binary bitmap or binary matrix with classes A and B.
- An explicitly selected mapping to the two species.
- A user-selected crop matching the final board aspect ratio.
- A frozen preprocessing specification if thresholding was needed.

Cropping, rotation, mirroring, and color swapping are manual preprocessing choices, not hidden solver freedoms. No automatic stretching or dithering in the first attempt. The target is interpreted as a piecewise-constant image over the finished physical rectangle.

### Board

- Finished width W, length L, and thickness H.
- Per-axis final dimensional tolerances.
- Final edge trim allowances on all four edges.
- Intended final top/bottom removal.
- Manufacturing dimension increment.

### Stock, independently for species A and B

- Positive measured rough width and thickness.
- Unlimited available longitudinal length.
- Required preparation allowances.
- Species identifier and optional display color.

Assumptions: rectangular, defect-free, suitably conditioned stock; longitudinal grain along source length; species suitable for the intended application. These assumptions must appear in plan metadata. The program does not establish their truth.

Unlimited length is a supply assumption, not permission to exceed workpiece-handling or machine limits. The result specifies finite rough stock segments and total required length by species.

### Shop and process profile

- Kerf by supported cutting operation.
- Minimum supported strip width and operation-specific workpiece dimensions.
- Maximum panel/workpiece dimensions and machine capacities.
- Required end reserves for repeated slicing.
- Preparation and flattening removal allowances.
- Supported final flattening method and its capacity.
- Declared dimensional variation bounds and machining assumptions.

No universal safe defaults are implied. The user must supply or explicitly accept the effective profile.

### Search settings

- Maximum recipe families Kmax.
- Bounded row and column counts.
- Search budget and reproducibility seed, if applicable.

Proposed initial software caps: 32 rows, 32 columns, 8 recipe families. These are computational bounds, not woodworking limits, and may change based on benchmarks.

## 4. Grid and recipes

All rows share nominal height h. All columns share nominal pitch p. Rectangular cells are allowed. Every recipe uses the same column grid. Edge trimming may leave partial cells, and both rendering and scoring must include that effect.

Cell pitch is conservatively constrained to be at least the configured minimum rip-strip width. Physical strips span integer numbers of columns and must fit their source stock width.

A visual recipe is a binary sequence of m cells. A physical realization is an ordered list of strips, each with species, width, thickness, and length. These are not interchangeable representations:

- Consecutive same-species cells may be merged into a run.
- A wide run may require multiple same-species physical strips.
- Same-species joints still count as physical joints, even when not visible in the binary render.

A recipe and its reversal may share one recipe family only when the supported physical transformation produces the requested result. Actual first-stage panel instances are tracked separately from recipe families.

## 5. Pattern error

Primary pattern error is normalized mismatched physical area:

E = area(target differs from final rendered surface) / (L × W).

For each retained cell region, let q be the fraction of target area labeled B. Assigning A contributes area × q; assigning B contributes area × (1 − q). Sum over retained regions and divide by final board area.

This handles target boundaries crossing cells and partial edge cells without first forcing the target onto a hard binary grid. The geometry of the final cropped assembly defines the integration regions.

Multiscale, topology, salience, and perceptual metrics are deferred. Display the final preview and difference view alongside numeric error.

## 6. Optimization and trade-offs

Explore recipe budgets from 1 through Kmax, subject to computational limits. Measure at least:

- Pattern error.
- Actual first-stage panel count.
- Physical glue-joint count, with first/final stage breakdown.
- Saw passes, with operation breakdown.
- Distinct nominal cutting settings, using a documented setting key.
- Rough stock volume consumed and length by species.

Report milling, kerf, trim, and offcut volumes separately. Report declared tolerance margins and constraint slack; do not convert them into an uncalibrated safety percentage.

Maintain a nondominated archive over explicitly documented metrics and offer representative alternatives. A solver may use internal scalar heuristics, but the result must expose raw measurements and the selection policy.

Claims must say “nondominated plans found,” not “the Pareto-optimal frontier,” unless proven. Setup count is a proxy until a schedule is explicitly modeled. Labor prices, glue consumption estimates, seven-weight controls, and universal total scores are not required.

## 7. Required outputs

A versioned canonical plan document contains:

- Input snapshot, units, assumptions, profile, and search metadata.
- Target placement and grid geometry.
- Recipe families, physical strip realizations, and row assignments.
- Rough stock segments and per-species requirements.
- Parts, dimensions, material/grain provenance, and operation dependencies.
- Explicit cuts, rotations, glue-ups, removal operations, and final trim.
- Material ledger and raw metrics.
- Validation results and precise result status.

Derived views include final-board preview, panel diagrams, stock cutting diagrams, and an operation list. These must derive from the plan, not a separate visual approximation.

## 8. Result semantics

- **Validated plan found:** replay passed under the recorded assumptions and supported model.
- **Infeasible within the supported model:** a demonstrated contradiction or exhaustive bounded proof is available; identify the scope of that proof.
- **No plan found within search limits:** no validated candidate was obtained within the bounded/heuristic search.
- **Invalid input:** malformed or contradictory input specification.

A timed-out or failed heuristic search does not prove infeasibility. A validated result is not an unconditional manufacturing guarantee or safety certification.
