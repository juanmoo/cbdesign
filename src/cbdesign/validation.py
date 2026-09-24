"""Public validation result with explicit nominal-only coverage semantics."""
from __future__ import annotations
from .models import Plan
from .replay import replay, ReplayError


def validate(plan: Plan) -> tuple[dict, object | None]:
    profile_checks = {
        "declared_saw_kerf": plan.shop.saw_kerf,
        "declared_workpiece_capacity": plan.shop.max_workpiece,
        "declared_slice_length_limit": plan.shop.max_slice_length,
    }
    checked_profile = [name for name, value in profile_checks.items() if value is not None]
    not_evaluated = [
        "interval_uncertainty_propagation", "physical_machine_safety", "joint_strength",
        "finite_inventory", "optimization", "minimum_handling_dimensions",
        "terminal_slicing_reserve", "rough_stock_preparation_allowances",
        *[name for name, value in profile_checks.items() if value is None],
    ]
    scope = "M1 nominal geometry and declared-profile checks only"
    if plan.schema_version == "cbdesign-plan/v2":
        scope = "N1 nominal rough-stock fabrication and required-profile checks only"
        checked_profile = [
            "declared_workpiece_capacity", "stage_specific_kerfs",
            "minimum_handling_dimensions", "terminal_slicing_reserve",
            "rough_stock_preparation_allowances", "operation_derived_face_preparation",
            "fixed_stock_cross_sections", "source_separation",
            "uniform_grid", "physical_panel_assignments", "visual_recipe_cells",
            "surfacing_process_capabilities",
        ]
        not_evaluated = [
            "interval_uncertainty_propagation", "physical_machine_safety", "joint_strength",
            "finite_inventory", "optimization",
        ]
    try:
        result = replay(plan)
        ledger = result.ledger()
        return ({
            "status": "nominal_valid",
            "scope": scope,
            "warning": "Uncertainty propagation, machining-error bounds, physical safety, and structural-joint certification are not evaluated.",
            "coverage": {"passed": ["strict_schema", "topological_operations", "exact_geometry", "source_provenance_partition", "terminal_disposition", "proper_rotations", "glue_compatibility", "construction_template", "final_dimensions", "end_grain_exposure", "increment", *checked_profile], "failed": [], "not_evaluated": not_evaluated},
            "final": {"part": result.terminal, "size_um": list(result.parts[result.terminal].size), "species_volumes": {k:v["finished"] for k,v in ledger["species"].items()}},
            "operations": result.operations,
            "joints": result.joints,
        }, result)
    except ReplayError as error:
        return ({"status": "invalid", "scope": scope, "coverage": {"passed": [], "failed": [error.diagnostic], "not_evaluated": not_evaluated}}, None)
