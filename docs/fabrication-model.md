# Fabrication model

This document defines the geometry and accounting contract for version 0. It describes supported operations, not machine-use instructions.

## 1. Coordinate system

Final board axes:

- X: across columns; finished width W.
- Y: across rows; finished length L.
- Z: thickness H.

First-stage panel axes before slicing:

- x: across longitudinal strips; width B.
- y: along the strips and longitudinal grain; panel length ℓ.
- z: panel thickness h after first-stage flattening.

Crosscut a slice of length d along y, then rotate it to expose end grain:

| Original extent | Final role |
| --- | --- |
| Strip width along x | Visible run width along X |
| Panel thickness h along z | Row height along Y |
| Slice length d along y | Thickness along Z before final flattening |

Transforms must be proper rigid rotations with explicit axis signs, not merely unsigned axis swaps. A reversal must also be represented by a realizable rotation. All slices must expose end grain on the final top face.

Example: a panel flattened to 20 mm thickness and sliced at 32 mm yields nominal 20 mm rows and 32 mm pre-flattening board thickness. Removing 2 mm from the final top/bottom gives 30 mm finished thickness. The source panel need not be 30 mm thick.

## 2. Nominal dimension equations

Let final trim amounts be tx−, tx+, ty−, ty+. Let total final top/bottom removal be f_final. For m columns and n rows:

- B = W + tx− + tx+
- p = B / m
- n h = L + ty− + ty+
- d = H + f_final
- h_strip = h + f_panel

Here f_panel is total thickness removed from a glued first-stage panel. Species-specific rough preparation is separate; both stock thicknesses must support h_strip after their required preparation losses.

All machining dimensions must lie on the configured increment. Reject candidate grids that cannot satisfy the nominal equations on that increment; never silently round every cell. Implementation must define how input unit conversion and representability are checked.

### Face-specific allowances

Track the direction and faces from which material is removed. First-panel thickness removal changes future row height; final-board top/bottom removal changes final thickness. Edge trim changes the visible pattern. A generic undirected “surfacing percentage” is insufficient.

For version 0, strips must have prepared mating edges before glue-up. Any panel-width cleanup must be explicitly budgeted and represented; it cannot silently shrink B. The first implementation should avoid unsupported width cleanup by using an explicit prepared-edge assumption and the final board's declared edge trim.

## 3. Stock and strip production

Source stock has a fixed rough cross-section and unlimited supply length. Instantiate finite rough segments in the plan before allocating parts.

For each segment:

1. Account for its source crosscut and any preparation end losses under one explicit convention.
2. Prepare to usable rectangular dimensions.
3. Rip strips using full-span orthogonal cuts.
4. Crosscut strips to panel requirements where supported by the selected sequence.
5. Record every retained part and residual piece.

Do not mix an explicit preparation cut with an allowance that already includes the same loss. The schema must identify whether each loss is a cut kerf, trimming operation, or other material removal.

Strips span integer column counts. A visible run wider than one species' usable stock width must be split into several strips of that species. Each split creates a real glue joint.

## 4. First-stage panels and batching

A recipe family describes a visible sequence up to permitted reversal. A panel instance is one actual assembly with a physical strip realization and finite length.

For each recipe demand:

- Determine the number of retained slices.
- Batch production into panel instances satisfying length/capacity and handling limits.
- Include end preparation, every slice cut, and a required terminal handling reserve.
- Record residual material, including any unused panel length.

No general n−1 kerf formula is authoritative. For example, cutting n retained slices while leaving a terminal reserve generally needs n separating passes in addition to any separately modeled preparation cuts. If a last retained part uses an existing boundary, the cut count differs. The operation sequence determines the geometry and losses.

Batching must be reproducible. Version 0 uses deterministic bounded enumeration rather than unrestricted shop scheduling.

## 5. Glue and assembly

Glue operations require compatible, prepared mating faces. The initial nominal geometry assumes negligible glue-line thickness; this assumption must be explicit in the plan. Real alignment and machining variation belong in the tolerance model.

Store:

- Ordered input part IDs and their transforms.
- Joined face pairs and nominal joint area.
- Output dimensions and material subdivision.
- Recipe and panel instance IDs.

The final glue-up joins intact slices edge to edge in their chosen row order. No offsets, overlaps, missing regions, individual cell placement, or end-to-end row splices are permitted.

Two-stage glue-up count means two process stages, not necessarily two physical glue-ups. Multiple first-stage panels increase the actual glue-up count.

## 6. Finishing

First-stage flattening and final end-grain flattening are different operations with different orientation and capacity checks.

Final flattening must specify a supported process and declared removal bounds. Do not default to ordinary thickness-planer use on end grain. The program validates the configured method's modeled constraints, not universal suitability or safety.

Final edge trim is represented by actual geometry removal and applicable saw passes. Render the retained rectangle after trimming, not the untrimmed grid.

Sanding/finishing removal must either be included in a declared total finishing allowance or separately modeled, never both. Coatings are outside the wood-volume ledger.

## 7. Dimensions, uncertainty, and feasibility

Fixed-point arithmetic prevents numerical drift; it does not represent machining accuracy.

Distinguish:

1. Nominal set dimensions.
2. Planned removal allowances.
3. Declared dimensional variation bounds.
4. Permitted final dimensional tolerances.

The implementation must propagate conservative dimensional bounds or otherwise document an equivalent conservative check. Sum of row-height variation can affect final length. Trimming can absorb oversize only when enough material remains and the specified trim/target-sizing operation supports it.

Bounds must distinguish correlated settings from independent errors where relevant; do not imply probabilistic confidence without a probabilistic model. If a guarantee cannot be established under the supplied bounds, report that limitation instead of treating nominal equality as proof.

Minimum final feature dimensions are distinct from machine-handled workpiece dimensions. A cell within a glued slice is not separately fed through a saw. Check handling constraints at the actual operation stage, including the workpiece remaining after previous cuts.

## 8. Provenance and material conservation

Every part retains source species and spatial provenance. An assembly can contain multiple species; it is not assigned a single species label.

For instantiated rough stock:

V_stock = V_finished + V_kerf + V_milling + V_trim + V_other_offcuts.

Ledger categories are mutually exclusive. Reusable is an attribute of an offcut, not a second volume category. Report total and per-species balances.

Kerfs and removal through mixed-species assemblies must be attributed using their actual material subdivision. Source-to-product traceability survives cuts, glue-ups, and rotations.

Do not subtract reusable remnants from consumed stock as though they were used by another project. Internal reuse is allowed only when an explicit later operation consumes the actual remnant; the first allocator need not optimize such reuse.

## 9. Independent replay

A validator reconstructs part geometry and material layout from stock and operations. It must not trust solver-reported dimensions, renders, costs, or ledger totals.

It checks operation legality, dimensional compatibility, transforms, source allocation, capacities, handling limits, allowances, nominal dimensions and declared tolerance checks, final pattern, and volume conservation. Sharing low-level exact arithmetic is reasonable; merely reusing the solver's conclusions is not independent validation.
