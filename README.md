# cbdesign

`cbdesign` is a local **bitmap-to-end-grain-board planning workbench**. It generates two-species plans from binary grids, searches bounded recipe alternatives, independently replays fabrication geometry, and exports diagrams, material accounting, CSV and PDF reports. Legacy hand-authored v1/v2 plans remain supported.

**Planning software, not shop instructions:** nominal validation and optional conservative dimensional bounds do not certify machine safety, joint strength, wood stability, or actual fabrication.

It independently reconstructs strict versioned JSON plans from finite stock boxes; replays full-span cuts, face-specific removals, proper rigid rotations, and ordered full-face glue-ups; preserves species/grain/source provenance; enforces the restricted two-species, two-stage intact-slice construction template; and produces an exact per-species material ledger plus SVG views.

## Implementation plan

See the **[current completion status](docs/implementation-status.md)** for verified gates and remaining limitations, and the [original roadmap](docs/implementation-roadmap.md) for the broader acceptance criteria.

- **N1/N2:** independent rough-stock replay and deterministic exact compilation, finite inventory and canonical panel batching.
- **N3:** bounded recipe/grid search, exact retained-area mismatch and replay-derived fabrication trade-offs.
- **F1/F2/F3:** opt-in dimensional-bound sidecars, loopback browser workflow, PNG/project import and PDF/CSV/SVG/JSON exports.

## Install and run

Python 3.12+ is required. Use a project-local environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m cbdesign validate examples/checkerboard.json --output /tmp/checkerboard
.venv/bin/python -m cbdesign validate examples/asymmetric-board.json --output /tmp/asymmetric
.venv/bin/python -m cbdesign validate examples/rough-stock-board.json --output /tmp/rough-stock
.venv/bin/pytest
```

### Browser demo — no JSON editing

```bash
.venv/bin/cbdesign serve --port 8765
```

Open **http://127.0.0.1:8765**. Choose a built-in pattern or upload [`mouse-head.png`](examples/targets/mouse-head.png), leave the illustrative 12×12 target grid and 290×290×30 mm board defaults, and select **Search alternatives**. Compare achieved boards and mismatch views, inspect metrics, download a fabrication ZIP, or save/reload a JSON project. Wood quantities and dimensions are editable under **Wood & shop settings**. Values in the forms are micrometres, not millimetres. The service binds only to loopback and uses no cloud service.

### Follow the fabrication replay

Select **Replay steps** on an alternative to start with its stock overview, then use Previous/Next or the step selector. The walkthrough includes **every cut, surface preparation, rotation and glue-up**, with before/after geometry, dimensions in millimetres, grain orientation and part links to earlier/later operations. Operation numbers and cumulative saw-pass counts are separate.

The two configured **stock types** define fixed width × thickness cross-sections. The current allocator consumes multiple finite **source segments** of those types; it does not model cutting them from two parent boards. The stripe example uses 24 source segments and 110 saw passes across 251 operations. This allocation is unchanged and remains conservative: one source per strip, without automatic offcut reuse. A cut remainder used later is distinguished from a terminal offcut.

The downloaded ZIP also includes **`replay.html`**, a self-contained walkthrough that opens offline. Very large walkthroughs produce an explicit limit notice rather than a truncated sequence; the complete plan and operation CSV remain available. These are nominal geometry diagrams, not machine setup or safety instructions.

### CLI generation and search

```bash
.venv/bin/cbdesign demo --pattern checkerboard > /tmp/board-request.json
.venv/bin/cbdesign generate /tmp/board-request.json --output /tmp/generated-board
.venv/bin/cbdesign search /tmp/board-request.json \
  --target examples/targets/mouse-head.png --recipes 8 --work-budget 32 \
  --output /tmp/mouse-alternatives
