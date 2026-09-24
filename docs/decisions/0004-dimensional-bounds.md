# Decision 0004: dimensional bounds sidecar

Status: accepted for F1. This is a conservative, opt-in dimensional feasibility check. It is separate from the nominal PlanV2 contract and does not alter the nominal ledger, replay result, or safety/strength claims.

## Contract

`validate_uncertainty(plan, declaration) -> dict` accepts only a PlanV2 and a sidecar with `version: "cbdesign-uncertainty/v1"` and `plan_digest`, a SHA-256 digest of the canonical plan JSON. A sidecar is invalid when the plan changes. There are no implicit zero bounds.

Every named item in `variables` has exactly `nominal`, `min`, and `max` values in micrometres, with `min <= nominal <= max`. Every source root explicitly maps `x`, `y`, and `z` to named variables. Every operation has an explicit declaration:

* Cuts name a `kerf` variable and retained setting. `machine_to_target` names the retained target; `remove_by` names the amount removed from the input after kerf. These commands are not interchangeable.
* Surfaces are either `remove_by` or `machine_to_target`. A target operation additionally names a removal guard, and the minimum input must cover the maximum target plus maximum guard.
* Rigid rotations and negligible glue lines are declared, rather than inferred.
* `final_tolerance` gives a closed `[min, max]` interval for each terminal axis.

`illustrative_uncertainty(plan)` creates a complete zero-width example only, visibly labelled as illustrative. It is not a default shop profile or a measurement claim.

## Conservative propagation

A dimension is an exact affine expression over `Fraction`s. A named variable used more than once remains the same variable: the validator never treats shared settings as independent random errors. Its interval is obtained by evaluating the affine expression over each named bound. This is an enclosure, not a probability model.

Cuts create both positive children and a positive kerf for every allowed realization. Surface removal produces a positive retained dimension. Actual input dimensions are checked against V2 process/workpiece minima and maxima. Glue sums the glue-axis affine dimensions. Every non-glue axis must be equal for **all** allowed settings. Interval overlap is specifically insufficient; a nonzero possible difference blocks dimensional validity. Rotations only permute expressions.

A result has `dimensionally_valid: false` for a bad digest, absent declaration, unsupported semantics, failed capacity/positivity/guard/tolerance check, or unresolved all-realizations glue compatibility. Nominal validity remains a separate result.

## Scope and exclusions

F1 covers the existing V2 cut, surface, rotation and negligible-glue assembly vocabulary and the declared V2 capacity profiles. It does not model wood movement, stock bow/twist/cup, fixture and clamp mechanics, material damage, machine safety, joint strength, statistical yield, arbitrary tool paths, glue-line thickness, or an unmodelled process. Unsupported semantics block the dimensional label instead of receiving an invented zero error.
