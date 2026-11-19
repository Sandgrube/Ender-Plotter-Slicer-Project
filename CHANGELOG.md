# Changelog

## 1.2.0

- Added continuous-tone, multi-angle pencil crosshatching and form-following curved strokes.
- Added pencil and portrait presets, physical stroke-width calibration, graphite opacity and noise smoothing.
- Added side-by-side source / actual-path preview, background conversion, cancellation and resource limits.
- Added saved raster settings and an action to adjust existing hatch geometry.
- Preserved transparent backgrounds, EXIF orientation and small highlight gaps during import and export.
- Replaced the quadratic nearest-path search with an exact deletable k-d tree.
- Added an optional Pen-up-only travel strategy and motion-time lower bounds including Z lifts.
- Reduced export preview graphics to two path items, hid travel by default and bounded the G-code text preview.
- Corrected machine-preview Y orientation and fit the complete work area after resizing.
- Fixed skipped first-path starts, missing closed-path edges and dropped short endpoints.
- Added regression tests and a reproducible visual comparison for pencil output.

## 1.1.0

- Added raster image import for PNG, JPEG, BMP, WEBP and TIFF.
- Added darkness-based raster-to-polyline conversion.
- Added configurable tone layers for denser hatching in dark image areas.
- Added a scrollable settings panel.
- Added ELEGOO Neptune 2 Pen Plotter as the default profile.
- Added GitHub-ready project files and documentation.

## 1.0.0

- Initial SVG/text layout and G-code export workflow.
