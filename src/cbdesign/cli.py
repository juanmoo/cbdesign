from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from pydantic import ValidationError
from .models import Plan
from .validation import validate
from .render_svg import board_svg, panels_svg

GENERATED_FILES = frozenset({"validation.json", "material-ledger.json", "board.svg", "panels.svg", "operations.txt"})


def _safe_output_directory(plan_path: Path, output: Path, overwrite: bool) -> tuple[bool, str | None]:
    """Validate a report target without ever deleting a user directory."""
    plan_resolved = plan_path.resolve(strict=True)
    output_resolved = output.resolve(strict=False)
    if output_resolved == plan_resolved or output_resolved in plan_resolved.parents:
        return False, "output directory must not be the plan file or an ancestor containing it"
    if output.exists():
        if output.is_symlink() or not output.is_dir():
            return False, "output path must be a real directory, not a file or symlink"
        if not overwrite:
            return False, "refusing to replace existing output; use --overwrite to replace only cbdesign-generated files"
        for name in GENERATED_FILES:
            candidate = output / name
            if candidate.exists() and (candidate.is_symlink() or not candidate.is_file()):
                return False, f"refusing to replace colliding generated name {name!r}: it is not a regular file"
    return True, None


def _operations_text(operations: list[dict]) -> str:
    lines = ["Nominal replay operation report (dimensions are integer micrometres)."]
    for op in operations:
        common = f"{op['id']} [{op['kind']}]: inputs={','.join(op['inputs'])}; outputs={','.join(op['outputs'])}"
        details = "; ".join(f"{key}={value}" for key, value in op.items() if key not in {"id", "kind", "inputs", "outputs"})
        lines.append(f"{common}; {details}" if details else common)
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cbdesign", description="Nominal-only fabrication-plan replay")
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate")
    v.add_argument("plan", type=Path)
    v.add_argument("--output", type=Path, required=True)
    v.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        raw = json.loads(args.plan.read_text())
        plan = Plan.from_json_obj(raw)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(json.dumps({"status": "invalid_schema", "error": str(error), "output": "No output artifacts were modified."}, indent=2))
        return 2
    report, result = validate(plan)
    if report["status"] != "nominal_valid":
        report["output"] = "Validation failed; existing output artifacts were not modified."
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1
    safe, message = _safe_output_directory(args.plan, args.output, args.overwrite)
    if not safe:
        print(json.dumps({"status": "output_rejected", "message": message, "output": "No output artifacts were modified."}, indent=2))
        return 2
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    # Only known regular files may be replaced. Unrelated files are deliberately preserved.
    if args.overwrite:
        for name in GENERATED_FILES:
            candidate = output / name
            if candidate.exists():
                os.unlink(candidate)
    (output / "validation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (output / "material-ledger.json").write_text(json.dumps(result.ledger(), indent=2, sort_keys=True) + "\n")
    (output / "board.svg").write_text(board_svg(result))
    (output / "panels.svg").write_text(panels_svg(result))
    (output / "operations.txt").write_text(_operations_text(result.operations))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0
