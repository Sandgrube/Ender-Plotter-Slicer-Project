# Raster Import Notes

Raster import converts an image into horizontal plotter lines. This is closer to hatching than to normal printer dithering.

## How it works

1. The image is converted to grayscale.
2. The grayscale image is sampled on a physical millimetre grid.
3. Each sampled pixel is converted to a darkness value.
4. Runs above the selected threshold become line segments.
5. Optional tone layers add extra lines in darker areas.

## Clean logos

Use low tone layers and a stronger threshold:

```text
Tone layers:        1
Darkness threshold: 35-60 %
Line spacing:       0.4-0.8 mm
```

## Photos

Use more tone layers and tighter spacing:

```text
Tone layers:        3-5
Darkness threshold: 20-40 %
Line spacing:       0.3-0.6 mm
```

Photo output can generate very large G-code files. Increase horizontal sample and line spacing if export becomes slow.
