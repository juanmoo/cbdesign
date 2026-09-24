"""Exact, deterministic N2 compiler from DesignRequest to replayable PlanV2."""
from __future__ import annotations
from dataclasses import dataclass
from collections import Counter
from typing import Any
from .design import DesignRequest
from .models_v2 import PlanV2
from .replay import Replay, replay, ReplayError
from .validation import validate


@dataclass(frozen=True)
class CompileError:
    code: str
    message: str


@dataclass(frozen=True)
class CompileResult:
    plan: PlanV2 | None
    report: dict[str, Any]
    replay: Replay | None
    metrics: dict[str, Any]
    error: CompileError | None = None


def _fail(code: str, message: str) -> CompileResult:
    return CompileResult(None, {"status":"failed", "code":code, "message":message}, None, {}, CompileError(code, message))


def compile_design(request: DesignRequest | dict[str, Any]) -> CompileResult:
    """Compile an exact plan. A failure is bounded to this deterministic recipe.

    It never says that *all* allocations are infeasible; ``allocation_failed`` means
    the conservative first-fit allocation implemented here did not fit finite stock.
    """
    try:
        # Revalidate model instances too: model_copy(update=...) intentionally does
        # not coerce nested replacements, while compiler inputs must remain strict.
        request = DesignRequest.model_validate(request.model_dump()) if isinstance(request, DesignRequest) else DesignRequest.model_validate(request)
    except Exception as exc: return _fail("invalid_request", str(exc))
    inc, rows, cols = request.shop.increment, len(request.matrix), len(request.matrix[0])
    # Explicit trim allowances are part of the request contract.  The raw grid
    # must divide exactly: rounding would silently alter the requested cell layout.
    raw_x, raw_y = request.final.x + request.shop.final_x_trim, request.final.y + request.shop.final_y_trim
    if raw_x % cols or raw_y % rows:
        return _fail("nonrepresentable_grid", "final dimensions plus explicit X/Y trim allowances must divide exactly by matrix columns/rows")
    pitch, row_height = raw_x // cols, raw_y // rows
    panel_z = row_height
    strip_z = panel_z + 2 * request.shop.panel_face_removal  # prepared strip thickness
    raw_strip_z = strip_z + 2 * request.shop.z_allowance
    # After rotation slice Y becomes final Z; panel X/Y become final X/row height.
    slice_len = request.final.z + 2 * request.shop.final_face_removal
    if any(v <= 0 or v % inc for v in (pitch,row_height,strip_z,panel_z,slice_len)):
        return _fail("increment_geometry", "derived pitch, row height, and thicknesses must be positive shop increments")
    if strip_z + 2 * request.shop.z_allowance < panel_z:
        return _fail("thickness_recipe", "final Z and allowances cannot produce the required panel thickness")
    # Each visual row is an independently constructed panel. This is conservative but
    # makes all variable run widths, reversals, and finite source use explicit.
    species_by_symbol = dict(request.species)
    stock_by_species = {stock.species: stock for stock in request.stock_types}
    strip_needs: Counter[str] = Counter(cell for row in request.matrix for cell in row)
    source_counts: dict[str, int] = {}
    for symbol, count in strip_needs.items():
        stock = stock_by_species[species_by_symbol[symbol]]
        usable_width = stock.width - 2 * request.shop.x_allowance
        if usable_width < pitch + request.shop.x_allowance + request.shop.kerf or stock.thickness < raw_strip_z:
            return _fail("stock_cross_section", f"stock {stock.id} cannot produce a legal pitch-wide strip with kerf and positive rip residual")
        source_counts[stock.id] = count
        required_length = slice_len + request.shop.slice_reserve + 2*request.shop.y_allowance + 3*request.shop.kerf
        if not any(length > required_length for length in stock.available_lengths):
            return _fail("stock_length", f"stock {stock.id} has no length with positive separation reserve")
    ops: list[dict[str,Any]]=[]; segments=[]; dispositions=[]; recipes=[]; panels=[]; rows_meta=[]
    strip_ids: dict[tuple[int,int], str] = {}
    stock_indices: Counter[str] = Counter()
    # Finite inventory is consumed once, in deterministic source order.
    stock_lengths = {stock.id: list(stock.available_lengths) for stock in request.stock_types}
    def cut(opid, input_, kept, rem, axis, retained, side, category="other_offcuts"):
        ops.append({"kind":"cut","id":opid,"input":input_,"outputs":[kept,rem],"axis":axis,"retained":retained,"kerf":request.shop.kerf,"tool":"saw","category":category,"retained_side":side})
    def surf(opid, input_, out, removed, axis, side, amount, process):
        ops.append({"kind":"surface","id":opid,"input":input_,"output":out,"removed":removed,"axis":axis,"side":side,"amount":amount,"category":"milling","process":process})
    # Canonical row families share physical panels.  A panel is sliced repeatedly
    # until its finite source-length capacity is reached; no multi-strip packing is
    # claimed by this conservative allocation.
    families: dict[tuple[str, ...], list[tuple[int, bool]]] = {}
    for row_index, requested in enumerate(request.matrix):
        forward, backward = tuple(requested), tuple(reversed(requested))
        canonical = min(forward, backward)
        families.setdefault(canonical, []).append((row_index, forward != canonical))
    row_builds: dict[int, tuple[str, str, str, bool]] = {}
    panel_serial = 0
    for canonical, assignments in sorted(families.items()):
        symbols_needed = set(canonical)
        capacities = []
        for symbol in symbols_needed:
            stock = stock_by_species[species_by_symbol[symbol]]
            lengths = stock_lengths[stock.id]
            if not lengths:
                return _fail("allocation_failed", f"deterministic finite allocation exhausted {stock.id} before panel batching")
            # Source separation also needs its kerf and a positive increment-sized
            # terminal child. The blank itself carries a slicing reserve and each
            # extracted slice contributes one saw kerf.
            maximum = max((length - (2 * request.shop.y_allowance + 3 * request.shop.kerf + inc) - request.shop.slice_reserve) // (slice_len + request.shop.kerf) for length in lengths)
            capacities.append(maximum)
        capacity = min(capacities)
        if capacity < 1:
            return _fail("stock_length", "no available stock length can support one sliced panel with reserve")
        for batch_start in range(0, len(assignments), capacity):
            batch = assignments[batch_start:batch_start + capacity]
            batch_count = len(batch); panel_serial += 1
            panel=f"panel-{panel_serial}"; raw=f"{panel}-raw"; panel_strips=[]
            blank_len = batch_count * (slice_len + request.shop.kerf) + request.shop.slice_reserve
            required = blank_len + 2 * request.shop.y_allowance + 3 * request.shop.kerf
            source_minimum = required + inc
            for c, symbol in enumerate(canonical):
                stock=stock_by_species[species_by_symbol[symbol]]; stock_indices[stock.id]+=1; n=stock_indices[stock.id]
                source=f"{stock.id}-{n}"
                eligible = [(index, length) for index, length in enumerate(stock_lengths[stock.id]) if length >= source_minimum]
                if not eligible: return _fail("allocation_failed", f"deterministic finite allocation exhausted usable {stock.id} stock; another allocation may exist")
                index, length = min(eligible, key=lambda item: (item[1], item[0])); stock_lengths[stock.id].pop(index)
                sep=f"{source}-separate"; segments.append({"id":source,"stock_type":stock.id,"length":length,"boundary":"allocated_window","separation_operation":sep})
                window=f"{source}-window"; reserve=f"{source}-reserve"; cut(sep,source,window,reserve,1,required,"min"); dispositions.append({"part":reserve,"category":"other_offcuts","reusable":False})
                end1=f"{source}-end1"; endoff=f"{source}-end-min-off"; cut(f"{source}-end-min",window,end1,endoff,1,required-request.shop.y_allowance-request.shop.kerf,"max","trim"); dispositions.append({"part":endoff,"category":"trim","reusable":False})
                blank=f"{source}-blank"; endoff2=f"{source}-end-max-off"; cut(f"{source}-end-max",end1,blank,endoff2,1,blank_len,"min","trim"); dispositions.append({"part":endoff2,"category":"trim","reusable":False})
                excess = stock.thickness - strip_z; z_remove = (excess // 2 // inc) * inc; z_remove_max = excess - z_remove
                z1=f"{source}-z1"; surf(f"{source}-zmin",blank,z1,f"{source}-zmin-loss",2,"min",z_remove,"thickness_planer"); dispositions.append({"part":f"{source}-zmin-loss","category":"milling","reusable":False})
                z2=f"{source}-z2"; surf(f"{source}-zmax",z1,z2,f"{source}-zmax-loss",2,"max",z_remove_max,"thickness_planer"); dispositions.append({"part":f"{source}-zmax-loss","category":"milling","reusable":False})
                x1=f"{source}-x1"; surf(f"{source}-xmin",z2,x1,f"{source}-xmin-loss",0,"min",request.shop.x_allowance,"jointer"); dispositions.append({"part":f"{source}-xmin-loss","category":"milling","reusable":False})
                x2=f"{source}-x2"; surf(f"{source}-xmax",x1,x2,f"{source}-xmax-loss",0,"max",request.shop.x_allowance,"jointer"); dispositions.append({"part":f"{source}-xmax-loss","category":"milling","reusable":False})
                pre=f"{source}-pre"; off=f"{source}-rip-off"; cut(f"{source}-rip",x2,pre,off,0,pitch+request.shop.x_allowance,"min"); dispositions.append({"part":off,"category":"other_offcuts","reusable":False})
                final=f"{panel}-strip-{c}"; surf(f"{source}-joint",pre,final,f"{source}-joint-loss",0,"max",request.shop.x_allowance,"jointer"); dispositions.append({"part":f"{source}-joint-loss","category":"milling","reusable":False}); panel_strips.append(final)
            recipe=f"recipe-{panel_serial}"; recipes.append({"id":recipe,"cells":[species_by_symbol[x] for x in canonical]})
            # A one-column recipe is a real one-strip panel, registered by V2State
            # before its panel-face surfacing; inventing a one-input glue is illegal.
            raw = panel_strips[0] if len(panel_strips) == 1 else raw
            panels.append({"id":panel,"part":raw,"recipe":recipe,"strips":panel_strips})
            if len(panel_strips) > 1:
                ops.append({"kind":"glue","id":f"{panel}-glue","inputs":panel_strips,"output":raw,"axis":0,"stage":"first","prepared_faces":True,"negligible_glue_line":True})
            p1=f"{panel}-z1"; surf(f"{panel}-zmin",raw,p1,f"{panel}-zmin-loss",2,"min",request.shop.panel_face_removal,"thickness_planer"); dispositions.append({"part":f"{panel}-zmin-loss","category":"milling","reusable":False})
            flat=f"{panel}-flat"; surf(f"{panel}-zmax",p1,flat,f"{panel}-zmax-loss",2,"max",request.shop.panel_face_removal,"thickness_planer"); dispositions.append({"part":f"{panel}-zmax-loss","category":"milling","reusable":False})
            remainder=flat
            for local, (row_index, reversed_) in enumerate(batch):
                sl=f"slice-{row_index}"; rem=f"{panel}-remainder-{local}"; cut(f"{panel}-slice-{local}",remainder,sl,rem,1,slice_len,"min"); remainder=rem
                dispositions.append({"part":rem,"category":"other_offcuts","reusable":False}) if local == batch_count - 1 else None
                row=f"row-{row_index}"; row_builds[row_index]=(row,panel,recipe,reversed_)
                ops.append({"kind":"rotate","id":f"{row}-rotate","input":sl,"output":row,"perm":[0,2,1],"sign":[ -1,1,1] if reversed_ else [1,-1,1]})
    rows_meta=[{"rotated_part":row_builds[index][0],"panel":row_builds[index][1],"recipe":row_builds[index][2],"reversed":row_builds[index][3]} for index in range(rows)]
    ops.append({"kind":"glue","id":"final-glue","inputs":[x["rotated_part"] for x in rows_meta],"output":"board-raw","axis":1,"stage":"final","prepared_faces":True,"negligible_glue_line":True})
    f1="board-z1"; surf("final-zmin","board-raw",f1,"final-zmin-loss",2,"min",request.shop.final_face_removal,"drum_sander"); dispositions.append({"part":"final-zmin-loss","category":"milling","reusable":False})
    flat="board-flat"; surf("final-zmax",f1,flat,"final-zmax-loss",2,"max",request.shop.final_face_removal,"drum_sander"); dispositions.append({"part":"final-zmax-loss","category":"milling","reusable":False})
    tx="board-x"; cut("final-x",flat,tx,"final-x-off",0,request.final.x,"min","trim"); dispositions.append({"part":"final-x-off","category":"trim","reusable":False})
    cut("final-y",tx,"finished","final-y-off",1,request.final.y,"min","trim"); dispositions.append({"part":"final-y-off","category":"trim","reusable":False})
    stock_types=[]
    for stock in request.stock_types:
        stock_types.append({"id":stock.id,"species":stock.species,"width":stock.width,"thickness":stock.thickness,"grain":[0,1,0],"preparation":{"x_min":request.shop.x_allowance,"x_max":request.shop.x_allowance,"y_min":request.shop.y_allowance,"y_max":request.shop.y_allowance,"z_min":request.shop.z_allowance,"z_max":request.shop.z_allowance}})
    prof=lambda kerf: {"kerf":kerf,"min_input":[inc,inc,inc],"max_input":request.shop.max_workpiece}
    try:
      plan=PlanV2.model_validate({"schema_version":"cbdesign-plan/v2","title":request.title,"assumptions":["N2 exact deterministic compiler","Nominal micrometre dimensions"],"shop":{"max_workpiece":request.shop.max_workpiece,"manufacturing_increment":inc,"cutting":{"separation":prof(request.shop.kerf),"preparation":prof(request.shop.kerf),"slicing":prof(request.shop.kerf),"final_trim":prof(request.shop.kerf),"minimum_rip_width":request.shop.min_rip_width,"slice_min":slice_len,"slice_max":slice_len,"slicing_reserve":request.shop.slice_reserve,"new_face_jointing":request.shop.x_allowance},"surfacing":[{"process":"jointer","axes":[0],"min_input":[inc,inc,inc],"max_input":request.shop.max_workpiece,"glue_ready":True,"end_grain_supported":False},{"process":"thickness_planer","axes":[2],"min_input":[inc,inc,inc],"max_input":request.shop.max_workpiece,"glue_ready":True,"end_grain_supported":False},{"process":"drum_sander","axes":[2],"min_input":[inc,inc,inc],"max_input":request.shop.max_workpiece,"glue_ready":True,"end_grain_supported":True}]},"stock_types":stock_types,"source_segments":segments,"grid":{"pitch":pitch,"columns":cols,"strip_thickness":strip_z,"panel_thickness":panel_z,"slice_length":slice_len},"template":{"recipes":recipes,"panels":panels,"rows":rows_meta},"operations":ops,"finishing":{"terminal":"finished","method":"drum_sander","end_grain_supported":True},"dispositions":dispositions,"expected_final_size":[request.final.x,request.final.y,request.final.z]})
      report, rep = validate(plan)
      if report["status"] != "nominal_valid" or rep is None:
          diagnostic = report.get("coverage", {}).get("failed", [{}])[0]
          return _fail(diagnostic.get("code", "compiler_plan_invalid"), diagnostic.get("message", "generated plan did not validate"))
    except (ValueError, ReplayError) as exc:
      code=getattr(exc,"diagnostic",{}).get("code","compiler_plan_invalid"); return _fail(code,str(exc))
    metrics={"pitch_um":pitch,"row_height_um":row_height,"slice_length_um":slice_len,"strip_thickness_um":strip_z,"panels":len(panels),"source_segments":len(segments),"operations":len(ops)}
    return CompileResult(plan,report,rep,metrics)
