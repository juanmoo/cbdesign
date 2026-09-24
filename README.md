# cbdesign

A manufacturing-constrained approximator for two-species, end-grain cutting-board patterns.

Given a binary target image, finished board dimensions, two lumber cross-sections, and explicit shop constraints, find a small set of reusable strip-panel recipes and expand them into executable fabrication plans.

**Status:** documentation-first repository. No application or solver has been implemented. The documents describe the agreed version-0 scope, not existing capabilities.

## Central idea

Make a first-stage panel by gluing longitudinal strips side by side. Crosscut that panel into slices, rotate them to expose end grain, and assemble the slices as rows of the final board. Repeated or reversed rows can share a panel recipe.

The solver may intentionally change part of the target pattern to reduce the number of recipes, glue-ups, cuts, or stock consumed. It optimizes a fabrication plan, not merely an image that someone must subsequently work out how to build.

## Version 0 at a glance

- Two species with fixed, potentially different rough widths and thicknesses.
- Unlimited available stock length; finite workpiece and machine capacities.
- One end-grain construction template with two glue-up stages.
- A uniform rectangular grid; rectangular cells are allowed.
- Every final row is one intact slice from one first-stage panel.
- A small reusable recipe library, with permitted row reversal.
- Explicit kerf, milling, trimming, provenance, and material accounting.
- Independent plan replay and validation.
- Area-based pattern error and multiple trade-off candidates.
- A local, viewer-independent program; JSON is the intended canonical plan format.

No arbitrary-angle cuts, individual pixel assembly, inlays, borders, finite inventory optimization, machine-learning model, or general fabrication-program synthesis in version 0.

## Documentation

| Document | Purpose |
| --- | --- |
| [Problem specification](docs/problem-specification.md) | Formal inputs, outputs, objectives, scope, and result semantics |
| [Fabrication model](docs/fabrication-model.md) | Axis mapping, dimensions, cuts, stock breakdown, tolerances, and accounting |
| [Implementation approach](docs/implementation-approach.md) | Proposed solver, domain boundaries, and delivery sequence |
| [Acceptance and validation](docs/acceptance-and-validation.md) | Reference cases, invariants, and release gates |
| [Scope decisions](docs/decisions/0001-version-zero-scope.md) | Why this restricted model was selected |

## Important dimensional fact

After a crosscut slice is rotated to expose end grain:

- Strip widths become visible cell/run widths.
- First-stage panel thickness becomes visible row height.
- Crosscut slice length becomes board thickness before final flattening.

Source stock thickness therefore constrains row height, **not directly the finished board thickness**. See the [axis mapping](docs/fabrication-model.md#1-coordinate-system).

## Validation is conditional

“Validated” means checked against the supported fabrication model, supplied stock assumptions, and selected shop constraints. It is not a safety certification, joint-strength analysis, wood-movement simulation, or guarantee of actual machining precision.

Shop limits must be supplied or explicitly accepted. Final end-grain flattening must use an explicitly supported method; the program must not silently prescribe ordinary thickness-planer use on end grain.

## Next milestone

Implement a thin end-to-end domain prototype: hand-authored recipe → explicit operations → independent replay → JSON and SVG output. Add approximation search only after the fabrication model works on reference cases.

There are currently no installation, build, or test commands. No license has been selected yet.
