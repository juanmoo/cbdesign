"""Metrics calculated from a compiled plan and its independently replayed result."""
from __future__ import annotations

from collections import Counter
from typing import Any

from .models_v2 import PlanV2
from .replay import Replay


def plan_metrics(plan: PlanV2, result: Replay) -> dict[str, Any]:
    """Return physical source, joint, and saw metrics for a replayed plan.

    Values use the plan's micrometre units: volumes are ``um3`` and glue-face
    areas are ``um2``.  They deliberately come from the emitted operations and
    source segments, rather than a search recipe estimate.
    """
    stock = {item.id: item for item in plan.stock_types}
    source_volume = 0
    source_by_species: Counter[str] = Counter()
    for segment in plan.source_segments:
        item = stock[segment.stock_type]
        volume = int(item.width) * int(segment.length) * int(item.thickness)
        source_volume += volume
        source_by_species[item.species] += volume

    # The replay log records the commands that actually executed.  In particular,
    # its lowercase ``kind`` is stable across the V2 operation model variants.
    saw_records = [operation for operation in result.operations if operation["kind"] == "cut"]
    saw_cuts = len(saw_records)
    saw_kerf_volume = sum(operation["kerf_volume_um3"] for operation in saw_records)
    # Joints are captured while replay still has both physical glue inputs, before
    # they are consumed.  Their areas therefore remain available after assembly.
    joint_count = len(result.joints)
    joint_area = sum(joint["area"] for joint in result.joints)

    terminal = result.parts[result.terminal]
    retained_volume = terminal.volume
    # Singleton panels register without a fictitious first-stage glue operation.
    panels = plan.template.panels
    glueups = [operation for operation in result.operations if operation["kind"] == "glue"]
    joints_by_stage = Counter(joint["stage"] for joint in result.joints)
    joint_area_by_stage = Counter()
    for joint in result.joints:
        joint_area_by_stage[joint["stage"]] += joint["area"]
    saw_settings = Counter()
    for operation in saw_records:
        key = (operation["axis"], operation["tool"], operation["retained_um"], operation["kerf_um"])
        saw_settings[key] += 1
    losses = Counter()
    for category, regions in result.losses.items():
        losses[category] = sum(region.volume for region in regions)
    capacities = tuple(int(value) for value in plan.shop.max_workpiece)
    # Include consumed intermediate panels, not only terminal/offcut parts.
    observed_sizes = [size for operation in result.operations
                      for size in operation['output_sizes_um'].values()]
    observed_sizes.extend((int(stock[segment.stock_type].width), int(segment.length),
                           int(stock[segment.stock_type].thickness))
                          for segment in plan.source_segments)
    min_capacity_margin = [min(capacities[axis] - size[axis] for size in observed_sizes)
                           for axis in range(3)]
    return {
        "source_segments": len(plan.source_segments),
        "source_volume_um3": source_volume,
        "source_volume_by_species_um3": dict(sorted(source_by_species.items())),
        "retained_volume_um3": retained_volume,
        "waste_volume_um3": source_volume - retained_volume,
        "loss_volume_by_category_um3": dict(sorted(losses.items())),
        "saw_cuts": saw_cuts,
        "saw_kerf_volume_um3": saw_kerf_volume,
        "saw_settings": [
            {"axis": axis, "tool": tool, "retained_um": retained, "kerf_um": kerf, "count": count}
            for (axis, tool, retained, kerf), count in sorted(saw_settings.items())
        ],
        "panels": len(panels),
        "glueups": len(glueups),
        "joint_count": joint_count,
        "joint_area_um2": joint_area,
        "joints_by_stage": dict(sorted(joints_by_stage.items())),
        "joint_area_by_stage_um2": dict(sorted(joint_area_by_stage.items())),
        "max_workpiece_margin_um": min_capacity_margin,
        "operations": len(plan.operations),
    }
