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
```

## Packaging smoke test

```bash
pip install -e .
ender-plotter-slicer
```