```

The common bundle contains `plan.json`, `validation.json`, `material-ledger.json`, `board.svg`, `panels.svg`, `stock.svg`, `operations.txt`, `operations.csv`, `material.csv`, `report.pdf`, and the offline `replay.html` walkthrough. Search adds frozen request/target snapshots, metrics and a ZIP per retained alternative. It refuses to overwrite an output directory unless `--overwrite` is supplied and preserves unrelated filenames. Nominal replay failures do not replace existing reports.

The [common-pattern gallery](examples/gallery/README.md) contains checkerboard, stripes, stepped diamond, basket-weave-style grid, block letter, asymmetric, unrelated-row and mouse-head examples. Regenerate the measured corpus with:

```bash
.venv/bin/python scripts/regenerate_gallery.py --write-fixtures --regenerate
```

`--write-fixtures` deliberately replaces the illustrative input fixtures; omit it to benchmark existing frozen inputs.

## Visual smoke tests

These are tiny synthetic geometry fixtures, **not full-size shop-ready board designs**. Images below are generated by the real CLI from the checked-in example plans; thin lines show physical region boundaries, including same-species joins.

| Reversed-row checkerboard — 20 × 64 × 18 mm | Asymmetric, saw-trimmed board — 15 × 64 × 18 mm |
| --- | --- |
| ![Checkerboard replay](docs/previews/checkerboard/board.png) | ![Asymmetric replay](docs/previews/asymmetric-board/board.png) |

First-stage panels: [checkerboard](docs/previews/checkerboard/panels.png) · [asymmetric](docs/previews/asymmetric-board/panels.png).

Inspect the generated [checkerboard reports](docs/previews/checkerboard/) or [asymmetric reports](docs/previews/asymmetric-board/) for SVGs, operation lists, validation coverage, and exact material ledgers.

To regenerate the tracked report bundles:

```bash
.venv/bin/python -m cbdesign validate examples/checkerboard.json --output docs/previews/checkerboard --overwrite
.venv/bin/python -m cbdesign validate examples/asymmetric-board.json --output docs/previews/asymmetric-board --overwrite
```

PNG snapshots additionally use the optional preview tool `cairosvg` (not a runtime dependency):

```bash
.venv/bin/pip install cairosvg
.venv/bin/python -c 'from pathlib import Path; import cairosvg; [cairosvg.svg2png(url=str(p), write_to=str(p.with_suffix(".png")), background_color="white", output_width=900) for p in Path("docs/previews").glob("*/*.svg")]'
```

## Rough-stock reference

The [v2 reference plan](examples/rough-stock-board.json) starts with six maple and four walnut finite rough segments of unequal cross-sections. It records both end trims, thickness/edge preparation, explicit rips and fresh-face jointing, three physical panels across two visual recipes, twelve normal/reversed rows, slicing reserves, and final finishing/trim.

**Finished size: 290 × 290 × 30 mm.** The independent [dimension chain and per-species ledger](docs/decisions/0002-rough-stock-contract.md) expect 54 saw passes, 17 first-stage joints, and 11 final-row joints. Same-species physical subdivisions remain visible even inside one visual run.

![Rough-stock reference board](docs/previews/rough-stock-board/board.png)

[Panels](docs/previews/rough-stock-board/panels.png) · [Stock breakdown](docs/previews/rough-stock-board/stock.svg) · [Reports](docs/previews/rough-stock-board/). Stock diagrams show exploded source-Z layers, not overlapping material counted twice. All shop settings are illustrative; this is not a fabrication certificate.

Regenerate all bundles with `.venv/bin/python scripts/regenerate_previews.py`; add `--png` with CairoSVG installed to update raster previews. The [CI workflow](.github/workflows/tests.yml) configures tests, wheel build and CLI smoke runs for Python 3.12 and 3.13; a checked-in workflow is not evidence of a successful remote run.

## Version-specific validation boundary

A `nominal_valid` result means the recorded plan passed exact nominal geometry, declared-profile, provenance partition, terminal-disposition, final-dimension, end-grain, and version-specific construction checks. It is **not** a fabrication certificate, machine instruction, safety assessment, joint-strength assessment, or actual-dimension guarantee. Neither plan schema embeds uncertainty bounds. An optional [digest-bound dimensional sidecar](docs/decisions/0004-dimensional-bounds.md) propagates exact affine bounds separately; unsupported semantics or unresolved all-realizations glue compatibility prevent a dimensional-valid label.

- **V1:** the tiny checkerboard/asymmetric fixtures begin with prepared strips. Optional saw-kerf, workpiece-capacity and slice-length checks are reported as passed only when supplied. Handling minima, slicing reserves and rough preparation remain explicitly `not_evaluated` for this version.
- **V2:** the rough-stock fixture requires stock types, finite source separation, six-face preparation allowances, stage-specific kerfs/feed minima/capacities, slicing reserves, supported surfacing processes, and independent physical-panel/visual-cell metadata. Missing required fields fail schema validation; declaration alone cannot establish prepared faces.

Synthetic examples and profiles are examples only, not universal safe defaults. Final end-grain finishing must use a declared supported process; no ordinary planer suitability is assumed.

See [plan format](docs/plan-format.md), [fabrication model](docs/fabrication-model.md), and [acceptance criteria](docs/acceptance-and-validation.md).

## Limits and remaining work

- The exact request grid describes the **pre-trim** board. Explicit X/Y trim amounts crop its maximum edges; dimensions must divide into exact manufacturing increments. Bitmap search instead fixes the target across the finished rectangle and scores actual retained replay geometry.
- Canonical rows share capacity-bounded panels. Allocation consumes finite source entries deterministically, but conservatively uses one source per whole-cell strip; it does not pack multiple strips into each source or optimize purchasing/offcut reuse.
- Search is a bounded heuristic, not a global optimizer. Exhaustion or no candidate is not proof that fabrication is impossible. Time/cancellation checks occur between candidate evaluations, not during one replay.
- All supplied wood/tool dimensions are **illustrative**, not measurements or safe-machine defaults. Nonzero dimensional bounds require explicit named declarations; the zero-width sidecar helper is only a format demonstration.
- Physical expert review, fabrication/measurement, strength/safety certification, wood movement, probabilistic yield and broader construction families remain outside this software release.
