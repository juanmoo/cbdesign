"""Independent exact replay, provenance partition checks, and construction-template checks."""
from __future__ import annotations
from dataclasses import dataclass, replace
from collections import Counter, defaultdict
from typing import Any
from .geometry import Box, Rotation
from .models import Plan, Cut, Surface, Rotate, Glue
from .dimensions import require_increment


class ReplayError(Exception):
    def __init__(self, code: str, message: str, operation: str | None = None, part: str | None = None, expected: Any = None, actual: Any = None):
        self.diagnostic = {"code": code, "message": message, **({"operation": operation} if operation else {}), **({"part": part} if part else {}), **({"expected": expected} if expected is not None else {}), **({"actual": actual} if actual is not None else {})}
        super().__init__(message)


@dataclass(frozen=True)
class Region:
    source_id: str
    species: str
    source: Box
    current: Box
    grain: tuple[int, int, int]

    @property
    def volume(self): return self.current.volume


@dataclass(frozen=True)
class Part:
    id: str
    size: tuple[int, int, int]
    regions: tuple[Region, ...]
    history: tuple[str, ...] = ()

    @property
    def volume(self): return sum(r.volume for r in self.regions)


def clip_regions(regions: tuple[Region, ...], box: Box, normalise_to: tuple[int, int, int] | None = None) -> tuple[Region, ...]:
    kept = []
    for region in regions:
        hit = region.current.intersect(box)
        if not hit: continue
        # Each transformation in this restricted model remains a signed axis permutation,
        # but source clipping follows the exact source/current affine correspondence encoded
        # by extents. Cuts after rotation therefore retain source-coordinate provenance.
        src_origin = list(region.source.origin); src_size = [0, 0, 0]
        for cur_axis in range(3):
            # Find source axis that maps to cur_axis from grain-independent bounding mapping.
            # Region source/current dimensions identify it uniquely for actual operation paths.
            matches = [i for i in range(3) if region.source.size[i] == region.current.size[cur_axis]]
            # Repeated dimensions make identity ambiguous; current/source volume provenance is
            # still clipped below via a stored axis map added by rotations. Defaults identity.
            source_axis = region.axis_map[cur_axis] if hasattr(region, "axis_map") else cur_axis
            sign = region.axis_sign[cur_axis] if hasattr(region, "axis_sign") else 1
            delta = hit.origin[cur_axis] - region.current.origin[cur_axis]
            if sign > 0:
                src_origin[source_axis] += delta
            else:
                src_origin[source_axis] += region.current.size[cur_axis] - delta - hit.size[cur_axis]
            src_size[source_axis] = hit.size[cur_axis]
        current = hit
        if normalise_to is not None:
            current = Box(tuple(hit.origin[i] - normalise_to[i] for i in range(3)), hit.size)
        kept.append(_region(region.source_id, region.species, Box(tuple(src_origin), tuple(src_size)), current, region.grain,
                              getattr(region, "axis_map", (0,1,2)), getattr(region, "axis_sign", (1,1,1))))
    return tuple(kept)


def _region(source_id, species, source, current, grain, axis_map=(0,1,2), axis_sign=(1,1,1)):
    r = Region(source_id, species, source, current, grain)
    object.__setattr__(r, "axis_map", axis_map)
    object.__setattr__(r, "axis_sign", axis_sign)
    return r


def transformed_region(region: Region, rotation: Rotation, old_size: tuple[int,int,int]) -> Region:
    # coordinate y=Q*x + offset to normalize output at zero
    new_size = rotation.output_size(old_size)
    origin = []
    for out in range(3):
        old = rotation.perm[out]
        start = region.current.origin[old]
        length = region.current.size[old]
        origin.append(start if rotation.sign[out] > 0 else old_size[old] - start - length)
    # compose output->source axis mapping
    old_map = getattr(region, "axis_map", (0,1,2)); old_sign = getattr(region, "axis_sign", (1,1,1))
    amap = tuple(old_map[rotation.perm[out]] for out in range(3))
    asign = tuple(rotation.sign[out] * old_sign[rotation.perm[out]] for out in range(3))
    grain = tuple(rotation.sign[i] * region.grain[rotation.perm[i]] for i in range(3))
    return _region(region.source_id, region.species, region.source, Box(tuple(origin), rotation.output_size(region.current.size)), grain, amap, asign)


