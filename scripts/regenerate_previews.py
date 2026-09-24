#!/usr/bin/env python3
"""Regenerate checked-in SVG validation previews from every example plan.

Run from any working directory.  The script calls the public CLI for every fixture,
so preview generation exercises the same validation and report-writing path users
receive.  Pass ``--png`` only when CairoSVG is installed to also write PNG previews.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
PREVIEWS = ROOT / "docs" / "previews"


def _render_png(folder: Path) -> None:
    try:
        import cairosvg
    except ImportError as error:
        raise SystemExit("--png requires CairoSVG; install it separately and retry") from error
    for name in ("board", "panels", "stock"):
        svg = folder / f"{name}.svg"
        if svg.exists():
            cairosvg.svg2png(url=str(svg), write_to=str(folder / f"{name}.png"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate nominal validation previews")
    parser.add_argument("--png", action="store_true", help="also render SVG previews to PNG with CairoSVG")
    args = parser.parse_args(argv)
    fixtures = sorted(EXAMPLES.glob("*.json"))
    if not fixtures:
        raise SystemExit(f"no JSON fixtures found in {EXAMPLES}")
    for fixture in fixtures:
        output = PREVIEWS / fixture.stem
        if args.png:
            for name in ("board.png", "panels.png", "stock.png"):
                target = output / name
                if target.is_symlink() or (target.exists() and not target.is_file()):
                    raise SystemExit(f"refusing to replace nonregular preview target: {target}")
        command = [sys.executable, "-m", "cbdesign", "validate", str(fixture), "--output", str(output), "--overwrite"]
        completed = subprocess.run(command, cwd=ROOT)
        if completed.returncode:
            return completed.returncode
        if args.png:
            _render_png(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
