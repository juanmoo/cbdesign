# Decision 0001: Constrain version 0 to reusable end-grain row recipes

- Status: accepted scope; implementation details remain proposed where marked.
- Date: 2026-09-24

## Context

The original problem permits a broad family of cutting, rotation, rearrangement, gluing, and recutting plans. General inverse geometry and fabrication-program synthesis would combine image approximation, stock cutting, grain compatibility, handling constraints, assembly sequencing, and multiobjective optimization into a very large search space.

The immediate goal is a usable program, not a general optimality result. A restricted construction family must still allow meaningful image-versus-fabrication trade-offs.

## Decision

Use a two-stage end-grain construction: longitudinal strip-panel glue-ups are sliced, rotated, and assembled as intact final rows. Search over a uniform rectangular grid and a small reusable library of row recipes, allowing valid row reversal.

Stock consists of two fixed rough cross-sections with unlimited available length. The planner instantiates finite stock segments and respects shop capacities. Approximation occurs by changing row recipes and sharing them, rather than only downsampling an image and manufacturing it exactly.

Keep explicit operations and an independent replay validator as core requirements. Use physical-area image error and raw fabrication metrics. Return useful nondominated candidates found by the search, without claiming a global Pareto frontier.

Develop a local, viewer-independent program. JSON plans are canonical; visualization is derived and may later reuse an existing tool if convenient.

## Alternatives deferred

- General geometry DSL and arbitrary operation synthesis: too broad to validate and optimize initially.
- Edge-grain stripes only: useful as a geometry exercise, but too restrictive for the intended bitmap approximation.
- Individually cut pixel blocks: permits complex images but undermines manageable fabrication and safe handling assumptions.
- Finite stock inventory: useful later, but not required by the arbitrary-length input model.
- Seven weighted cost controls: premature before metrics and shop effort estimates are calibrated.
- Neural search, MCTS, or differentiable rendering: unnecessary for the first structured recipe problem.
- Hosted multi-user infrastructure: unrelated to proving plan usefulness.

## Consequences

- Some feasible boards and attractive patterns cannot be represented in version 0.
- Source thickness constrains visible row height; slice length controls pre-finish board thickness.
- Recipe count and actual panel count are separate metrics.
- Stock-width limits may create multiple physical strips inside one visible run.
- The solver may be heuristic, but every displayed feasible plan must pass independent replay.
- “No plan found” is not equivalent to infeasibility.
- Physical review remains necessary before outputs are described as shop-ready.

## Revisit when

The reference corpus and physical pilot show a specific limitation worth addressing, such as variable row heights, richer panel construction, finite inventories, or a more perceptual image metric. Additions should be explicit scope changes rather than silent expansions inside the solver.