def volume_by_species(regions):
    out = Counter()
    for r in regions: out[r.species] += r.volume
    return dict(out)


@dataclass
class Replay:
    parts: dict[str, Part]
    terminal: str
    losses: dict[str, list[Region]]
    joints: list[dict]
    operations: list[dict]
    source_sizes: dict[str, tuple[int,int,int]]
    source_species: dict[str, str]
    row_sequences: dict[str, list[str]]
    first_glue_panels: dict[str, Part]

    def ledger(self):
        initial = Counter(); finished = Counter(); categories = defaultdict(Counter)
        for part in self.parts.values():
            for r in part.regions:
                # Roots have history empty; only calculate initial uniquely by source boxes.
                pass
        for source, size in self.source_sizes.items():
            initial[self.source_species[source]] += size[0] * size[1] * size[2]
        final = self.parts[self.terminal]
        finished.update(volume_by_species(final.regions))
        for cat, regs in self.losses.items(): categories[cat].update(volume_by_species(regs))
        # terminal nonfinal parts are dispositioned by caller and included in losses.
        species = sorted(initial)
        categories_order = ("kerf", "milling", "trim", "other_offcuts")
        return {"units": "cubic_micrometres", "species": {s: {"stock": initial[s], "finished": finished[s], **{c: categories[c][s] for c in categories_order}, "balance": initial[s] - finished[s] - sum(categories[c][s] for c in categories)} for s in species}, "totals": {"stock": sum(initial.values()), "finished": sum(finished.values()), **{c: sum(categories[c].values()) for c in categories_order}}}


def preflight(plan: Plan):
    species = {stock.species for stock in plan.stock}
    if len(species) != 2:
        raise ReplayError("two_species_scope", "M1 requires exactly two distinct stock species", expected=2, actual=len(species))
    seen = {s.id for s in plan.stock}; produced = set(seen); consumed = set()
    removal_outputs: set[str] = set()
    op_ids = set()
    for op in plan.operations:
        if op.id in op_ids: raise ReplayError("duplicate_operation_id", "operation IDs must be unique", op.id)
        op_ids.add(op.id)
        inputs = [op.input] if hasattr(op, "input") else op.inputs
        outputs = list(op.outputs) if isinstance(op, Cut) else [op.output] + ([op.removed] if isinstance(op, Surface) else [])
        for item in inputs:
            if item not in produced: raise ReplayError("missing_or_forward_reference", "operations must be topologically ordered", op.id, item)
            if item in removal_outputs: raise ReplayError("consumed_removal_output", "surface-removal outputs are terminal losses and may not be consumed", op.id, item)
            if item in consumed: raise ReplayError("multiple_consumers", "input part may be consumed once", op.id, item)
        if len(inputs) != len(set(inputs)): raise ReplayError("repeated_glue_input", "glue input cannot repeat", op.id)
        for item in outputs:
            if item in produced: raise ReplayError("duplicate_part_id", "part ID is globally unique", op.id, item)
        if isinstance(op, Surface):
            removal_outputs.add(op.removed)
        consumed.update(inputs); produced.update(outputs)


