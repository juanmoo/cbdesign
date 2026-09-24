# Decision 0002: nominal rough-stock contract

Status: accepted for N1 implementation. This contract is nominal-only, not a machine-safety or physical-suitability certificate. Preparation removals are explicit material loss, not tolerance or uncertainty bounds.

## Version boundary

`cbdesign-plan/v1` remains the prepared-strip replay format. `cbdesign-plan/v2` is separate and requires complete stock, shop and construction metadata. No implicit migration or invented profile defaults. The public `load_plan` dispatches versions; `Plan.from_json_obj` remains the v1 API.

V2 replaces `stock` with exactly two `stock_types` (unique species and IDs) and finite `source_segments`. A type declares `width`, `thickness`, `grain: [0,1,0]`, and `preparation` with `x_min`, `x_max`, `y_min`, `y_max`, `z_min`, `z_max` nonnegative minimum removals. Roots derive their X/Z extents exclusively from their type. Segments declare `id`, `stock_type`, `length`, `boundary: allocated_window`, and `separation_operation`.

An allocated window starts with existing, unprepared boundaries; it incurs no fictitious kerf outside that finite root. Its referenced source-separation cut must actually cut that root along Y, retaining the minimum child and leaving a positive terminal reserve. The retained blank's two end allowances are measured from the separated blank, not donated by the external reserve. Both subsequent end trims are explicit saw cuts.

## Operations and profiles

The same four exact geometry primitives apply. V2 cuts additionally require `retained_side: min|max`; `outputs[0]` is always the retained child. Both children and kerf are positive. Maximum-side retention swaps the two positive children of the existing minimum-side cut geometry; no stock rotation is needed to prepare both ends. `retained_side` names the child to keep, not the face to trim: trimming the maximum X/Y face retains the minimum-side child.

The required shop profile has `manufacturing_increment`, `max_workpiece`, `cutting` and `surfacing`. Cutting has four profiles (`separation`, `preparation`, `slicing`, `final_trim`), each with `kerf`, `min_input` and `max_input` three-axis dimensions. It also has `minimum_rip_width`, `slice_min`, `slice_max`, `slicing_reserve`, and `new_face_jointing`. Each supported surfacing process declares `process`, supported `axes`, `min_input`, `max_input`, `glue_ready`, and `end_grain_supported`. Limits are checked on actual workpieces before consumption; discarded chips need not satisfy feed minima. Stage is derived from construction ancestry, not an operation label or Y axis alone.

All source dimensions, stock allowances, grid dimensions, command dimensions, kerfs, and profile lengths must be on the manufacturing increment. Zero is permitted only for nonnegative preparation requirements, never as a zero-volume operation.

Preparation requires both sufficient removal and a qualifying process. Raw longitudinal faces are not glue-ready. New X saw faces require explicit qualifying jointing of at least `new_face_jointing`; fresh boundaries cannot inherit previous face credits. Y end preparation uses explicit cuts and the declared end allowances. Face evidence is clipped, transformed and carried through assembly rather than asserted by `prepared_faces`. Prepared strips must meet all six allowances, preserve +Y grain, and have the declared strip thickness. Panel Z preparation must establish both faces with a glue-ready process before slicing; those faces become final-row mating faces after rotation.

## Grid and construction

`grid` declares `pitch`, `columns`, `strip_thickness`, `panel_thickness`, and `slice_length`. A `template` contains `recipes` (`id`, visual species `cells`), `panels` (`id`, `part`, `recipe`, ordered physical `strips`), and ordered `rows` (`rotated_part`, `panel`, `recipe`, `reversed`). Visual cells and physical strips are independent: a strip spans whole pitch multiples, and adjacent same-species strips retain their real joints.

A panel declaration registers either a real first-glue output or one prepared strip. Single-strip panels do not invent glue operations or joints. Exactly one final Y glue consumes at least two direct rotated slices, in declared row order. After panel Z preparation, slices are extracted by full-width Y cuts of successive remainders; no side-ripping, row splicing, recutting extracted slices or extra assembly stages. Slicing uses positive explicit terminal reserve. Normal rotation is `perm=[0,2,1], sign=[1,-1,1]`; reversed is `perm=[0,2,1], sign=[-1,1,1]`. Final finishing follows only retained surfaces and retained trim cuts.

## Reference arithmetic (mm)

Six maple roots: 108 × 419 × 33. Four walnut roots: 83 × 419 × 37.
Each separates as 419 = 316 + 3 kerf + 100 reserve; both end trims remove 5 offcut + 3 kerf, leaving 300. Thickness is milled on both faces: maple 3+3, walnut 5+5, leaving 27. External edges lose 1 each. Maple rip: 106 = 51 + 3 + 52; walnut: 81 = 51 + 3 + 27. Joint the retained new face by 1; joint the remainder's new face by 1 and remove 1 more from its opposite edge. Yields: twelve A50, four B50, four B25.

Two R panels use A50,A50,B50,A50,A50,B25,B25. One S panel uses B50,A50,A50,B50,A50,A50. Each is 300 × 300 × 27, flattened 1 per Z face to 25. Four slices of 32 and four kerfs of 3 leave 160 reserve. Twelve rows form 300 × 300 × 32. Row order: R+,R−,S+,R+,S−,R−,R+,S+,R−,R+,S−,R−. Flatten 1 per final Z face, then max-X/max-Y trims each retain 290 + 3 kerf + 7 offcut. Finished size: 290 × 290 × 30.

Independent ledger goldens (mm³; multiply by 10^9 for µm³):

| Category | Maple | Walnut |
| --- | ---: | ---: |
| Stock | 8959896 | 5146996 |
| Finished | 1698000 | 825000 |
| Kerf | 548856 | 320256 |
| Milling | 1889400 | 1398000 |
| Trim | 285240 | 175340 |
| Other offcuts | 4538400 | 2428400 |
| Balance | 0 | 0 |

Expected: **54 saw passes** (10 source separations + 20 end trims + 10 rips + 12 panel slices + 2 final trims), 17 first-stage joints, 11 final-row joints. The initial planning count of 44 omitted the ten source-separation passes; the independent volume ledger already included their kerf. These settings demonstrate nominal accounting and are not universal safe shop defaults.
