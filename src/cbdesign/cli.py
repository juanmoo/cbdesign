from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from dataclasses import asdict
from pydantic import ValidationError
from .models import load_plan
from .validation import validate
from .bundle import REPORT_FILES, json_bytes, operations_text, plan_bundle, zip_bundle

GENERATED_FILES = REPORT_FILES | {'request.json', 'search.json', 'target.json', 'metrics.json'} | {f'candidate-{i:03d}.zip' for i in range(1, 257)}
_operations_text = operations_text


def _safe_output_directory(plan_path: Path, output: Path, overwrite: bool) -> tuple[bool, str | None]:
    """Validate a report target without ever deleting a user directory."""
    plan_resolved = plan_path.resolve(strict=True)
    output_resolved = output.resolve(strict=False)
    if output_resolved == plan_resolved or output_resolved in plan_resolved.parents:
        return False, 'output directory must not be the input file or an ancestor containing it'
    if output.is_symlink():
        return False, 'output path must be a real directory, not a file or symlink'
    if output.exists():
        if not output.is_dir():
            return False, 'output path must be a real directory, not a file or symlink'
        if not overwrite:
            return False, 'refusing to replace existing output; use --overwrite to replace only cbdesign-generated files'
        for name in GENERATED_FILES:
            candidate = output / name
            if candidate.is_symlink() or (candidate.exists() and not candidate.is_file()):
                return False, f'refusing to replace colliding generated name {name!r}: it is not a regular file'
    return True, None


def _write_output(inputs, output, overwrite, files):
    for source in inputs:
        safe, message = _safe_output_directory(source, output, overwrite)
        if not safe:
            raise ValueError(message)
        if source.resolve() in {(output / name).resolve() for name in GENERATED_FILES}:
            raise ValueError('output would overwrite an input file')
    # Render all reports before this point so rendering failures leave old output intact.
    output.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for name in GENERATED_FILES:
            candidate = output / name
            if candidate.exists():
                os.unlink(candidate)
    for name, content in files.items():
        (output / name).write_bytes(content)


def _json(path):
    return json.loads(path.read_text())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='cbdesign', description='Nominal end-grain design and independent fabrication-plan replay')
    sub = parser.add_subparsers(dest='command', required=True)
    for command, input_name in [('validate', 'plan'), ('generate', 'request'), ('search', 'request')]:
        p = sub.add_parser(command)
        p.add_argument(input_name, type=Path)
        p.add_argument('--output', type=Path, required=True)
        p.add_argument('--overwrite', action='store_true')
        if command == 'validate':
            p.add_argument('--uncertainty', type=Path, help='Digest-bound dimensional declaration; nominal status stays separate')
        if command == 'search':
            p.add_argument('--target', type=Path, help='PNG target covering the finished rectangle')
            p.add_argument('--threshold', type=int, default=128)
            p.add_argument('--recipes', type=int, default=4)
            p.add_argument('--work-budget', type=int, default=32)
            p.add_argument('--seed', type=int, default=0)
            p.add_argument('--grid', action='append', metavar='ROWSxCOLS', help='Repeat to compare explicit grids; default uses request grid')
    demo = sub.add_parser('demo', help='Write an illustrative design request to stdout')
    demo.add_argument('--pattern', default='checkerboard', choices=['checkerboard', 'stripes', 'diamond', 'basket_weave', 'letter', 'asymmetric', 'unrelated', 'mouse_head'])
    serve_parser = sub.add_parser('serve', help='Launch the loopback-only browser interface')
    serve_parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.command == 'serve':
            from .web import serve
            serve(port=args.port)
            return 0
        if args.command == 'demo':
            from .design import illustrative_request
            from . import patterns
            target = getattr(patterns, args.pattern)()
            from .target import target_occupancy
            from fractions import Fraction
            matrix = [['B' if v >= Fraction(1, 2) else 'A' for v in row] for row in target_occupancy(target, 12, 12)]
            print(json_bytes(illustrative_request(matrix).model_dump(mode='json')).decode(), end='')
            return 0
        source = getattr(args, 'plan', None) or args.request
        inputs = [source]
        if args.command == 'validate':
            plan = load_plan(_json(source))
            report, result = validate(plan)
            if result is None:
                print(json_bytes(report).decode(), end='')
                return 1
            uncertainty = None
            if args.uncertainty:
                from .uncertainty import validate_uncertainty
                inputs.append(args.uncertainty)
                uncertainty = validate_uncertainty(plan, _json(args.uncertainty))
            files = plan_bundle(plan, report, result, uncertainty)
            status = report
            exit_code = 1 if uncertainty and uncertainty['status'] != 'dimensionally_valid' else 0
        else:
            from .design import DesignRequest
            request = DesignRequest.model_validate(_json(source))
            files = {'request.json': json_bytes(request.model_dump(mode='json'))}
            if args.command == 'generate':
                from .compiler import compile_design
                result = compile_design(request)
                if result.plan is None:
                    print(json_bytes({'status': 'not_compiled', 'error': str(result.error), 'report': result.report}).decode(), end='')
                    return 1
                files.update(plan_bundle(result.plan, result.report, result.replay))
                files['metrics.json'] = json_bytes(result.metrics)
                status = {'status': 'nominal_valid', 'metrics': result.metrics}
            else:
                from .search import SearchSettings, search_design
                from .target import decode_png
                target = None
                if args.target:
                    inputs.append(args.target)
                    target = decode_png(args.target, threshold=args.threshold)
                grids = tuple(tuple(int(v) for v in grid.lower().split('x')) for grid in args.grid) if args.grid else ((len(request.matrix), len(request.matrix[0])),)
                settings = SearchSettings(recipe_budget=args.recipes, grid_dimensions=grids, work_budget=args.work_budget, seed=args.seed)
                result = search_design(request, target, settings)
                status = {'status': 'validated_alternatives' if result.candidates else 'no_validated_candidate', 'termination': result.termination,
                          'attempted': result.attempted, 'compiled': result.compiled, 'rejected': result.rejected,
                          'settings': asdict(settings), 'candidates': []}
                for index, candidate in enumerate(result.candidates, 1):
                    name = f'candidate-{index:03d}.zip'
                    compiled = candidate.compile_result
                    bundle = plan_bundle(compiled.plan, compiled.report, compiled.replay)
                    bundle['request.json'] = json_bytes(candidate.request.model_dump(mode='json'))
                    bundle['metrics.json'] = json_bytes(candidate.metrics)
                    files[name] = zip_bundle(bundle)
                    status['candidates'].append({'file': name, 'label': candidate.label, 'mismatch_fraction': str(candidate.score),
                                                  'grid': candidate.grid, 'recipe_families': candidate.recipe_families, 'metrics': candidate.metrics})
                files['target.json'] = json_bytes(result.target.as_dict())
                files['search.json'] = json_bytes(status)
            exit_code = 0 if args.command == 'generate' or result.candidates else 1
        _write_output(inputs, args.output, args.overwrite, files)
        print(json_bytes(status).decode(), end='')
        return exit_code
    except (OSError, json.JSONDecodeError, ValidationError, ValueError, TypeError) as error:
        print(json_bytes({'status': 'input_or_output_rejected', 'error': str(error)}).decode(), end='')
        return 2
