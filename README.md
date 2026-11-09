# Labelate

A label template editor built with **QPUIQ 1.8** and Pillow, supporting a
**PySide6 desktop app** and a **Pyodide browser build**. The desktop source imports
PySide6 directly; the static build changes that import to Pyodide. There is no
runtime backend selector. Browser Python runs in a worker without an app server.

**Open the app: [https://buganini.github.io/labelate/](https://buganini.github.io/labelate/)**

Use a current browser with WebAssembly JSPI support, such as Chrome or Edge.
The first visit downloads the pinned Pyodide runtime and Pillow from jsDelivr.
Images, fonts, templates, and rendering stay in the browser. Reloading the page
clears its virtual filesystem, so download your work before leaving.

## Editing labels

The left canvas has a black background outside the label. The right panel shows
Label, Objects, and Variables, in that order.

- Select one of 25 label presets or set a custom size. Unit, width, height, and
  Rotate share one row; DPI and mode share the next. Units are mm, cm, and in.
  The default is **300 DPI**. Rotate swaps label width and height.
- Add Text, Image, QR, Code128, or Rect. Select objects in the list or canvas and
  drag to position them. X/Y and W/H each share a row. Delete selected appears
  only when an object is selected. Later objects render over earlier objects.
- Text content commits on blur. The desktop app allows choosing a font file;
  the web app fixes the font to Noto Sans CJK TC. Point size, normal/italic style,
  normal/bold weight, and color in color mode are supported. Style and weight
  share a row. Italic uses a 12-degree slant; bold uses a proportional stroke.
  The color button opens a PUI prompt for a color name or hex value. Text clips
  to its box without automatic wrapping or shrinking.
- Image objects show a file picker and a read-only path, not a Content editor.
  Images preserve aspect ratio. JSON references files; Base64 is not supported.
- Rect supports width, height, line width, and corner R in the selected unit.
  It has a black outline and transparent interior; R = 0 gives square corners.
- Use `{name}` placeholders in text, QR, or Code128 content. Variables are derived
  from content and unused names are removed. Names follow
  `[A-Za-z_][A-Za-z0-9_]*`. Variable values commit on Enter or blur.
- Codes use whole-pixel modules and quiet zones. Increase size or DPI if a code
  does not fit. Code128 accepts non-empty ASCII without a printed caption.
- Invalid objects appear as red boxes with details in the status line. Export
  fails rather than silently omitting invalid objects.

## Opening and downloading files

- **Open JSON / ZIP** imports a JSON template or a portable template ZIP.
- **Open folder** imports a folder containing exactly one JSON template and its
  images, preserving relative paths. A JSON file alone cannot grant the
  browser access to neighboring files: import the folder/ZIP or reselect assets.
- **Save JSON** downloads JSON with relative file paths. It does not download
  assets; use Save ZIP to obtain a complete portable template.
- **Save ZIP** downloads `label.json` plus referenced image files.
  This preserves relative references without embedding image bytes in JSON.
- **Export PNG** renders at the label's full dimensions/DPI and includes DPI
  metadata. The canvas preview is capped at 1024 × 1024 pixels.

In the browser, PUI presents a filename dialog, then a download notification. Click its Download
button to save the result to your device. Saving always creates a download; the
app cannot overwrite the file you originally selected. New/Open first ask about
unsaved changes. A browser navigation warning is requested while edits are pending;
its display is controlled by the browser. Save/export commit pending text drafts.

## Python rendering API

The renderer is also usable outside the browser and does not depend on a GUI:

```python
from pathlib import Path
from labelate import render

json_string = Path('examples/product.json').read_text(encoding='utf-8')
image = render(json_string, {'name': 'Coffee', 'sku': 'ABC123'})
image.save('label.png', dpi=image.info['dpi'])
```

`render(json_string, variables)` returns `PIL.Image.Image`: mode `1` for monochrome
or `RGB` for color. Monochrome uses threshold 128 without dithering. Values override
saved defaults and are converted to strings. Missing variables, invalid assets,
and unrenderable codes raise `ValueError`. Relative paths in this string-only API
resolve against the working directory; the editor resolves imported templates
against their JSON directory. The browser always uses Noto Sans CJK TC, including when importing JSON with a
custom font path. The standalone renderer still accepts explicit font paths.

Version 1 JSON stores geometry in millimetres regardless of `canvas.unit`.
Font size is in points. Object types are `text`, `image`, `qr`, `code128`, `rect`.
Image paths are stored in `content`, font paths in `font`. Text options are
`font_style` and `font_weight`; rectangle options are `stroke_mm` and `radius_mm`.
See [examples/product.json](examples/product.json) for a complete template.

## Desktop app

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python3 labelate
# Or: python -m labelate
```

The desktop app uses PUI's PySide6 backend. Text objects have a font path field
and a Choose font button. JSON saves reference images and fonts relative to the
selected JSON destination; opening a template resolves those paths against its
folder. File dialogs save directly to disk. ZIP exports bundle selected assets.

## Local browser build

Python 3.12 and Node.js 22 are recommended. The builder converts the single
`import PUI.PySide6 as UI` in `labelate.app` to `import PUI.pyodide as UI` inside
the generated archive and replaces `labelate.platform` with `web/platform.py`.
The checked-in desktop source is never changed by the build.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
npm ci
mkdir -p .build
git clone https://github.com/buganini/PUI.git .build/PUI
git -C .build/PUI checkout 091c24f44916c5bf5796f0bb922380d3cddba1e4
python scripts/build_pyodide.py
npm run build
python3 -m http.server 8868 --directory dist/pyodide
```

Open [http://localhost:8868](http://localhost:8868). Do not open `index.html` with
`file://`. Deploy `dist/pyodide/` to any HTTPS static host, including a URL subpath.

The Python builder pins the QPUIQ 1.8 source commit and packages only shared/Pyodide
modules, Labelate, qrcode 8.2, and python-barcode 0.16.1. The JavaScript builder
adapts the pinned PUI cookbook bootstrap to start Labelate, loading Pyodide
314.0.7 and its Pillow package. Source changes are checked against the pinned
bootstrap, and worker/archive hashes reject mismatched cached assets. PySide6,
the Web server backend, and cookbook application code are not shipped.

## Tests and GitHub Pages

```sh
python -m pytest -q
npx playwright install chromium
npm run test:browser
```

To use an existing Chrome installation locally, set `CHROME_PATH` to its executable.
Python tests cover rendering, model validation, desktop font selection/saving,
browser-backend bindings/lifecycle,
relative paths and safe ZIP imports. Playwright exercises the actual Pyodide app,
content edits, image imports, and JSON/PNG/ZIP downloads.

[Build and deploy Labelate](.github/workflows/pages.yml) runs tests and builds on
pull requests, pushes to main, and manual dispatch. Each successful build uploads
a `labelate-pyodide` artifact. Main and manual runs also deploy to GitHub Pages;
pull requests never deploy. Repository Settings → Pages → Source must be
**GitHub Actions**. Deployment uses the `github-pages` environment and minimal
`pages: write` / `id-token: write` permissions in the deploy job only.

## License

GNU General Public License version 3 only (`GPL-3.0-only`); see [LICENSE](LICENSE).
The static site includes PUI's MIT license, and the Python archive retains the
licenses and metadata from bundled dependencies.

## Default font

The web editor fixes text rendering to **Noto Sans CJK TC Regular 2.004**, with
no font selector. It covers common Traditional/Simplified Chinese, Japanese,
Korean, and Latin characters, but not every Unicode code point or emoji.

- [Noto CJK project](https://github.com/notofonts/noto-cjk)
- [Pinned font download](https://raw.githubusercontent.com/notofonts/noto-cjk/Sans2.004/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf)
- [SIL Open Font License](https://github.com/notofonts/noto-cjk/blob/Sans2.004/LICENSE)

Font binaries are **not checked into this repository**. The build downloads the
font and license into ignored `.build/fonts/`, verifies their SHA-256 hashes,
and includes them in the browser archive. This adds about 16 MB before ZIP
compression. Source-only Python usage can pass a font path explicitly; without
the built font, the renderer retains its platform/Pillow fallback.
