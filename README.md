# Labelate

A label template editor and renderer.

- **Web app** — edit labels and export PNG, right in the browser.
- **Desktop app** — connect to Brother, Niim, or TSC label printers and print directly.

**Open the web app: [https://buganini.github.io/labelate/](https://buganini.github.io/labelate/)**

Use a current browser with WebAssembly JSPI support, such as Chrome or Edge.
Images, fonts, templates, and rendering stay in the browser. Reloading the page
clears its virtual filesystem, so download your work before leaving.

## Editing labels

The **Label** tab contains the file toolbar, canvas, and properties. The right
panel shows Label, Objects, and Variables. The **Data** tab holds editable rows
for batch printing.

- **Label properties**: width, height, unit (mm/cm/in), rotation (0/90/180/270),
  DPI (default 300), and color mode.
- **Objects**: add Text, Image, QR, Code128, or Rect. Select objects on the canvas
  and drag to position them. Later objects render over earlier objects.
  Selected objects have corner resize handles and a rotation handle above the top
  edge.
- **Text**: point size, normal/italic style, normal/bold weight, and color in
  color mode. Both apps bundle Noto Sans CJK TC (default) and Noto Sans Mono,
  listed first in the font picker; the desktop app adds installed fonts and
  font-file selection. Text clips to its box.
- **Image**: images preserve aspect ratio and are embedded in the template.
- **Rect**: line width and corner radius; black outline, transparent interior.
- **QR / Code128**: use whole-pixel modules and quiet zones. Increase size or DPI
  if a code does not fit. Code128 accepts non-empty ASCII.
- **Variables**: use `{name}` placeholders in text, QR, or Code128 content.
  Names follow `[A-Za-z_][A-Za-z0-9_]*`.
- Invalid objects appear as red boxes with details in the status line.

## Importing variables from a spreadsheet

Fill a label's `{variables}` from an XLSX or CSV file to print one label per row,
on both desktop and web.

1. Put `{name}` placeholders in text, QR, or Code128 content on the **Label** tab.
   Each variable becomes a column in the **Data** tab.
2. Prepare the spreadsheet: the first row holds column names matching the variable
   names exactly (case-sensitive, surrounding spaces ignored); each later row is
   one label. For example, a template using `{SN}` and `{customer}`:

   | SN | customer | notes |
   | --- | --- | --- |
   | A-001 | Ada | |
   | A-002 | Bob | |

3. On the **Data** tab, click **Import XLSX/CSV** and choose the file.

- Only the first worksheet of an XLSX is read; formulas use their last saved values.
  CSV files are read as UTF-8 (a BOM is fine).
- Columns without a matching variable (such as `notes`) are ignored; a variable
  without a column imports as empty text. Column names must be unique.
- Importing replaces the current rows. Edit cells by double-clicking, and use
  **Add row**, **Dedup**, or **Remove selected row** to adjust them.
- A table may hold up to 10,000 cells (rows × variables). Rows are saved in the
  `.lbl` file.
- **Print All** prints every row once; with **File / PNG** output it writes one
  PNG per row (`label-0001.png`, …).

## Opening and downloading files

- **Open .lbl** imports a MessagePack template, including embedded images.
- **Save .lbl** saves the template and images in one binary file.
- Select **File** as the brand and **PNG** as the printer to export images. The
  print button renders at the label's full dimensions/DPI.

In the browser, saving creates a download; the app cannot overwrite the original
file. New/Open first ask about unsaved changes.

## Desktop app

Python 3.11+ is required.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python3 labelate
```

The desktop app adds system font selection, direct file save, and hardware
printer support.

## Printing

Select Brother, Niim, or TSC as the printer brand to scan for devices. Use
**Printer settings** to configure model and media options.

- **Print Single Label** prints the current template (with **Copies** count).
- In the Data tab, **Print All** prints every row once (see
  [Importing variables from a spreadsheet](#importing-variables-from-a-spreadsheet)).

Install printer support:

```sh
python -m pip install -e '.[printers]'   # All three families
# Or: .[brother]  .[niim]  .[tsc]
```

USB requires system libusb; BLE requires Bluetooth permissions. File/PNG output
is available on both desktop and web.

## License

MIT; see [LICENSE](LICENSE).

## Development

See [docs/development.md](docs/development.md) for the Python rendering API,
template format, local browser build, tests, CI, and printer adapter details.