def replay(plan: Plan) -> Replay:
    preflight(plan)
    parts: dict[str, Part] = {}
    source_sizes = {}; source_species = {}
    for stock in plan.stock:
        size = tuple(map(int, stock.size)); box = Box((0,0,0), size)
        parts[stock.id] = Part(stock.id, size, (_region(stock.id, stock.species, box, box, (0,1,0)),))
        source_sizes[stock.id] = size; source_species[stock.id] = stock.species
    losses: dict[str, list[Region]] = defaultdict(list); joints=[]; log=[]; row_sequences={}; first_glue_panels={}; terminal_origins={}
    for op in plan.operations:
        try:
            # Capacity is evaluated at the actual operation stage, including roots later consumed.
            if plan.shop.max_workpiece is not None:
                maximum = tuple(map(int, plan.shop.max_workpiece))
                input_ids = [op.input] if hasattr(op, "input") else op.inputs
                for input_id in input_ids:
                    candidate = parts[input_id]
                    if any(candidate.size[i] > maximum[i] for i in range(3)):
                        raise ReplayError("shop_capacity", "input workpiece exceeds configured capacity", op.id, input_id, maximum, candidate.size)
            if isinstance(op, Cut) and plan.shop.max_slice_length is not None and op.axis == 1 and int(op.retained) > int(plan.shop.max_slice_length):
                raise ReplayError("slice_stage_limit", "commanded retained slice exceeds configured slice-stage limit", op.id, expected=int(plan.shop.max_slice_length), actual=int(op.retained))
            if isinstance(op, Cut):
                p = parts.pop(op.input); a, k, b = Box((0,0,0), p.size).cut(op.axis, int(op.retained), int(op.kerf))
                parts[op.outputs[0]] = Part(op.outputs[0], a.size, clip_regions(p.regions, a, a.origin), p.history + (op.id,))
                parts[op.outputs[1]] = Part(op.outputs[1], b.size, clip_regions(p.regions, b, b.origin), p.history + (op.id,))
                terminal_origins[op.outputs[1]] = op.category
                losses["kerf"].extend(clip_regions(p.regions, k)); log.append({"id":op.id,"kind":"cut","inputs":[op.input],"outputs":list(op.outputs),"input_size_um":list(p.size),"output_sizes_um":{op.outputs[0]:list(a.size),op.outputs[1]:list(b.size)},"axis":op.axis,"retained_um":int(op.retained),"kerf_um":int(op.kerf),"kerf_volume_um3":k.volume,"tool":op.tool,"category":op.category})
            elif isinstance(op, Surface):
                p=parts.pop(op.input); kept, rem=Box((0,0,0),p.size).remove_face(op.axis,op.side,int(op.amount))
                parts[op.output]=Part(op.output,kept.size,clip_regions(p.regions,kept,kept.origin),p.history+(op.id,))
                remregs=clip_regions(p.regions,rem,rem.origin); parts[op.removed]=Part(op.removed,rem.size,remregs,p.history+(op.id,)); terminal_origins[op.removed] = op.category; log.append({"id":op.id,"kind":"surface","inputs":[op.input],"outputs":[op.output,op.removed],"input_size_um":list(p.size),"output_sizes_um":{op.output:list(kept.size),op.removed:list(rem.size)},"axis":op.axis,"side":op.side,"amount_um":int(op.amount),"category":op.category,"process":op.process})
            elif isinstance(op, Rotate):
                p=parts.pop(op.input); r=Rotation(tuple(op.perm),tuple(op.sign)); size=r.output_size(p.size)
                parts[op.output]=Part(op.output,size,tuple(transformed_region(x,r,p.size) for x in p.regions),p.history+(op.id,)); log.append({"id":op.id,"kind":"rotate","inputs":[op.input],"outputs":[op.output],"input_size_um":list(p.size),"output_sizes_um":{op.output:list(size)},"perm":list(op.perm),"sign":list(op.sign)})
            else:
                ps=[parts.pop(i) for i in op.inputs]
                if op.stage == "final":
                    for input_id, p in zip(op.inputs, ps):
                        row_sequences[input_id] = [r.species for r in sorted(p.regions, key=lambda r: r.current.origin[0])]
                base=list(ps[0].size)
                for p in ps[1:]:
                    if any(p.size[i] != base[i] for i in range(3) if i != op.axis): raise ReplayError("incompatible_glue_faces","all non-glue extents must match",op.id,expected=base,actual=p.size)
                regions=[]; offset=0
                for p in ps:
                    for r in p.regions:
                        cur=list(r.current.origin); cur[op.axis]+=offset
                        regions.append(_region(r.source_id,r.species,r.source,Box(tuple(cur),r.current.size),r.grain,getattr(r,"axis_map",(0,1,2)),getattr(r,"axis_sign",(1,1,1))))
                    offset += p.size[op.axis]
                base[op.axis]=offset; parts[op.output]=Part(op.output,tuple(base),tuple(regions),tuple(x for p in ps for x in p.history)+(op.id,))
                if op.stage == "first":
                    # Snapshot the actual first-stage output. Later cuts/rotations must not
                    # turn descendants or the final board into panel-render candidates.
                    first_glue_panels[op.output] = parts[op.output]
                for left,right in zip(ps,ps[1:]): joints.append({"operation":op.id,"stage":op.stage,"axis":op.axis,"area":left.size[(op.axis+1)%3]*left.size[(op.axis+2)%3],"left":left.id,"right":right.id})
                log.append({"id":op.id,"kind":"glue","inputs":list(op.inputs),"outputs":[op.output],"input_sizes_um":{p.id:list(p.size) for p in ps},"output_sizes_um":{op.output:list(base)},"axis":op.axis,"stage":op.stage,"joint_count":len(ps)-1,"prepared_faces":op.prepared_faces,"negligible_glue_line":op.negligible_glue_line})
        except ReplayError: raise
        except ValueError as e: raise ReplayError("invalid_operation_geometry",str(e),op.id) from e
    if plan.finishing.terminal not in parts: raise ReplayError("missing_terminal","finishing terminal does not exist",part=plan.finishing.terminal)
    terminal=plan.finishing.terminal
    # Capacity also applies to every output and final terminal, not merely inputs.
    if plan.shop.max_workpiece is not None:
        maximum = tuple(map(int, plan.shop.max_workpiece))
        for part in parts.values():
            if any(part.size[axis] > maximum[axis] for axis in range(3)):
                raise ReplayError("shop_capacity", "generated or terminal workpiece exceeds configured capacity", part=part.id, expected=maximum, actual=part.size)
    # Disposition is mandatory exactly once for every live nonfinished terminal.
    # A terminal created by Surface has an immutable operation-derived category;
    # ordinary unused retained inventory is always other_offcuts (with reusable flag).
    live = set(parts) - {terminal}
    disposition_ids = [d.part for d in plan.dispositions]
    if len(disposition_ids) != len(set(disposition_ids)):
        duplicates = sorted(pid for pid, count in Counter(disposition_ids).items() if count > 1)
        raise ReplayError("duplicate_disposition", "each terminal must have exactly one disposition", actual=duplicates)
    declared = {d.part: d for d in plan.dispositions}
    if set(declared) != live:
        raise ReplayError("terminal_disposition", "every nonfinished live terminal needs exactly one disposition", expected=sorted(live), actual=sorted(declared))
    for pid, d in declared.items():
        expected_category = terminal_origins.get(pid, "other_offcuts")
        if d.category != expected_category:
            raise ReplayError("disposition_category_mismatch", "terminal disposition cannot reclassify operation-derived material", part=pid, expected=expected_category, actual=d.category)
        losses[expected_category].extend(parts[pid].regions)
    rep=Replay(parts,terminal,losses,joints,log,source_sizes,source_species,row_sequences,first_glue_panels)
    _validate(rep,plan)
    return rep


