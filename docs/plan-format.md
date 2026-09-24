# M1 plan format and operation semantics

`cbdesign-plan/v1` is a strict JSON document. Every dimension is a positive **integer micrometre** value; JSON booleans and floats are invalid. It is a nominal-only replay format, not a machining program or safety certification.

## Roots and provenance

`stock` creates finite source boxes with `(x, y, z)` sizes. Source longitudinal grain is immutable `+Y`. Every region carries its source box, species, grain vector, and current box. Replayed operations keep the mapping `current = R × source + t`; cuts and removals clip source and current regions together. Equal-species regions are never coalesced, so hidden physical joints remain observable.

## Operations

Operations must be in topological order. IDs, roots, and generated parts are globally unique; a live part is consumed at most once.

- `cut`: a full-span axis cut. `outputs[0]` is the commanded retained child and `outputs[1]` is residual/offcut. `retained` is the commanded child dimension and must meet the manufacturing increment. `kerf` is exact material loss and must agree with `shop.saw_kerf` for `tool: saw`; it is not automatically a commanded increment. `category` is `other_offcuts` normally or `trim` for an explicit final trim cut. Only a `trim` cut's retained `outputs[0]` may occur on the finished-terminal chain.
- `surface`: removes a specified amount from a named `min` or `max` face. It creates both retained and removed parts and classifies the removal as `milling`, `trim`, or `other_offcuts`.
- `rotate`: a signed axis permutation whose determinant is `+1`; reflections are invalid. Outputs normalize into a positive local coordinate frame.
- `glue`: ordered, full-face concatenation along one axis. Offsets are derived, inputs must have matching other extents, and prepared mating faces plus a negligible glue-line assumption are explicit.

`finishing` names exactly one finished terminal and an end-grain-capable method. Geometric finishing uses explicit `surface`; finishing metadata cannot silently change geometry. A surface's `removed` output is an immutable terminal loss and cannot be consumed or designated finished. A retained final trim cut is supported only through its `outputs[0]` child.

Every other live terminal, including untouched stock and removal parts, needs exactly one `disposition`. Terminal dispositions cannot reclassify material: surface removals retain their declared `milling`, `trim`, or `other_offcuts` category; retained unused inventory is `other_offcuts`. Cut kerf is recorded directly at the cut and is never a terminal disposition. The ledger keeps `kerf`, `milling`, `trim`, and `other_offcuts` mutually exclusive; `reusable` is an offcut attribute, not a volume category.

## Construction template

M1 accepts only the restricted two-stage construction: at least one first-stage strip glue, exactly one final row glue, intact rotated rows in that final glue, and no unaccounted terminals. Optional recipe/row metadata is checked against the final glue's inputs. The final top must have source grain normal to it (end grain).

## Status

A successful report uses `nominal_valid`, never a feasibility or fabrication-certification claim. It explicitly lists interval uncertainty propagation, physical safety, joint strength, inventory optimization, and optimization as not evaluated.
