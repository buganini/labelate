"""Optional native printer adapters. No GUI imports, files, or automatic retries."""
from dataclasses import dataclass
import importlib
import math

from .model import loads, dumps
from .renderer import render

PACKAGES = {'Brother': 'brother_ql', 'Niim': 'pyniim', 'TSC': 'pytsc'}


def module(brand, suffix):
    try:
        return importlib.import_module(PACKAGES[brand] + '.' + suffix)
    except ImportError as exc:
        raise RuntimeError(f"Install from the Labelate checkout: python -m pip install -e '.[{brand.lower()}]' ({exc})") from exc


@dataclass(frozen=True)
class Printer:
    brand: str
    identifier: str
    backend: str
    name: str

    @property
    def display(self):
        return f'{self.name} · {self.identifier} [{self.backend}]'


def discover(brand):
    helpers = module(brand, 'backends.helpers')
    records = helpers.discover('pyusb') if brand == 'Brother' else helpers.discover()
    devices, warnings, seen = [], [], set()
    for record in records:
        if record.get('kind') == 'warning':
            warnings.append(record['message'])
            continue
        identifier = record['identifier']
        backend = record.get('backend', 'pyusb' if brand == 'Brother' else 'bleak')
        if (backend, identifier) in seen:
            continue
        seen.add((backend, identifier))
        name = record.get('name') or record.get('description') or record.get('model') or brand
        devices.append(Printer(brand, identifier, backend, str(name)))
    return devices, warnings


def models(brand):
    manager = module(brand, 'models').ModelsManager()
    if brand == 'Brother':
        return list(manager.iter_identifiers())
    if brand == 'Niim':
        return [name for name in manager.iter_identifiers()
                if manager.get_model_by_identifier(name).support != 'catalog-only']
    return [model.identifier for model in manager.get_models()]


def stocks():
    return list(module('Brother', 'labels').LabelsManager().iter_identifiers())


def settings(brand):
    return {'model': '', 'stock': '62', 'media': 'gap', 'gap': '2', 'baudrate': '9600'}


def positive_integer(value, name='Copies'):
    text = str(value)
    if not text.isascii() or not text.isdigit() or int(text) < 1:
        raise ValueError(f'{name} must be a positive integer')
    return int(text)


def prepare(printer, config, template_bytes, values):
    """Render at device resolution, then build one label job without device I/O."""
    brand = printer.brand
    template = loads(template_bytes)
    canvas = template['canvas']
    model = module(brand, 'models').ModelsManager().get_model_by_identifier(config['model'])
    canvas['dpi'] = 300 if brand == 'Brother' else model.dpi if brand == 'Niim' else model.dots_per_mm * 25.4
    image = render(dumps(template), values)
    label = f"{canvas['width_mm']:g}x{canvas['height_mm']:g}"
    conversion = module(brand, 'conversion').convert
    raster_module = module(brand, 'raster')
    if brand == 'Brother':
        label = config['stock']
        spec = module(brand, 'labels').LabelsManager().get_label_by_identifier(label)
        # Render the physical label at 300 DPI; crop only white unprintable margins.
        # Never scale barcodes or silently discard marks outside the printable area.
        nominal = spec.tape_size
        if not math.isclose(canvas['width_mm'], nominal[0], abs_tol=.1):
            raise ValueError(f'Brother stock {label} requires label width {nominal[0]} mm')
        if nominal[1] and not math.isclose(canvas['height_mm'], nominal[1], abs_tol=.1):
            raise ValueError(f'Brother stock {label} requires label height {nominal[1]} mm')
        target = (spec.dots_printable[0], spec.dots_printable[1] or image.height)
        if image.width < target[0] or image.height < target[1]:
            raise ValueError('Label is smaller than the Brother printable area')
        x, y = (image.width-target[0])//2, (image.height-target[1])//2
        box = (x, y, x+target[0], y+target[1])
        mask = image.convert('L').point(lambda p: 255-p)
        mask.paste(0, box)
        if mask.getbbox():
            raise ValueError('Objects extend into Brother unprintable margins; move them inward')
        image = image.crop(box)
        return conversion(raster_module.BrotherQLRaster(config['model']), [image], label, rotate=0, red=bool(spec.color))
    if brand == 'Niim':
        return conversion(raster_module.NiimbotRaster(config['model']), [image], label, rotate=0)
    gap = float(config['gap'])
    if not math.isfinite(gap) or gap < 0:
        raise ValueError('Gap must be a non-negative number in mm')
    return conversion(raster_module.TSPLRaster(config['model']), [image], label,
                      rotate=0, gap=gap, media=config['media'])


def send(printer, config, job):
    options = {}
    if printer.brand == 'TSC':
        if printer.backend == 'cups':
            options['recreate_queue'] = False
        elif printer.backend == 'serial':
            options['baudrate'] = positive_integer(config['baudrate'], 'Baud rate')
    return module(printer.brand, 'backends.helpers').send(
        job, printer_identifier=printer.identifier, backend_identifier=printer.backend,
        blocking=True, **options)


def print_labels(printer, config, template_bytes, rows, copies, progress=lambda message: None):
    copies = positive_integer(copies)
    if not rows:
        raise ValueError('No data rows to print')
    # Preflight every row before sending the first label; retain only one raster at a time.
    for index, row in enumerate(rows):
        progress(f'Checking label {index+1}/{len(rows)}…')
        prepare(printer, config, template_bytes, row)
    completed, outcomes = 0, set()
    total = len(rows) * copies
    for row in rows:
        job = prepare(printer, config, template_bytes, row)
        for _ in range(copies):
            progress(f'Printing {completed+1}/{total}…')
            try:
                result = send(printer, config, job)
                outcome = result.get('outcome', 'unknown')
                if outcome not in ('printed', 'queued', 'sent'):
                    raise RuntimeError(f'Printer outcome: {outcome}')
            except Exception as exc:
                raise RuntimeError(f'Stopped after {completed}/{total} submissions; current label may have printed. {exc}') from exc
            completed += 1
            outcomes.add(outcome)
    if outcomes == {'printed'}:
        return f'Printed {completed} label(s).'
    return f'Submitted {completed} label(s) ({", ".join(sorted(outcomes))}); physical printing not confirmed.'
