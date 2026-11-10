"""Declarative QPUIQ editor, including its canvas and input controls."""
import math
import copy
from pathlib import Path

import PUI.PySide6 as UI
from PIL import Image, ImageDraw, ImageColor

from .model import (new_template, new_object, variable_names, reconcile_variables,
                    dumps, display_length, millimetres, LABEL_PRESETS, UNIT_MM)
from .renderer import render, object_image, pixels
from .template_io import open_document
from .geometry import view_size, view_box, from_view
from . import platform


class Binding:
    """PUI's value binding protocol backed by validated model operations."""
    def __init__(self, get, set):
        self.get, self.set = get, set

    @property
    def value(self):
        return self.get()

    @value.setter
    def value(self, value):
        self.set(value)


class Labelate(UI.Application):
    def __init__(self):
        super().__init__()
        self.template, self.path = new_template(), None
        self.selected, self.modified = None, False
        self.state = UI.State()
        self.state.revision = 0
        self.active_tab = 'Label'
        self.brand = ''
        self.printers = []
        self.printer_choice = 'Scan for printers…'
        self.copies = '1'
        self.busy = False
        self.print_message = ''
        self.printer_configs = {}
        self.settings_open = False
        self.settings_draft = {}
        self.model_choices = []
        self.stock_choices = []
        self.pending_print = False
        self.drafts = {}
        self.drag = None
        self.viewport = (0, 0, 1)
        self.preview = None
        self.status = ''
        self.project_dir = None
        self.bindings = {}
        self.binding_scope = "label"
        self.refresh_preview()

    def update(self, prev=None):
        super().update(prev)
        platform.attach(self)

    def binding(self, key, get, set):
        binding = self.bindings.get(key)
        if binding is None:
            binding = self.bindings[key] = Binding(get, set)
        else:
            binding.get, binding.set = get, set
        return binding

    def notify(self):
        self.state.revision += 1
        platform.modified(self.modified or any(self.object_by_id(k) and self.object_by_id(k)['content'] != v
                                      for k, v in self.drafts.items()))

    def current(self):
        return self.object_by_id(self.selected)

    def object_by_id(self, key):
        return next((obj for obj in self.template['objects'] if obj['id'] == key), None)

    def button(self, text, action, key=None, disabled=False):
        return UI.Button(text, disabled=disabled).id(key or text).click(lambda event: action())

    def select(self, label, choices, value, setter, key):
        UI.Label(label)
        with UI.ComboBox(text_model=self.binding(self.binding_scope + ':' + key, lambda: value, setter)).id(key):
            for choice in choices:
                UI.ComboBoxItem(choice)

    def number(self, label, value, setter, key, minimum=0, maximum=10000):
        UI.Label(label)
        def commit(text):
            try:
                number = float(text)
                if not math.isfinite(number) or not minimum <= number <= maximum:
                    raise ValueError(f'{label} must be between {minimum} and {maximum}')
                setter(number)
            except ValueError as exc:
                self.status = str(exc)
                self.notify()
        return UI.TextField(self.binding(self.binding_scope + ':' + key, lambda: f'{value:.3f}'.rstrip('0').rstrip('.'), commit)).id(key).layout(minWidth=48)

    def content(self):
        _ = self.state.revision
        with UI.Window(title='Labelate — Label Template Editor', size=(1280, 800)).id('window'):
            with UI.VBox().layout(padding=10):
                with UI.Tabs(model=self.binding('active-tab', lambda: self.active_tab, self.set_tab)).id('tabs').layout(weight=1):
                    with UI.Tab('Label').id('Label'):
                        with UI.HBox().id('toolbar'):
                            for title, action in [('New', self.new), ('Open .lbl', self.open), ('Save .lbl', self.save), ('Export PNG', self.export)]:
                                self.button(title, action)
                            UI.Spacer()
                        with UI.Splitter().id('workspace'):
                            UI.Canvas(self.paint).id('canvas').layout(width=720, minWidth=240, minHeight=300).mousedown(self.pointer_down).mousemove(self.pointer_move).mouseup(self.pointer_up)
                            with UI.Scroll().id('sidebar').layout(width=520, minWidth=460):
                                with UI.VBox().layout(padding=10):
                                    self.label_panel()
                                    UI.Divider()
                                    self.objects_panel()
                                    UI.Divider()
                                    self.variables_panel()
                                    UI.Spacer()
                    with UI.Tab('Data').id('Data'):
                        self.data_panel()
                self.print_panel()
                if platform.PRINTING:
                    self.print_settings_panel()

    def set_tab(self, value):
        self.commit_content()
        self.active_tab = value
        self.notify()

    def data_panel(self):
        names = variable_names(self.template)
        rows = self.template.get('data_rows', [])
        with UI.HBox():
            self.button('Add row', self.add_data_row)
            self.button('Remove last row', self.remove_data_row, disabled=not rows)
            UI.Label(f'{len(rows)} row(s) · one label per row')
            UI.Spacer()
        if not names:
            UI.Label('Add {variables} in the Label tab to create data columns.')
        with UI.Table(columnHeader=['#', *names]).id('data-table').layout(weight=1):
            for i, row in enumerate(rows):
                with UI.TableNode().id(f'data-row-{i}'):
                    UI.TableNode(str(i+1))
                    for name in names:
                        UI.TableNode(row.get(name, str(self.template['variables'].get(name, '')))).id(name).set(self.set_data_cell, i, name)

    def add_data_row(self):
        if (len(self.template.get('data_rows', [])) + 1) * (len(variable_names(self.template)) + 1) > 10000:
            self.print_message = 'Data table exceeds 10,000 cells'
            self.notify()
            return
        self.template.setdefault('data_rows', []).append(dict(self.template['variables']))
        self.modified = True
        self.notify()

    def remove_data_row(self):
        if self.template.get('data_rows'):
            self.template['data_rows'].pop()
            self.modified = True
            self.notify()

    def set_data_cell(self, value, index, name):
        self.template['data_rows'][index][name] = str(value)
        self.modified = True
        self.notify()

    def print_panel(self):
        with UI.HBox().id('message-bar'):
            UI.Label(self.print_message or self.status).id('status').layout(weight=1)
            if not platform.PRINTING:
                return
            UI.Spacer()
            with UI.ComboBox(text_model=self.binding('brand', lambda: self.brand or 'Select brand…', self.set_brand),
                             disabled=self.busy or not platform.PRINTING).id('printer-brand'):
                UI.ComboBoxItem('Select brand…')
                for brand in ('Brother', 'Niim', 'TSC'):
                    UI.ComboBoxItem(brand)
            with UI.ComboBox(text_model=self.binding('printer', lambda: self.printer_choice, self.set_printer),
                             disabled=self.busy or not platform.PRINTING or not self.brand).id('printer-device'):
                UI.ComboBoxItem('Scan for printers…')
                for printer in self.printers:
                    UI.ComboBoxItem(printer.display)
                if self.selected_printer():
                    UI.ComboBoxItem('Printer settings…')
            disabled = self.busy or not platform.PRINTING or not self.selected_printer()
            if self.active_tab == 'Label':
                UI.Label('Copies')
                binding = self.binding('copies', lambda: self.copies, self.set_copies)
                UI.TextField(binding, edit_model=binding).id('copies').layout(width=60)
                self.button('Print Single Label', self.request_print, disabled=disabled)
            else:
                self.button('Print All', self.request_print, disabled=disabled or not self.template.get('data_rows'))

    def set_copies(self, value):
        self.copies = str(value)

    def selected_printer(self):
        return next((p for p in self.printers if p.display == self.printer_choice), None)

    def set_brand(self, value):
        if self.busy or not platform.PRINTING or value not in ('Brother', 'Niim', 'TSC'):
            return
        self.brand = value
        self.printers = []
        self.printer_choice = 'Scan for printers…'
        self.scan_printers()

    def set_printer(self, value):
        if self.busy:
            return
        if value == 'Scan for printers…':
            self.scan_printers()
        elif value == 'Printer settings…':
            self.configure_printer(False)
        else:
            self.printer_choice = value
            self.notify()

    def run_task(self, message, work, complete):
        self.busy = True
        self.print_message = message
        self.notify()
        def done(result, error):
            self.busy = False
            if error:
                self.print_message = str(error)
            else:
                complete(result)
            self.notify()
        platform.run_background(self, work, done)

    def scan_printers(self):
        if self.busy or not self.brand or not platform.PRINTING:
            return
        from . import printing
        brand = self.brand
        def complete(result):
            self.printers, warnings = result
            self.printer_choice = self.printers[0].display if self.printers else 'Scan for printers…'
            self.print_message = f'Found {len(self.printers)} {brand} device(s).'
            if warnings:
                self.print_message += ' ' + ' | '.join(warnings)
        self.run_task('Scanning printers…', lambda progress: printing.discover(brand), complete)

    def config_key(self):
        printer = self.selected_printer()
        return (printer.brand, printer.backend, printer.identifier)

    def configure_printer(self, pending):
        from . import printing
        if not self.selected_printer():
            return
        try:
            self.model_choices = printing.models(self.brand)
            self.stock_choices = printing.stocks() if self.brand == 'Brother' else []
            self.settings_draft = dict(self.printer_configs.get(self.config_key(), printing.settings(self.brand)))
            self.pending_print = pending
            self.settings_open = True
        except Exception as exc:
            self.print_message = str(exc)
        self.notify()

    def print_settings_panel(self):
        with UI.Modal(self.binding('print-settings', lambda: self.settings_open, self.close_settings),
                      offValue=False, title='Printer settings', size=(520, 340)).id('print-settings'):
            with UI.VBox().layout(padding=12):
                self.binding_scope = 'printer-settings'
                with UI.HBox():
                    self.select('Model', ['', *self.model_choices], self.settings_draft.get('model', ''),
                                lambda value: self.set_print_setting('model', value), 'printer-model')
                if self.brand == 'Brother':
                    with UI.HBox():
                        self.select('Stock', self.stock_choices, self.settings_draft.get('stock', '62'),
                                    lambda value: self.set_print_setting('stock', value), 'printer-stock')
                    UI.Label('Label dimensions must match stock. Keep objects inside printable margins.')
                if self.brand == 'TSC':
                    with UI.HBox():
                        self.select('Media', ['gap', 'continuous', 'black-mark'], self.settings_draft.get('media', 'gap'),
                                    lambda value: self.set_print_setting('media', value), 'printer-media')
                    with UI.HBox():
                        UI.Label('Gap / mark (mm)')
                        UI.TextField(self.binding('printer-gap', lambda: self.settings_draft.get('gap', '2'),
                                                  lambda value: self.set_print_setting('gap', value)))
                    if self.selected_printer() and self.selected_printer().backend == 'serial':
                        with UI.HBox():
                            UI.Label('Baud rate')
                            UI.TextField(self.binding('printer-baud', lambda: self.settings_draft.get('baudrate', '9600'),
                                                      lambda value: self.set_print_setting('baudrate', value)))
                UI.Spacer()
                with UI.HBox():
                    self.button('Cancel', lambda: self.close_settings(False), key='cancel-printer-settings')
                    self.button('Save and Print' if self.pending_print else 'Apply', self.apply_print_settings,
                                key='apply-printer-settings', disabled=not self.settings_draft.get('model'))

    def set_print_setting(self, key, value):
        self.settings_draft[key] = value
        self.notify()

    def close_settings(self, value):
        self.settings_open = bool(value)
        if not value:
            self.pending_print = False
        self.notify()

    def apply_print_settings(self):
        self.printer_configs[self.config_key()] = dict(self.settings_draft)
        pending = self.pending_print
        self.close_settings(False)
        if pending:
            self.request_print()

    def request_print(self):
        if self.busy or not platform.PRINTING or not self.selected_printer():
            return
        from . import printing
        self.commit_content()
        try:
            copies = printing.positive_integer(self.copies) if self.active_tab == 'Label' else 1
            rows = copy.deepcopy(self.template.get('data_rows', [])) if self.active_tab == 'Data' else [{}]
            if not rows:
                raise ValueError('No data rows to print')
            config = self.printer_configs.get(self.config_key())
            if not config:
                self.configure_printer(True)
                return
            template_bytes = dumps(self.template)
            printer = self.selected_printer()
            config = dict(config)
        except ValueError as exc:
            self.print_message = str(exc)
            self.notify()
            return
        def complete(result):
            self.print_message = result
        self.run_task('Preparing print…',
                      lambda progress: printing.print_labels(printer, config, template_bytes, rows, copies, progress),
                      complete)

    def label_panel(self):
        self.binding_scope = 'label'
        canvas = self.template['canvas']
        unit = canvas['unit']
        UI.Label('Label').style(fontWeight=700)
        preset = next((name for name, size in LABEL_PRESETS.items()
                       if size == (canvas['width_mm'], canvas['height_mm'])), 'Custom')
        with UI.HBox().id('preset-row'):
            self.select('Label preset', ['Custom', *LABEL_PRESETS], preset, self.preset, 'preset')
        with UI.HBox().id('dimensions-row'):
            self.select('Unit', list(UNIT_MM), unit, self.set_unit, 'unit')
            for key, label in [('width_mm', 'Width'), ('height_mm', 'Height')]:
                self.number(label, display_length(canvas[key], unit),
                            lambda v, k=key: self.set_canvas(k, millimetres(v, unit)), key, .001)
            self.select('Rotation', ['0', '90', '180', '270'], str(canvas.get('rotation', 0)),
                        self.set_rotation, 'rotation')
        with UI.HBox().id('output-row'):
            self.number('DPI', canvas['dpi'], lambda v: self.set_canvas('dpi', round(v)), 'dpi', 36, 2400)
            self.select('Mode', ['mono', 'color'], canvas['mode'], lambda v: self.set_canvas('mode', v), 'mode')

    def objects_panel(self):
        UI.Label('Objects').style(fontWeight=700)
        with UI.HBox().id('object-toolbar'):
            for label, kind in [('Text', 'text'), ('Image', 'image'), ('QR', 'qr'), ('Code128', 'code128'), ('Rect', 'rect')]:
                self.button(label, lambda k=kind: self.add(k))
            UI.Spacer()
            if self.current():
                self.button('Delete selected', self.delete)
        with UI.Scroll().id('object-list').layout(height=125):
            with UI.VBox():
                for obj in self.template['objects']:
                    prefix = '● ' if obj['id'] == self.selected else ''
                    self.button(f"{prefix}{obj['type']} · {(obj.get('image_name', '') if obj['type'] == 'image' else obj['content'])[:32]}",
                                lambda key=obj['id']: self.select_object(key), obj['id'])
                UI.Spacer()
        obj = self.current()
        if obj:
            with UI.VBox().id('properties-' + obj['id']):
                self.object_properties(obj)

    def object_properties(self, obj):
        unit, oid = self.template['canvas']['unit'], obj['id']
        self.binding_scope = oid
        def change(key, value):
            self.set_object(key, value, oid)
        with UI.HBox():
            self.number(f'X ({unit})', display_length(obj['x_mm'], unit),
                        lambda v: change('x_mm', millimetres(v, unit)), 'x_mm')
            self.number(f'Y ({unit})', display_length(obj['y_mm'], unit),
                        lambda v: change('y_mm', millimetres(v, unit)), 'y_mm')
        with UI.HBox():
            self.number(f'W ({unit})', display_length(obj['width_mm'], unit),
                        lambda v: change('width_mm', millimetres(v, unit)), 'width_mm', .001)
            self.number(f'H ({unit})', display_length(obj['height_mm'], unit),
                        lambda v: change('height_mm', millimetres(v, unit)), 'height_mm', .001)
        if obj['type'] == 'image':
            UI.Label('Image file')
            UI.Label(obj.get('image_name') or 'No image selected').id('image-name')
            self.button('Choose image…', self.browse_image)
        elif obj['type'] != 'rect':
            UI.Label('Content')
            binding = self.binding(oid + ':content', lambda: obj['content'], lambda v: self.apply_content(v, oid))
            draft = self.binding(oid + ':draft', lambda: self.drafts.get(oid, obj['content']), lambda v: self.set_draft(oid, v))
            UI.TextEdit(binding, edit_model=draft).id('content-' + oid).layout(height=90)
        if obj['type'] == 'rect':
            with UI.HBox():
                for key, label, default, minimum in [('stroke_mm', 'Line width', .3, .001), ('radius_mm', 'Corner R', 0, 0)]:
                    self.number(f'{label} ({unit})', display_length(obj.get(key, default), unit),
                                lambda v, k=key: change(k, millimetres(v, unit)), key, minimum)
        if obj['type'] == 'text':
            platform.font_controls(self, obj, change)
            with UI.HBox():
                self.number('Font size (pt)', obj.get('font_size', 12), lambda v: change('font_size', v), 'font-size', 1, 1000)
            with UI.HBox().id('typography-row'):
                self.select('Style', ['normal', 'italic'], obj.get('font_style', 'normal'), lambda v: change('font_style', v), 'style')
                self.select('Weight', ['normal', 'bold'], obj.get('font_weight', 'normal'), lambda v: change('font_weight', v), 'weight')
            if self.template['canvas']['mode'] == 'color':
                with UI.HBox():
                    UI.Label('Color')
                    self.button(obj.get('color', '#000000'), self.choose_color, 'color')

    def variables_panel(self):
        UI.Label('Variables').style(fontWeight=700)
        names = variable_names(self.template)
        for name in names:
            with UI.HBox().id('variable-' + name):
                UI.Label(name)
                UI.TextField(self.binding('variable:' + name, lambda k=name: str(self.template['variables'].get(k, '')),
                                     lambda v, k=name: self.set_variable(k, v))).id(name)
        if not names:
            UI.Label('Use {name} in object content.')

    def set_draft(self, oid, value):
        # TextEdit publishes edits here without redrawing or committing on each key.
        self.drafts[oid] = value
        platform.modified(True)

    def commit_content(self):
        pending, self.drafts = self.drafts, {}
        for oid, value in pending.items():
            self.apply_content(value, oid)

    def changed(self):
        self.modified = True
        reconcile_variables(self.template)
        self.refresh_preview()
        self.notify()

    def set_canvas(self, key, value):
        old = self.template['canvas'][key]
        self.template['canvas'][key] = value
        try:
            dumps(self.template)
        except ValueError as exc:
            self.template['canvas'][key] = old
            self.status = str(exc)
            self.notify()
            return
        self.changed()

    def set_unit(self, unit):
        self.commit_content()
        self.set_canvas('unit', unit)

    def set_rotation(self, value):
        self.commit_content()
        self.drag = None
        self.template['canvas'].setdefault('rotation', 0)
        self.set_canvas('rotation', int(value))

    def preset(self, name):
        if name in LABEL_PRESETS:
            self.template['canvas']['width_mm'], self.template['canvas']['height_mm'] = LABEL_PRESETS[name]
            self.changed()

    def set_object(self, key, value, oid=None):
        obj = self.object_by_id(oid if oid is not None else self.selected)
        if obj is None or obj.get(key) == value:
            return
        old = obj.get(key)
        obj[key] = value
        try:
            dumps(self.template)
        except ValueError as exc:
            obj[key] = old
            self.status = str(exc)
            self.notify()
            return
        self.changed()

    def apply_content(self, value, oid=None):
        oid = oid if oid is not None else self.selected
        self.drafts.pop(oid, None)
        self.set_object('content', value, oid)

    def set_variable(self, key, value):
        self.template['variables'][key] = value
        self.changed()

    def add(self, kind):
        self.commit_content()
        obj = new_object(kind)
        self.template['objects'].append(obj)
        self.selected = obj['id']
        self.changed()

    def delete(self):
        self.commit_content()
        self.template['objects'] = [o for o in self.template['objects'] if o['id'] != self.selected]
        self.selected = None
        self.changed()

    def select_object(self, oid):
        self.commit_content()
        self.selected = oid
        self.notify()

    def refresh_preview(self):
        canvas = self.template['canvas']
        size = tuple(pixels(canvas[k], canvas['dpi']) for k in ('width_mm', 'height_mm'))
        result = Image.new('RGBA', size, 'white')
        errors = []
        for obj in self.template['objects']:
            try:
                tile = object_image(obj, canvas, self.template['variables'])
            except Exception as exc:
                errors.append(f"{obj['type']}: {exc}")
                tile = Image.new('RGBA', (pixels(obj['width_mm'], canvas['dpi']), pixels(obj['height_mm'], canvas['dpi'])), '#ffe4e6')
                ImageDraw.Draw(tile).rectangle((0, 0, tile.width-1, tile.height-1), outline='red', width=2)
            result.alpha_composite(tile, (round(obj['x_mm'] * canvas['dpi'] / 25.4), round(obj['y_mm'] * canvas['dpi'] / 25.4)))
        if canvas['mode'] == 'mono' and not errors:
            result = result.convert('L').point(lambda v: 255 if v >= 128 else 0).convert('RGBA')
        result = result.rotate(-canvas.get('rotation', 0), expand=True)
        result.thumbnail((1024, 1024), Image.Resampling.NEAREST)
        self.preview = result
        self.status = ' | '.join(errors) if errors else f"{size[0]} × {size[1]} px · {canvas['dpi']} DPI · {canvas.get('rotation', 0)}° view · Drag objects to position them"

    def paint(self, canvas):
        c = self.template['canvas']
        vw, vh = view_size(c)
        scale = max(.001, min((canvas.width-24)/vw, (canvas.height-24)/vh))
        w, h = vw*scale, vh*scale
        x, y = (canvas.width-w)/2, (canvas.height-h)/2
        self.viewport = x, y, scale
        canvas.drawRect(0, 0, canvas.width, canvas.height, fill=0x000000)
        resource = canvas.loadRGBA(self.preview.width, self.preview.height, self.preview.tobytes())
        canvas.drawImage(resource, x, y, w, h)
        obj = self.current()
        if obj:
            canvas.push()
            canvas.clipRect(x, y, w, h)
            left, top, right, bottom = view_box(obj, c)
            canvas.drawRect(x+left*scale, y+top*scale, x+right*scale, y+bottom*scale, stroke=0x2563eb, width=2)
            canvas.pop()

    def pointer_down(self, event):
        if event.button != 1:
            return
        self.commit_content()
        x, y, scale = self.viewport
        c = self.template['canvas']
        mx, my = from_view((event.x-x)/scale, (event.y-y)/scale, c)
        hit = None
        if 0 <= mx <= c['width_mm'] and 0 <= my <= c['height_mm']:
            hit = next((o for o in reversed(self.template['objects']) if
                        o['x_mm'] <= mx <= o['x_mm']+o['width_mm'] and
                        o['y_mm'] <= my <= o['y_mm']+o['height_mm']), None)
        self.selected = hit['id'] if hit else None
        self.drag = (mx-hit['x_mm'], my-hit['y_mm']) if hit else None
        self.notify()

    def pointer_move(self, event):
        obj = self.current()
        if self.drag is None or obj is None:
            return
        x, y, scale = self.viewport
        c = self.template['canvas']
        mx, my = from_view((event.x-x)/scale, (event.y-y)/scale, c)
        obj['x_mm'] = max(0, min(max(0, c['width_mm']-obj['width_mm']), mx-self.drag[0]))
        obj['y_mm'] = max(0, min(max(0, c['height_mm']-obj['height_mm']), my-self.drag[1]))
        self.changed()

    def pointer_up(self, event):
        self.drag = None

    def browse_image(self):
        path = UI.OpenFile(title='Choose image', types={'Images': ['png', 'jpg', 'jpeg', 'bmp', 'gif', 'webp'], 'All files': ['*']})
        if path:
            try:
                if Path(path).stat().st_size > 100 * 1024 * 1024:
                    raise ValueError('Image exceeds 100 MiB')
                data = Path(path).read_bytes()
                from io import BytesIO
                with Image.open(BytesIO(data)) as image:
                    image.verify()
                obj = self.current()
                candidate = dict(obj, data=data, image_name=Path(path).name, content='')
                updated = dict(self.template, objects=[candidate if item is obj else item for item in self.template['objects']])
                dumps(updated)
                obj.update(candidate)
                self.changed()
            except (OSError, ValueError) as exc:
                UI.Warning(str(exc), title='Image error')

    def choose_color(self):
        value = UI.Prompt('Enter a color (e.g. #ff0000)', title='Text color', default=self.current().get('color', '#000000'))
        if value is not None:
            try:
                ImageColor.getrgb(value)
                self.set_object('color', value)
            except ValueError:
                UI.Warning('Enter a valid color name or hex value.', title='Invalid color')

    def confirm_discard(self):
        self.commit_content()
        if not self.modified:
            return True
        if UI.Confirm('Save changes before continuing?', title='Unsaved changes'):
            return self.save()
        return UI.Confirm('Discard unsaved changes and continue?', title='Unsaved changes')

    def new(self):
        if self.confirm_discard():
            self.template, self.path, self.selected, self.modified = new_template(), None, None, False
            self.drafts.clear()
            self.bindings.clear()
            self.project_dir = None
            self.refresh_preview()
            self.notify()

    def load_path(self, path):
        try:
            template, directory = open_document(path)
            template = platform.prepare_template(template)
            self.template, self.project_dir = template, directory
            self.path, self.selected, self.modified = Path(path), None, False
            self.drafts.clear()
            self.bindings.clear()
            self.refresh_preview()
            self.notify()
        except (OSError, ValueError) as exc:
            UI.Warning(str(exc), title='Open error')

    def open(self):
        if not self.confirm_discard():
            return
        path = UI.OpenFile(title='Open template', types=['lbl'])
        if path:
            self.load_path(path)

    def save(self):
        self.commit_content()
        path = UI.SaveFile(default='label.lbl', title='Save label', types=['lbl'])
        if not path:
            return False
        try:
            self.status = platform.save_document(self.template, path, self.project_dir)
            self.modified = False
            self.notify()
            return True
        except (OSError, ValueError) as exc:
            UI.Warning(str(exc), title='Save error')
            return False

    def export(self):
        self.commit_content()
        try:
            image = render(dumps(self.template), {})
            path = UI.SaveFile(default='label.png', title='Export PNG', types=['png'])
            if path:
                image.save(path, format='PNG', dpi=image.info['dpi'])
                self.status = f'Exported {path}'
                self.notify()
        except (OSError, ValueError) as exc:
            UI.Warning(str(exc), title='Export error')


def main():
    return Labelate().start()
