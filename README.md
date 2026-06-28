# Ender Plotter Slicer

A Python/Qt desktop tool for turning vector artwork, text and raster images into pen-plotter G-code for Ender-3-style machines and the **ELEGOO Neptune 2**.

The project is intended for 3D-printer-to-plotter conversions where a pen holder is mounted to the toolhead and pen pressure is controlled through Z moves.

## Features

- 2D page layout with a millimetre grid
- Text-to-path generation
- SVG import
- PNG/JPG/BMP/WEBP/TIFF raster import
- Raster-to-line conversion based on image darkness
- Adjustable hatch density for grayscale images
- G-code preview before export
- Marlin-compatible XY/Z-only output
- Built-in profiles for:
  - ELEGOO Neptune 2 Pen Plotter
  - Ender 3 Pen Plotter
  - Ender 3 Pen Plotter Rotated Bed
- Scrollable settings panel for smaller screens
- JSON project files: `*.plotproj.json`

## Screenshots

Screenshots are not included yet. Add them later under `docs/images/` and reference them here.

## Quick start on Windows

1. Install **Python 3.10 or newer**.
2. Download or clone this repository.
3. Double-click:

```text
start_ender_plotter_slicer.bat
```

The launcher creates a local `.venv`, installs all required packages, verifies the imports and starts the app.

## Manual start

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
python -m ender_plotter_slicer
```

The old direct entry point also works:

```bash
python main.py
```

## Raster image import

Use **File → Import Image...** to import:

- PNG
- JPG / JPEG
- BMP
- WEBP
- TIFF

The app does not embed the bitmap into the G-code. It samples the brightness of the image and converts dark regions into horizontal plotter polylines.

### Important raster settings

| Setting | Meaning |
|---|---|
| Target width | Physical width of the plotted image in millimetres. |
| Max height | Maximum physical height. Aspect ratio is preserved. |
| Horizontal sample | X resolution of the sampling grid. Smaller values create more detail and larger G-code files. |
| Line spacing | Distance between scan lines. Smaller values create denser output. |
| Darkness threshold | Minimum darkness required before a segment is drawn. |
| Tone layers | Multiple darkness levels. Darker areas receive more hatch lines. |
| Contrast / Gamma | Controls how brightness is interpreted. |
| Invert brightness | Useful for bright line art on a dark background. |

Recommended starting values for clean logos or line art:

```text
Tone layers:        1
Darkness threshold: 35-60 %
Line spacing:       0.4-0.8 mm
```

Recommended starting values for photos or grayscale images:

```text
Tone layers:        3-5
Darkness threshold: 20-40 %
Line spacing:       0.3-0.6 mm
```

## ELEGOO Neptune 2 profile

The default profile is:

```text
ELEGOO Neptune 2 Pen Plotter
```

It is configured for:

- 220 × 220 mm XY work area
- 210 × 210 mm default page with safety margin
- Marlin-compatible G-code
- Z-based pen-up / pen-down movement
- Ender-3/PLTR-style pen mount conversions
- No extrusion commands during plotting

## Pen calibration

The default `Pen-down Z` is only a safe starting point. It is not automatically correct for every pen holder.

Recommended calibration procedure:

1. Home the printer.
2. Move the toolhead over the paper.
3. Lower Z slowly until the pen barely touches the paper.
4. Use that Z value as `Pen-down Z`.
5. Set `Pen-up Z` high enough that rapid XY moves do not leave marks.
6. Test with a small square before plotting a full page.

Do a dry run without a pen when testing a new profile or a new holder.

## G-code behaviour

The generated output uses only:

- absolute positioning
- millimetres
- XY travel moves
- Z pen-up / pen-down moves
- optional comments

No filament extrusion is generated. Hotend, bed and fan are disabled in the ELEGOO Neptune 2 start G-code.

## Project structure

```text
ender_plotter_slicer/
├─ ender_plotter_slicer/       Python package
│  ├─ gui/                     Qt user interface
│  ├─ gcode.py                 G-code generator
│  ├─ raster_importer.py       Raster image to line conversion
│  ├─ svg_importer.py          SVG flattening/import
│  ├─ profiles.py              Built-in machine profiles
│  └─ document.py              Project model
├─ docs/                       Extra documentation
├─ examples/                   Example input files
├─ tools/                      Smoke tests and helper scripts
├─ requirements.txt            Runtime dependencies
├─ requirements-dev.txt        Development dependencies
├─ pyproject.toml              Packaging metadata
├─ start_ender_plotter_slicer.bat
└─ start_ender_plotter_slicer.sh
```

## Development checks

```bash
python -m compileall ender_plotter_slicer
python tools/smoke_test.py
```

Optional:

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

## Safety notes

This software produces machine movement commands. Always inspect the preview and the exported G-code before running it on real hardware. Keep the first run slow, stay near the printer and make sure the pen holder cannot crash into clips, bed screws or the frame.

## License

MIT License. See [`LICENSE`](LICENSE).