def _operation_producers(plan: Plan) -> dict[str, object]:
    producers: dict[str, object] = {}
    for operation in plan.operations:
        outputs = list(operation.outputs) if isinstance(operation, Cut) else [operation.output] + ([operation.removed] if isinstance(operation, Surface) else [])
        for output in outputs:
            producers[output] = operation
    return producers


def _ancestors(part_id: str, producers: dict[str, object]) -> list[object]:
    operation = producers.get(part_id)
    if operation is None:
        return []
    inputs = [operation.input] if hasattr(operation, "input") else operation.inputs
    return [*sum((_ancestors(input_id, producers) for input_id in inputs), []), operation]


def _validate_construction_lineage(plan: Plan) -> Glue:
    """Enforce the one-panel-to-intact-slice-to-row construction lineage."""
    producers = _operation_producers(plan)
    glues = [operation for operation in plan.operations if isinstance(operation, Glue)]
    if any(not operation.prepared_faces for operation in glues):
        bad = next(operation for operation in glues if not operation.prepared_faces)
        raise ReplayError("unprepared_glue_faces", "every glue operation requires explicit prepared mating faces", bad.id)
    first_glues = [operation for operation in glues if operation.stage == "first"]
    final_glues = [operation for operation in glues if operation.stage == "final"]
    if not first_glues or len(final_glues) != 1:
        raise ReplayError("construction_template", "at least one first-stage glue and exactly one final glue are required")
    for first in first_glues:
        if first.axis != 0:
            raise ReplayError("first_glue_orientation", "first-stage strips must glue side by side along X", first.id, expected=0, actual=first.axis)
        for input_id in first.inputs:
            prior = _ancestors(input_id, producers)
            if any(isinstance(operation, (Glue, Rotate)) for operation in prior):
                raise ReplayError("first_glue_lineage", "first-stage glue inputs must be unrotated longitudinal stock/strip descendants", first.id, input_id)
    final = final_glues[0]
    if final.axis != 1:
        raise ReplayError("final_glue_orientation", "final rows must glue along Y", final.id, expected=1, actual=final.axis)
    for row_id in final.inputs:
        rotate = producers.get(row_id)
        if not isinstance(rotate, Rotate):
            raise ReplayError("row_not_intact_slice", "every final glue input must be a direct rotated slice", final.id, row_id)
        prior = _ancestors(rotate.input, producers)
        prior_glues = [operation for operation in prior if isinstance(operation, Glue)]
        if len(prior_glues) != 1 or prior_glues[0].stage != "first":
            raise ReplayError("row_lineage", "row must descend from exactly one first-stage panel glue", final.id, row_id)
        if not any(isinstance(operation, (Cut, Surface)) for operation in prior):
            raise ReplayError("row_not_slice", "final row must be an explicit slice of its first-stage panel", final.id, row_id)
        if any(isinstance(operation, Rotate) for operation in prior):
            raise ReplayError("row_lineage", "rotated rows cannot be recut, spliced, or rotated again", final.id, row_id)
        if any(isinstance(operation, Glue) and operation.stage != "first" for operation in prior):
            raise ReplayError("row_lineage", "row lineage contains an unsupported glue stage", final.id, row_id)
    return final


