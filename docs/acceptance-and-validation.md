# Acceptance and validation

M1 implements and runs regression coverage for strict dimensions, half-open geometry, all proper rotations, operation replay, provenance partitioning, ledgers, fixtures, fault injection, CLI output handling, and SVG structure. The list below remains the broader release-gate target; entries covering search, target scoring, batching synthesis, and physical review are deferred to later milestones.

## 1. Required reference cases

| Case | Required evidence |
| --- | --- |
| Exact checkerboard | Correct alternating layout, dimensions, recipe reuse, cuts, and material balance |
| Asymmetric binary icon | Axis mapping, reversal, row order, and final render cannot pass through symmetry by accident |
| Reversed rows | One family can supply normal and reversed rows via explicit valid rotations |
| Approximate recipe reuse | Fewer families than exact reproduction, with correctly measured nonzero image error |
| Different stock cross-sections | Both species mill to compatible thickness; width differences affect actual strip allocation |
| Wide same-species run | Multiple source-compatible strips form one visible run; hidden joints are counted |
| Multi-panel batch | One recipe requires multiple physical panels; all slice cuts and end reserves are recorded |
| Trimmed partial cells | Post-trim preview and error use only retained physical area |
| Thickness-axis example | 20 mm panel thickness becomes row height, while 32 mm slices can yield 30 mm final thickness with 2 mm removal |
| Intentionally invalid plan | Independent validator rejects corruption rather than trusting solver metadata |

Include targets with stripes, stepped diamonds, block letters, and unrelated rows when benchmarking approximation quality. Avoid only symmetric examples.

## 2. Unit tests

- Dimension parsing, increment representability, and display-unit conversion.
- Proper rotations and grain-axis transformations.
- Recipe canonicalization under permitted reversal.
- Same-species run merging and physical strip splitting.
- Cell target occupancy and physical-area mismatch.
- Face-specific milling and trim dimensions.
- Explicit cut geometry and kerf accounting.
- Panel batching, last retained slice, and terminal reserves.
- Joint count and area, including same-species joints.
- Total and per-species ledger reconciliation.
- Search status distinctions and serialization versions.

## 3. Validator fault injection

Corrupt otherwise valid plans by:

- Removing a kerf or double-counting a trim allowance.
- Over-allocating a stock segment or consuming a part twice.
- Changing a species label without provenance.
- Flipping an axis incorrectly or exposing long grain.
- Introducing a dependency cycle or a missing input part.
- Joining incompatible faces or leaving a gap.
- Exceeding a machine capacity or violating a stage-specific handling limit.
- Removing too much thickness or reporting pre-trim geometry as finished geometry.
- Omitting a same-species glue joint.
- Altering solver-reported dimensions, ledger totals, or image score without altering operations.

The validator should reject the defect or recompute the correct derived quantity according to its API contract, never silently trust inconsistent solver summaries.

## 4. Property tests

- Every consumed piece has valid provenance and is consumed at most once unless explicitly modeled as an unchanged reference.
- A cut conserves parent volume across children and kerf.
- A glue-up conserves wood volume under the negligible-glue-line assumption.
- Rotation preserves dimensions up to axis permutation, material volume, and species.
- Material ledger categories are mutually exclusive and sum to instantiated rough stock.
- Rendered material matches independently replayed geometry.
- Display-unit changes do not change physical feasibility.
- Tightening a hard bound cannot make the same previously invalid plan valid for that bound.
- Increasing kerf cannot improve yield for the same fixed cutting pattern and stock.

Do not assert heuristic-output monotonicity: changing constraints or kerf can change the search path, so a heuristic may find a better or worse candidate for incidental reasons. Mathematical monotonicity claims must specify a fixed plan, feasible set, or proven optimum.

## 5. Search tests

- Compare tiny fixed-grid recipe problems with exhaustive enumeration.
- Repeat runs with identical seeds and tie-break rules.
- Validate every returned incumbent, including runs stopped by a time budget.
- Verify that candidates obey their reported recipe budget.
- Test reversal equivalence without losing distinct row assignments.
- Do not require one exact plan when several are equally valid.
- Treat no-found-plan as unknown unless a proof within stated bounds exists.
- Confirm candidate metrics are computed after physical plan expansion and trimming.

## 6. Physical review gate

Before calling documentation shop-ready:

1. Have at least one generated plan reviewed by an experienced woodworker.
2. Build a selected reference board under recorded shop assumptions.
3. Compare actual and predicted dimensions, stock requirements, cut counts, and removal losses.
4. Record ambiguous instructions and failed assumptions.
5. Turn model discrepancies into regression cases.

The release goal is zero known false-feasible plans in the reference corpus. This does not establish universal safety or a statistical guarantee.
