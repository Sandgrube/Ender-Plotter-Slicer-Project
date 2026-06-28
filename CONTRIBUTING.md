# Contributing

Contributions are welcome.

## Basic workflow

1. Fork the repository.
2. Create a feature branch.
3. Keep changes focused.
4. Run the smoke test before opening a pull request.

```bash
python -m compileall ender_plotter_slicer
python tools/smoke_test.py
```

## Code style

The codebase uses plain Python with PySide6 for the GUI. Keep UI strings in English and avoid adding machine-specific assumptions without exposing them as profile settings.
