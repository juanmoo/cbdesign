# Software completion status

Updated 2026-09-24. This is an implemented local software release with explicitly bounded optimization and physical exclusions—not a claim that every original roadmap gate is complete.

## Published checkpoints

- N1: `a982b94`; 99 baseline tests. [Python 3.12/3.13 CI](https://github.com/juanmoo/cbdesign/actions/runs/35957916069) passed.
- End-to-end compiler/search/workbench: `b260eef`. [Python 3.12/3.13 CI](https://github.com/juanmoo/cbdesign/actions/runs/35959985903) passed, including build and real validate/generate/search commands.
- Final gallery/verification changes follow on branch `software-completion`.

## Implemented and verified

- **N2:** strict versioned requests, explicit maximum-edge trims, exact rectangular grid sizing, finite inventory consumption, canonical reversal-family panel batching, and independent PlanV2 replay. One-strip panel and finite-depletion regressions included.
- **N3:** deterministic bounded recipe budgets and explicit alternative grids; exact post-trim physical mismatch; deduplicated nondominated alternatives; per-call compile cache; cancellation and progress. Metrics use physical replay operations, joints, material losses and observed dimensions.
- **Targets/gallery:** bounded PNG decoding and immutable targets; eight common/unusual examples. All eight exact compiles pass. K=1/2/4/8 searches retain actual successes, failures, runtime and termination in raw metrics. All measured gallery searches completed with zero rejected candidates.
- **F1:** separate digest-bound declarations, named affine Fraction propagation, shared-setting correlation, all-realizations glue equality, positivity/capacity/material guards and final intervals. Nonzero accepted examples and endpoint/negative regressions exist. Unsupported/malformed input cannot receive a dimensional-valid label.
- **F2:** loopback-only HTTP server with Host/Origin checks, bounded requests/work, editable illustrative stock/dimensions, PNG upload, project save/load, progress/cancel, actual board/difference SVGs and ZIP downloads.
- **F3:** common deterministic JSON/SVG/CSV/PDF reports, plus gallery PNGs and a mouse report. PDF table and representative pages visually inspected; physical diagrams remain distinct from target pixels.
- **Local tests:** 148 passing before final publication, including an independent partial-cell physical-area oracle. Compiler tests deliberately exercise invalid model copies and emit Pydantic serializer warnings.
- **Actual runtime:** CLI demo/generate/search and installed-wheel generation pass. Chromium mouse PNG upload → four alternatives → nominal-valid ZIP → project/PNG save/reload passes. Cancellation preserves a validated incumbent; invalid dimensions show a diagnostic. No browser JS errors and no horizontal overflow at 390px in inspected run.

## Measured example

For the fixed 64×64 mouse target on a 12×12 construction grid, selected mismatch is 19.78% (K=1), 9.42% (K=2), 5.58% (K=4), and 4.80% (K=8). The browser K≤4 run compares 24–60 source segments and 110–254 saw passes. These deliberately conservative material numbers are not a recommended purchasing list.

## Remaining software limitations / uncompleted roadmap gates

- **Allocation:** one source per whole-cell strip. No multi-strip source packing, width-run combination, purchasing optimizer, or automatic offcut reuse. Allocation failure is not a proof of infeasibility. Full exhaustive allocation/batching optimality comparison is not delivered.
- **Search:** weighted medoid-style family selection and reassignment, not the full proposed merge/local-bit optimization. Seed is recorded but the current deterministic heuristic does not randomize. No cross-request persistent cache or global optimality proof. Intermediate budgets can yield nonmonotonic individual proposals.
- **Target fit:** exact requests describe the pre-trim grid. Fixed-finished-rectangle targets can therefore have substantial mismatch even for a regular checkerboard. Search scoring is exact, but the proposal heuristic is not fully trim-aware.
- **UI:** browser search currently uses a fixed 12×12 construction grid, with editable target sampling dimensions; alternate construction grids and K up to 8 are exposed through CLI/library. Uploaded targets use default threshold/crop choices in the UI (explicit controls are library/CLI-level). Full advanced shop profile editing and uncertainty-sidecar authoring are JSON/library workflows.
- **Work limits:** cancellation/time checks are cooperative between candidates, not hard interruption inside one compile/replay.
- **Exports:** printable reports are text/tables, not detailed per-operation geometry sheets. The conservative mouse plan produces a long operation report. No external viewer library was added: existing replay-derived SVGs preserve authoritative IDs and geometry without another scene model.
- **Uncertainty:** supported dimensional process assumptions only; no guarantee of real process capability, required physical preparation quality, statistical yield, or wood stability. Zero-width helper is a format demonstration, not measured shop data.

## Non-software gates

Physical expert review, fabrication/measurement, machine/process safety, joint-strength certification, wood movement, bow/twist/cup, clamping and food-contact suitability remain outstanding. No result is shop-ready merely because nominal or supported dimensional checks pass.