def _validate_final_finishing_path(plan: Plan, final_glue: Glue) -> None:
    """Tie end-grain material removal, not just metadata, to finishing.method."""
    producers = _operation_producers(plan)
    current = plan.finishing.terminal
    saw_end_grain_removal = False
    while current != final_glue.output:
        operation = producers.get(current)
        if isinstance(operation, Surface) and operation.output == current:
            if operation.axis == 2:
                saw_end_grain_removal = True
                if operation.process != plan.finishing.method:
                    raise ReplayError("finishing_process_mismatch", "final end-grain removal process must equal declared finishing method", operation.id, expected=plan.finishing.method, actual=operation.process)
            current = operation.input
            continue
        # A final trim cut is permitted only by following its explicitly retained child
        # (outputs[0]); outputs[1] is residual/offcut and can never become finished.
        if isinstance(operation, Cut) and operation.outputs[0] == current and operation.category == "trim":
            current = operation.input
            continue
        raise ReplayError("finishing_lineage", "finished terminal must follow retained surface outputs or retained final trim-cut outputs", part=current)
    if not saw_end_grain_removal:
        raise ReplayError("missing_end_grain_finishing", "finished terminal requires explicit final Z-axis end-grain removal", part=plan.finishing.terminal)


def _validate(rep: Replay, plan: Plan):
    final_glue = _validate_construction_lineage(plan)
    _validate_final_finishing_path(plan, final_glue)
    final=rep.parts[rep.terminal]
    if final.size != tuple(map(int,plan.expected_final_size)): raise ReplayError("final_dimension_mismatch","replayed final dimensions do not match declaration",part=final.id,expected=list(plan.expected_final_size),actual=list(final.size))
    try:
        for value,label in zip(final.size,("final x","final y","final z")): require_increment(value,int(plan.shop.manufacturing_increment),label)
        for op in plan.operations:
            if isinstance(op,Cut): require_increment(int(op.retained),int(plan.shop.manufacturing_increment),f"cut retained {op.id}")
            if isinstance(op,Surface): require_increment(int(op.amount),int(plan.shop.manufacturing_increment),f"surface amount {op.id}")
    except ValueError as e: raise ReplayError("increment_violation",str(e)) from e
    if plan.shop.saw_kerf is not None:
        for op in plan.operations:
            if isinstance(op,Cut) and op.tool == "saw" and int(op.kerf) != int(plan.shop.saw_kerf): raise ReplayError("kerf_profile_mismatch","cut kerf differs from declared saw profile",op.id,expected=int(plan.shop.saw_kerf),actual=int(op.kerf))
    # Final top must expose transformed source Y (end grain): no region may have grain along final XY plane.
    if any(abs(r.grain[2]) != 1 for r in final.regions): raise ReplayError("long_grain_exposure","final top face does not expose end grain",part=final.id)
    # Full terminal source partition accounting by exact source boxes: volume plus no overlap per source.
    ledger=rep.ledger()
    if any(v["balance"] != 0 for v in ledger["species"].values()): raise ReplayError("source_partition_failure","terminal regions do not fully partition source stock",actual=ledger)
    # Volume alone is insufficient: source-coordinate retained/lost boxes must have no
    # overlap and together exactly cover every instantiated source root.
    terminal_regions = list(final.regions) + [r for regs in rep.losses.values() for r in regs]
    for source_id, source_size in rep.source_sizes.items():
        root = Box((0, 0, 0), source_size)
        pieces = [r.source for r in terminal_regions if r.source_id == source_id]
        if any(root.intersect(piece) != piece for piece in pieces):
            raise ReplayError("source_partition_failure", "source-derived region lies outside its stock root", part=source_id)
        if sum(piece.volume for piece in pieces) != root.volume:
            raise ReplayError("source_partition_failure", "source-coordinate pieces do not cover their root", part=source_id, expected=root.volume, actual=sum(piece.volume for piece in pieces))
        for i, left in enumerate(pieces):
            for right in pieces[i + 1:]:
                if left.intersect(right) is not None:
                    raise ReplayError("source_partition_failure", "source-coordinate terminal pieces overlap", part=source_id)
    first=sum(1 for j in rep.joints if j["stage"]=="first"); finalj=sum(1 for j in rep.joints if j["stage"]=="final")
    if not first or not finalj: raise ReplayError("construction_template","two glue stages are required")
    if any(isinstance(o,Glue) and o.stage=="first" for o in plan.operations if False): pass
    # Final-glue successor semantics are enforced precisely by _validate_final_finishing_path,
    # including retained explicit trim cuts and excluding surface removed outputs.
    final_glues=[o for o in plan.operations if isinstance(o,Glue) and o.stage=="final"]
    if len(final_glues)!=1: raise ReplayError("construction_template","exactly one final row glue-up is required")
    final_glue=final_glues[0]
    if len(plan.template.rows) and len(plan.template.rows) != len(final_glue.inputs): raise ReplayError("row_assignment_mismatch", "row assignments must cover every final glue input", expected=len(final_glue.inputs), actual=len(plan.template.rows))
    assigned_rows = [row.rotated_part for row in plan.template.rows]
    if len(assigned_rows) != len(set(assigned_rows)) or set(assigned_rows) != set(final_glue.inputs):
        raise ReplayError("row_assignment_mismatch", "row assignments must bijectively cover final glue inputs", expected=sorted(final_glue.inputs), actual=assigned_rows)
    recipes = {r.id: r for r in plan.template.recipes}
    for row in plan.template.rows:
        if row.rotated_part not in final_glue.inputs: raise ReplayError("row_assignment_mismatch","declared row is not an input to final glue",part=row.rotated_part)
        if row.recipe not in recipes: raise ReplayError("recipe_missing", "row assignment names no declared recipe", part=row.rotated_part, actual=row.recipe)
        # Physical regions in final X order were captured before final glue consumes the row.
        sequence = rep.row_sequences[row.rotated_part]
        expected = recipes[row.recipe].sequence
        if row.reversed: expected = list(reversed(expected))
        if sequence != expected: raise ReplayError("recipe_sequence_mismatch", "declared recipe differs from replayed strip sequence", part=row.rotated_part, expected=expected, actual=sequence)
