# Labelate

A desktop label template editor built with **QPUIQ 1.8** and its PySide6 backend.
The canvas is on the left, with a black background outside the label; the right
panel contains **Label**, **Objects**, and **Variables**, in that order. The
Pillow renderer also works without a GUI.

## Installation and launch

Use Python 3.10 or later with a compatible PySide6 wheel (Python 3.12 recommended).

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
labelate
# Alternatively:
python -m labelate
# Or run the package directory from the repository root:
python3 labelate
```

## Editing labels

- Choose a label preset or enter custom width and height, DPI, and monochrome or
  color mode. The preset selector appears above the unit selector. Choose from
  25 sizes spanning 20 × 10 to 100 × 150 mm and 1 × 1 to 4 × 8 in.
  Switch between **mm**, **cm**, and **in** without changing physical size.
  Unit, width, height, and **Rotate** share one row; DPI and mode share the next.
  **Rotate** swaps the label dimensions while retaining object positions and sizes.
- Add text, image, QR code, Code 128, or Rect objects. Click an object on the canvas or
  in the list to select it, then drag it or edit its position and size.
- Content is applied automatically when the field loses focus. Text supports multiple lines, font
  files (`.ttf`, `.otf`, `.ttc`), point sizes, and a color picker in color mode.
  Style offers `normal`/`italic`, and weight offers `normal`/`bold`. These are
  saved as `font_style` and `font_weight`; older templates default to normal.
  Bold uses a proportional stroke and italic a 12-degree slant, applied to the
  selected font in both preview and export (including custom font files).
  Text is clipped to its object box; it does not automatically wrap or shrink.
- Rect objects have width, height, line width, and corner radius R in the selected
  unit. They draw a black outline with a transparent interior. R = 0 gives square
  corners; rendering caps radius and stroke at half the shorter side. JSON stores
  line width as `stroke_mm` and radius as `radius_mm`.
- Images preserve aspect ratio. **Choose image** opens a file picker; the image
  properties show the selected path instead of a Content field. Only the path is
  saved, relative to the JSON file location. Opening a template resolves image
  paths against that location; Save as recalculates them for the new location.
  Keep the referenced image files with your template. Base64 embedding is not supported.
- Use placeholders such as `{name}`, `{sku}`, or `{image_path}` in any object's
  content. The Variables panel is derived from those placeholders and removes
  unused names. Enter preview/default values there; commit a field with Enter or
  by moving focus. Names follow `[A-Za-z_][A-Za-z0-9_]*` and are case-sensitive.
- Save/open JSON templates and export PNG images with DPI metadata. New, Open,
  and window close prompt when there are unsaved model changes. Save and export
  also commit pending content edits.

Objects render in list order, with later objects on top. Geometry outside the
label is clipped in exported images. Invalid objects appear as red boxes in the
editor, with an explanation below the canvas; export reports an error rather
than silently omitting them. QR codes and Code 128 use whole-pixel modules and
quiet zones. Increase object dimensions or DPI if a code cannot fit. Code 128
supports non-empty ASCII content and does not add a human-readable caption.

## Python rendering API

```python
from pathlib import Path
from labelate import render

json_string = Path('examples/product.json').read_text(encoding='utf-8')
image = render(json_string, {'name': 'Coffee', 'sku': 'ABC123'})
image.save('label.png', dpi=image.info['dpi'])
```

`render(json_string, {key: value})` returns a `PIL.Image.Image`: mode `1` for
monochrome labels or `RGB` for color labels. Monochrome output uses a fixed 128
threshold, without dithering. Explicit variables override defaults saved in the
template; values are converted to strings. Missing variables, invalid templates,
unreadable assets, and codes that do not fit raise `ValueError`. An empty saved
default counts as a supplied value. No display server or QApplication is needed.

The standalone `render(json_string, variables)` API has no JSON file location,
so relative image and font paths resolve against the process working directory.
Run it from the template directory or resolve image paths before rendering.
The GUI resolves image paths automatically when opening JSON. Font files are not embedded;
install or copy custom fonts on every rendering machine. The default renderer
tries platform fonts, then Pillow's fallback. For consistent typography and CJK
coverage, select the same suitable font file on each machine.

## JSON format

Version 1 stores all geometry in **millimetres**, regardless of the selected
display unit. `canvas.unit` only controls editor presentation. Font sizes use
points (1/72 inch). Pixel dimensions are rounded from `mm * dpi / 25.4`.

```json
{
  "version": 1,
  "canvas": {
    "width_mm": 100, "height_mm": 60,
    "dpi": 300, "mode": "mono", "unit": "mm"
  },
  "objects": [
    {
      "id": "title", "type": "text",
      "x_mm": 5, "y_mm": 5, "width_mm": 80, "height_mm": 12,
      "content": "{name}", "font": "", "font_size": 18,
      "color": "#000000"
    }
  ],
  "variables": {"name": "Coffee"}
}
```

Object types are `text`, `image`, `qr`, `code128`, and `rect`. Image content accepts a
local file path (stored in the image object's `content` key). Canvas mode is `mono` or `color`;
unit is `mm`, `cm`, or `in`. The model limits individual canvas/object allocations to
40 million pixels. Templates should come from trusted sources: image/font paths
are local file references.

## Development

```sh
python -m pytest -q
```

Tests cover JSON validation and round trips, units and output dimensions,
variable discovery and overrides, all five object renderers, image paths,
error handling, and the QPUIQ/Qt lifecycle with selection and movement. GUI tests
use Qt's offscreen platform.

The GUI is declared with QPUIQ 1.8: `Application`, `Window`, `VBox`, `HBox`,
`Splitter`, `Scroll`, `Button`, `Label`, `TextField`, `TextEdit`, `ComboBox`, and
`Canvas`. PUI State invalidates the view, and value bindings validate edits before
updating the JSON model. Canvas drawing and drag events also use PUI APIs.
Numeric inputs commit on Enter or blur and report invalid values in the status
line. Multiline content commits on blur; save/export also commit pending drafts.

Unsaved changes use PUI `Confirm`: first ask whether to save, then, if declined,
ask whether to discard. Declining both cancels the operation.

`labelate.native` contains only the Qt adapters for a window-close veto and
the color picker, which have no matching
public PUI 1.8 API. There are no native Qt editor layouts or custom widget nodes.
`labelate.model` owns the JSON schema and unit conversion;
`labelate.renderer` has no GUI dependency and supplies object drawing to both
the canvas and the public renderer. The canvas preview is scaled to at most
1024 × 1024 pixels; exports retain the full configured DPI and dimensions.

## License

This project is licensed under the GNU General Public License version 3 only
(`GPL-3.0-only`). See [LICENSE](LICENSE) for the full license text.
