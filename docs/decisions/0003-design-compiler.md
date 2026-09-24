# 0003: exact design compiler

## Decision

N2 introduces a strict `DesignRequest` separate from `PlanV2`.  The request holds a rectangular symbol matrix, symbol-to-species mapping, final dimensions, finite stock types, and a shop profile. `compile_design()` deterministically derives integer pitch, row height, prepared strip thickness, panel thickness, and slice length, then emits a fully replayable `PlanV2`.

The compiler uses only integer micrometres and the shop increment. It emits explicit source separation, end preparation, X/Z surfacing, rips, fresh-face jointing, first-stage panels, panel face preparation, slicing, deterministic alternate row reversal, final glue-up, final face removals, and X/Y trims.

## Allocation and failures

The implemented recipe groups equal-or-reversed visual rows into canonical row families. One physical panel is sliced for multiple row instances, bounded by each family's finite source-length capacity and terminal reserve; capacity overflows split deterministically into more panels. Allocation remains conservative within a panel: it assigns one finite source segment to each whole-cell strip and intentionally does not claim multi-strip source packing. It demands a positive terminal separation reserve and reports `allocation_failed` only for this deterministic allocation, not as a proof of global infeasibility. All generated output is independently passed through the existing exact replay engine before being returned.

## Scope

This keeps the existing CLI and validator unchanged. The request model is intentionally not a hand-authored plan dialect: `model_validate` accepts input and generated plans use `PlanV2.model_validate` / `model_dump` conventions.
