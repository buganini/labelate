# Labelate

A label template editor built with **QPUIQ 1.8 + FontComboBox** and Pillow, supporting a
**PySide6 desktop app** and a **Pyodide browser build**. The desktop source imports
PySide6 directly; the static build changes that import to Pyodide. There is no
runtime backend selector. Browser Python runs in a worker without an app server.

**Open the app: [https://buganini.github.io/labelate/](https://buganini.github.io/labelate/)**

Use a current browser with WebAssembly JSPI support, such as Chrome or Edge.
The first visit downloads the pinned Pyodide runtime and Pillow from jsDelivr.
Images, fonts, templates, and rendering stay in the browser. Reloading the page
clears its virtual filesystem, so download your work before leaving.

## Editing labels

The **Label** tab contains the file toolbar, canvas, and properties. The canvas
has a black background outside the label. The right panel shows Label, Objects,
and Variables, in that order. The message bar stays below the tabs; printer controls appear alongside it only
in the PySide6 desktop app. The **Data** tab holds editable rows for batch printing.

- Width, height, unit, and rotation share one row; DPI and mode share the next.
  Units are mm, cm, and in; the default is **300 DPI**.
  Rotation selects 0, 90, 180, or 270 degrees. At 90/270 degrees the editor
  swaps the canvas width and height; objects stay upright with unchanged X/Y/W/H.
  Rotation is saved in `canvas.rotation` (default 0 for older templates).
  `render()`, PNG exports, and printing compose the oriented canvas first,
  then rotate the complete image by `-rotation` back to the physical label size.
- Add Text, Image, QR, Code128, or Rect. Select objects in the list or canvas and
  drag to position them. X/Y/W/H share one row. Delete selected appears
  only when an object is selected. Later objects render over earlier objects.
- Text content commits on blur. The desktop app offers a system font picker and font-file selection;
  the web app fixes the font to Noto Sans CJK TC. Point size, normal/italic style,
  normal/bold weight, and color in color mode are supported. Style and weight
  share a row. Italic uses a 12-degree slant; bold uses a proportional stroke.
  The color button opens a PUI prompt for a color name or hex value. Text clips
  to its box without automatic wrapping or shrinking.
- Image objects show a file picker and the original filename, not a Content editor.
  Images preserve aspect ratio and are embedded as raw bytes in the template.
  Format detection uses file contents; an image filename needs no extension.
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

- **Open .lbl** imports a MessagePack template, including its embedded images.
- **Save .lbl** saves the template and original image bytes in one binary file.
  Images do not depend on external paths and do not use Base64.
- Select **File** as the brand and **PNG** as the printer. The print button renders at the label's full dimensions/DPI and includes DPI
  metadata. The canvas preview is capped at 1024 × 1024 pixels.

In the browser, PUI presents a filename dialog, then a download notification. Click its Download
button to save the result to your device. Saving always creates a download; the
app cannot overwrite the file you originally selected. New/Open first ask about
unsaved changes. A browser navigation warning is requested while edits are pending;
its display is controlled by the browser. Text edits commit through PUI when the editor loses focus.

## Python rendering API

The renderer is also usable outside the browser and does not depend on a GUI:

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

Version 2 uses MessagePack with binary values and the `.lbl` extension. Old JSON
and ZIP templates are not supported. Geometry is stored in millimetres regardless
of `canvas.unit`; font size is in points. Object types are `text`, `image`, `qr`,
`code128`, and `rect`. Images store original bytes in `data`, without the original filename. Font paths remain in `font`. Text options are
`font_style` and `font_weight`; rectangle options are `stroke_mm` and `radius_mm`.
Use `labelate.model.loads(lbl_bytes)` and `dumps(template)` to decode and encode.
See [examples/product.lbl](examples/product.lbl) for a complete template.

## Desktop app

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python3 labelate
# Or: python -m labelate
```

The desktop app uses PUI's PySide6 backend. Text objects have a system FontComboBox, a font path field,
and a Choose font button. Font paths are saved relative to the selected `.lbl`
destination and resolved against that folder on opening. Images are embedded;
fonts remain external files. File dialogs save directly to disk.

## Data and desktop printing

In the Data tab, **Import XLSX/CSV** replaces the table after validation.
The first row contains column names, matched to template variables case-sensitively.
Missing columns or cells become empty strings; extra columns are ignored. CSV uses UTF-8, including BOM. XLSX uses the first worksheet
and cached formula values. Rows are retained even when values are missing or empty; failed imports preserve data.

The Data tab has one column per template variable. Add a row to copy the current
variable defaults, then click a cell to edit it. Each row represents one label.
Select a cell and use Remove selected row to delete that row. Data rows are saved in the same
`.lbl` file as `data_rows`; older version-2 templates without this field open with
an empty table. Variables added after a row was created use the current default
until that cell is edited. Columns removed from the template retain their stored
row values, so restoring a variable restores its data.

Python 3.11+ is required. Printer libraries are optional and pinned to Git commits:

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

Select Brother, Niim, or TSC to scan, then select a discovered device. Use the
printer dropdown's Scan for printers… item to rescan, or Printer settings… to
change settings. On first Print, choose the actual model and, for Brother, the
loaded stock. TSC settings include media type, gap/mark length, and serial baud
rate when applicable. Settings and device selection are kept for this app session;
they are not stored in the template.

In Label, **Copies** defaults to 1 and accepts positive integers; **Print Single
Label** prints the current template and variable values that many times. In Data,
**Print All** prints every row once, in order, without using Copies. Editing and
switching tabs remain available during printing; a job uses a snapshot taken when
Print is pressed. Closing the app waits for the active operation to finish.

All rows are preflighted before the first submission. Rendering uses the selected
printer's resolution, including TSC's actual 8 or 12 dots/mm. Brother stock must
match the label's physical dimensions; white edge margins are cropped to the
printable area. Marks in unprintable margins cause an error instead of scaling or
silently discarding content. The preview and PNG export retain the Label DPI.

Pillow images pass directly to each converter and jobs are sent from memory;
Labelate creates no temporary image or instruction files. CUPS can spool files
internally. Existing CUPS queues are preserved (`recreate_queue=False`). Failures
stop the batch, report completed submissions and uncertain current-label progress,
and never automatically resend. A queued/sent result does not claim physical
printing; only a printer-confirmed result is shown as printed.

File output is available on both backends and is selected by default. A single output
opens a Save File dialog. Multiple outputs open a folder picker and write
`label-0001.png`, `label-0002.png`, and so on, with confirmation before replacing
existing files. Copies applies in Label; Data exports one PNG per row.
All images are rendered before choosing a destination.

The GitHub Pages/Pyodide build offers only File / PNG; Brother, Niim, TSC and
hardware settings remain desktop-only. Browser folder export uses the File System
Access API and requires a supported browser such as Chrome or Edge. Native
USB/BLE/serial/CUPS dependencies are not bundled.

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
git -C .build/PUI checkout c4358175115bc2da8d1859e07ecb0e0e85ebc457
python scripts/build_pyodide.py
npm run build
python3 -m http.server 8868 --directory dist/pyodide
```

Open [http://localhost:8868](http://localhost:8868). Do not open `index.html` with
`file://`. Deploy `dist/pyodide/` to any HTTPS static host, including a URL subpath.

The Python builder pins the QPUIQ 1.8 + FontComboBox source commit and packages only shared/Pyodide
modules, Labelate, qrcode 8.2, python-barcode 0.16.1, and msgpack 1.1.2
(using its pure Python implementation in the browser). The JavaScript builder
adapts the pinned PUI cookbook bootstrap to start Labelate, loading Pyodide
314.0.7 and its Pillow package. Source changes are checked against the pinned
bootstrap, and worker/archive hashes reject mismatched cached assets. PySide6,
the Web server backend, and cookbook application code are not shipped.

## Reactive object model

The editor stores objects in a PUI State list, with a State dictionary per object.
Content, font, style, and weight controls use native State bindings. Numeric input
State converts the selected display unit to canonical millimetres and synchronizes
back after dragging or model edits. State change callbacks validate edits, restore
invalid values, reconcile variables, and refresh the preview. PUI owns the
in-progress text buffer and commits content on blur; input marks the document dirty.
Persistence, rendering, and printing receive ordinary dictionaries through a
snapshot; UI State and callbacks are never serialized into the `.lbl` file.

## Tests and GitHub Pages

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

Desktop font selection uses PUI FontComboBox. The selected system family is resolved
to a Pillow-readable font file; collection fonts also store a zero-based
`font_index`. Manual font-file selection remains available. The web version
continues to use bundled Noto Sans CJK TC. PUI is pinned to commit
`c4358175115bc2da8d1859e07ecb0e0e85ebc457` for FontComboBox support.

Selected objects have four corner resize handles and a rotation handle above the
top edge. Drag inside an object to move it, drag a corner to resize its box, or drag
the top handle to rotate clockwise about its center. The R field (degrees) also
accepts an exact angle. Text box resizing retains the font size; use Size to change
the text size. Object angles are stored as `rotation_deg` (default 0 for older
files) and apply to preview, PNG export, and printing. Label Rotation remains a
separate workspace setting. Content outside the label is clipped.
