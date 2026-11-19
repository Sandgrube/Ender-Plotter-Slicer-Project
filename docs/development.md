# Development

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate  # Windows
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Run

```bash
python -m ender_plotter_slicer
```

## Checks

```bash
python -m compileall ender_plotter_slicer
python tools/smoke_test.py
ruff check .
pytest -q
python tools/render_pencil_demo.py
```

## Packaging smoke test

```bash
pip install -e .
ender-plotter-slicer
```

## Pencil rendering checks

`tests/test_raster.py` checks continuous tone against a 32-patch grayscale reference, multiple hatch directions, preserved white holes, transparent backgrounds, EXIF orientation, deterministic curved strokes, cancellation, resource guards and project round trips.

`tests/test_gcode.py` checks exact ordering against a brute-force reference, pen lifts across highlight gaps, closed contours, the first drawing move, endpoint retention, fixed Z values, optional short lifts and motion-time accounting.

`tests/test_raster_dialog.py` uses offscreen Qt to check preview/import consistency, invalidation after settings changes and cancellation before worker destruction. No plotter is driven by these checks.

Rebuild `docs/images/pencil_comparison.png` with `python tools/render_pencil_demo.py` after changing the rendering algorithm. Inspect the image as well as the numerical checks. The generated source is an analytically shaded scene, so it requires no external image asset.
