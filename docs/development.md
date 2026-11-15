# Development

Technical details for contributors and developers working on Labelate.

## Python rendering API

The renderer is usable outside the browser and does not depend on a GUI:

```python
from pathlib import Path
from labelate import render

lbl_bytes = Path('examples/product.lbl').read_bytes()
image = render(lbl_bytes, {'name': 'Coffee', 'sku': 'ABC123'})
image.save('label.png', dpi=image.info['dpi'])
```

`render(lbl_bytes, variables)` returns `PIL.Image.Image`: mode `L` (8-bit greyscale)
or `RGB` for color. Greyscale preserves intermediate tones without thresholding.
Older templates using `mono` are loaded as `greyscale`. Values override
saved defaults and are converted to strings. Missing variables, invalid assets,
and unrenderable codes raise `ValueError`. Image bytes are decoded directly.
Relative font paths in this API resolve against the working directory; the editor
resolves them against the template directory. The browser always uses Noto Sans
CJK TC. The standalone renderer accepts explicit font paths.

## Template format

Version 2 uses MessagePack with binary values and the `.lbl` extension. Old JSON
and ZIP templates are not supported. Geometry is stored in millimetres regardless
of `canvas.unit`; font size is in points. Object types are `text`, `image`, `qr`,
`code128`, and `rect`. Images store original bytes in `data` and the filename basename in `image_name`. Font paths remain in `font`. Text options are
`font_style` and `font_weight`; rectangle options are `stroke_mm` and `radius_mm`.
Use `labelate.model.loads(lbl_bytes)` and `dumps(template)` to decode and encode.
See [examples/product.lbl](../examples/product.lbl) for a complete template.

## Reactive object model

The editor stores objects in a PUI State list, with a State dictionary per object.
Content, font, style, and weight controls use native State bindings. Numeric input
State converts the selected display unit to canonical millimetres and synchronizes
back after dragging or model edits. State change callbacks validate edits, restore
invalid values, reconcile variables, and refresh the preview. PUI owns the
in-progress text buffer and commits content on blur; input marks the document dirty.
Persistence, rendering, and printing receive ordinary dictionaries through a
snapshot; UI State and callbacks are never serialized into the `.lbl` file.

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
git -C .build/PUI checkout e7c1886ddbfecd37b7af32bcb8e057e4f64d5303
python scripts/build_pyodide.py
npm run build
python3 -m http.server 8868 --directory dist/pyodide
```

Open [http://localhost:8868](http://localhost:8868). Do not open `index.html` with
`file://`. Deploy `dist/pyodide/` to any HTTPS static host, including a URL subpath.

The Python builder pins the QPUIQ 1.10 source commit and packages only shared/Pyodide
modules, Labelate, qrcode 8.2, python-barcode 0.16.1, and msgpack 1.1.2
(using its pure Python implementation in the browser). The JavaScript builder
adapts the pinned PUI cookbook bootstrap to start Labelate, loading Pyodide
314.0.7 and its Pillow package. Source changes are checked against the pinned
bootstrap, and worker/archive hashes reject mismatched cached assets. PySide6,
the Web server backend, and cookbook application code are not shipped.

## Tests

```sh
python -m pytest -q
npx playwright install chromium
npm run test:browser
```

To use an existing Chrome installation locally, set `CHROME_PATH` to its executable.
Python tests cover rendering, model validation, desktop font selection/saving,
printer adapters, batch preflight/failure behavior, and background UI dispatch,
browser-backend bindings/lifecycle,
relative font paths and binary image round trips. Playwright exercises the actual Pyodide app,
tabs, data-cell commits, content edits, extensionless image imports, .lbl round
trips, and PNG downloads. Install `.[dev,printers]` to run all offline printer
conversion tests; without printer extras those tests are skipped. Automated tests
never send real print jobs; physical output still requires hardware verification.

## CI and GitHub Pages

[Build and deploy Labelate](../.github/workflows/pages.yml) runs tests and builds on
pull requests, pushes to main, and manual dispatch. Each successful build uploads
a `labelate-pyodide` artifact. Main and manual runs also deploy to GitHub Pages;
pull requests never deploy. Repository Settings → Pages → Source must be
**GitHub Actions**. Deployment uses the `github-pages` environment and minimal
`pages: write` / `id-token: write` permissions in the deploy job only.

## Printer adapters

Printer libraries are optional and pinned to Git commits:

```sh
python -m pip install -e '.[printers]'   # All three families
# Or select one:
python -m pip install -e '.[brother]'
python -m pip install -e '.[niim]'
python -m pip install -e '.[tsc]'
```

- [brother_ql](https://github.com/pklaus/brother_ql): Brother QL USB discovery and
  printing. Network discovery is not implemented upstream and is not offered here.
- [pyniim](https://github.com/buganini/pyniim): BLE discovery; the supported model
  is currently M2_H. Discovery may include unrelated BLE advertisements; the library
  verifies the service and model on connection.
- [pytsc](https://github.com/buganini/pytsc): serial, CUPS, and optional direct USB
  discovery. Direct USB currently targets the PL2305 adapter, not arbitrary USB
  printers. Adapter discovery does not identify the attached printer model.

USB requires system libusb (for example, `brew install libusb` on macOS), and BLE
requires Bluetooth permissions. Missing libraries or device access errors appear
in the message bar without preventing editing.

Pillow images pass directly to each converter and jobs are sent from memory;
Labelate creates no temporary image or instruction files. CUPS can spool files
internally. Existing CUPS queues are preserved (`recreate_queue=False`). Failures
stop the batch, report completed submissions and uncertain current-label progress,
and never automatically resend. A queued/sent result does not claim physical
printing; only a printer-confirmed result is shown as printed.

## Desktop font handling

Desktop font selection uses PUI FontComboBox. The selected system family is resolved
to a Pillow-readable font file; collection fonts also store a zero-based
`font_index`. Manual font-file selection remains available. The web version
continues to use bundled Noto Sans CJK TC. PUI is pinned to commit
`e7c1886ddbfecd37b7af32bcb8e057e4f64d5303` for the QPUIQ 1.10 release.

## Default font details

The web editor fixes text rendering to **Noto Sans CJK TC Regular 2.004**.

- [Noto CJK project](https://github.com/notofonts/noto-cjk)
- [Pinned font download](https://raw.githubusercontent.com/notofonts/noto-cjk/Sans2.004/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf)
- [SIL Open Font License](https://github.com/notofonts/noto-cjk/blob/Sans2.004/LICENSE)

Font binaries are **not checked into this repository**. The build downloads the
font and license into ignored `.build/fonts/`, verifies their SHA-256 hashes,
and includes them in the browser archive. This adds about 16 MB before ZIP
compression. Source-only Python usage can pass a font path explicitly; without
the built font, the renderer retains its platform/Pillow fallback.
