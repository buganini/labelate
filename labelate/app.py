"""Declarative QPUIQ editor, including its canvas and input controls."""
import math
import copy
from pathlib import Path

import PUI.PySide6 as UI
from PUI.state import Unstate
from PIL import Image, ImageDraw, ImageColor

from .model import (new_template, new_object, variable_names, reconcile_variables,
                    dumps, display_length, millimetres, UNIT_MM)
from .renderer import render, object_image, pixels
from .template_io import open_document
from .data_import import read_data
from .geometry import view_size, view_box, from_view
from . import platform


OBJECT_NAMES = {'text': 'Text', 'image': 'Image', 'qr': 'QR', 'code128': 'Code128', 'rect': 'Rect'}


class Labelate(UI.Application):
    def __init__(self):
        super().__init__()
        self.template, self.path = new_template(), None
        self.selected, self.modified = None, False
        self.state = UI.State()
        self.state.revision = 0
        self.state.selected_data_row = None
        self.state.objects = UI.State([])
        self.template['objects'] = self.state.objects
        self.template['data_rows'] = UI.State([])
        self.object_inputs = {}
        self.accepted_objects = {}
        self.state.active_tab = 'Label'
        self.brand = 'File'
        self.printers = []
        self.printer_choice = 'PNG'
        self.state.copies = '1'
        self.busy = False
        self.print_message = ''
        self.printer_configs = {}
        self.settings_open = False
        self.settings_draft = {}
        self.model_choices = []
        self.stock_choices = []
        self.pending_print = False
        self.drag = None
        self.viewport = (0, 0, 1)
        self.preview = None
        self.status = ''
        self.project_dir = None
        self.inputs = UI.State({})
        self.input_callbacks = {}
        self.binding_scope = "label"
        self.refresh_preview()

    def snapshot(self):
        """Detach reactive objects at the persistence/render/worker boundary."""
        return {**self.template, 'objects': Unstate(self.state.objects),
                'data_rows': Unstate(self.template['data_rows'])}

    def install_template(self, template):
        with self.state:
            self.state.selected_data_row = None
            self.object_inputs.clear()
            self.accepted_objects.clear()
            self.template = dict(template)
            objects = [self.make_object_state(obj) for obj in template['objects']]
            self.state.objects.clear()
            self.state.objects.extend(objects)
            self.template = {**template, 'objects': self.state.objects,
                             'data_rows': UI.State([self.make_data_row(row) for row in template.get('data_rows', [])])}

    def make_object_state(self, data):
        # Supply defaults for fields omitted by older templates before binding them.
        values = {**new_object(data['type']), **data}
        for key in self.NUMBER_FIELDS:
            values[key] = float(values[key])
        obj = UI.State(values)
        oid = obj['id']
        self.accepted_objects[oid] = Unstate(obj)
        inputs = self.object_inputs[oid] = UI.State({
            key: self.object_number_text(obj, key) for key in self.NUMBER_FIELDS})
        inputs['font_family'] = platform.font_family(obj)
        for key in self.NUMBER_FIELDS:
            inputs(key).change(lambda value, k=key: self.commit_object_number(obj, k, value))
        for key in obj.keys():
            obj(key).change(lambda value, item=obj: self.object_state_changed(item))
        return obj

    NUMBER_FIELDS = ('x_mm', 'y_mm', 'width_mm', 'height_mm', 'stroke_mm', 'radius_mm', 'font_size')

    def object_number_text(self, obj, key):
        value = obj[key]
        if key.endswith('_mm'):
            value = display_length(value, self.template['canvas']['unit'])
        return f'{value:.3f}'.rstrip('0').rstrip('.')

    def sync_object_inputs(self, obj):
        with self.state:
            for key in self.NUMBER_FIELDS:
                self.object_inputs[obj['id']][key] = self.object_number_text(obj, key)

    def commit_object_number(self, obj, key, text):
        if self.object_by_id(obj['id']) is not obj:
            return
        inputs = self.object_inputs[obj['id']]
        # Ignore old notifications and formatted values synchronized from the model.
        if inputs[key] != text or text == self.object_number_text(obj, key):
            return
        try:
            value = float(text)
            minimum = 0 if key in ('x_mm', 'y_mm', 'radius_mm') else 1 if key == 'font_size' else .001
            maximum = 1000 if key == 'font_size' else 10000
            if not math.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError(f'{key} must be between {minimum} and {maximum}')
            if key.endswith('_mm'):
                value = millimetres(value, self.template['canvas']['unit'])
            obj[key] = value
        except ValueError as exc:
            self.status = str(exc)
            self.sync_object_inputs(obj)
            self.notify()

    def object_state_changed(self, obj):
        oid = obj['id']
        if self.object_by_id(oid) is not obj:
            return
        previous = self.accepted_objects[oid]
        current = Unstate(obj)
        if current == previous:
            return
        try:
            dumps(self.snapshot())
        except ValueError as exc:
            with self.state:
                for key, value in previous.items():
                    obj[key] = value
                self.sync_object_inputs(obj)
                self.status = str(exc)
                self.notify()
            return
        self.accepted_objects[oid] = current
        if current.get('font') != previous.get('font') or current.get('font_index') != previous.get('font_index'):
            self.object_inputs[oid]['font_family'] = platform.font_family(obj)
        self.changed()

    def object_number(self, label, obj, key):
        UI.Label(label)
        return UI.TextField(self.object_inputs[obj['id']](key)).id(key).layout(minWidth=48)

    def object_select(self, label, choices, obj, key):
        UI.Label(label)
        with UI.ComboBox(text_model=obj(key)).id(key):
            for choice in choices:
                UI.ComboBoxItem(choice.title(), value=choice)

    def update(self, prev=None):
        self.prepare_inputs()
        super().update(prev)
        platform.attach(self)

    def prepare_inputs(self):
        """Synchronize converted form values before entering the UI builder."""
        canvas = self.template['canvas']
        unit = canvas['unit']
        values = {
            'label:unit': unit,
            'label:rotation': str(canvas.get('rotation', 0)),
            'label:mode': canvas['mode'].title(),
            'brand': self.brand,
            'printer': self.printer_choice,
            'print-settings': self.settings_open,
            'printer-settings:printer-model': self.settings_draft.get('model', ''),
            'printer-settings:printer-stock': self.settings_draft.get('stock', '62'),
            'printer-settings:printer-media': self.settings_draft.get('media', 'gap'),
            'printer-gap': self.settings_draft.get('gap', '2'),
            'printer-baud': self.settings_draft.get('baudrate', '9600'),
        }
        for key in ('width_mm', 'height_mm', 'dpi'):
            value = canvas[key] if key == 'dpi' else display_length(canvas[key], unit)
            values['label:' + key] = f'{value:.3f}'.rstrip('0').rstrip('.')
        values.update(('variable:' + key, str(value)) for key, value in self.template['variables'].items())
        self.input_values = values
        with self.inputs:
            for key, value in values.items():
                if key not in self.inputs:
                    self.inputs[key] = value
                    self.inputs(key).change(lambda value, k=key: self.commit_input(k, value))
                else:
                    self.inputs[key] = value

    def input_state(self, key, setter):
        self.input_callbacks[key] = setter
        return self.inputs(key)

    def commit_input(self, key, value):
        # Model-to-form synchronization does not run user edit actions.
        if self.inputs[key] != value or self.input_values[key] == value:
            return
        self.input_callbacks[key](value)

    def notify(self):
        self.state.revision += 1
        platform.modified(self.modified)

    def current(self):
        return self.object_by_id(self.selected)

    def object_by_id(self, key):
        return next((obj for obj in self.template['objects'] if obj['id'] == key), None)

    def button(self, text, action, key=None, disabled=False):
        return UI.Button(text, disabled=disabled).id(key or text).click(lambda event: action())

    def select(self, label, choices, value, setter, key):
        UI.Label(label)
        with UI.ComboBox(text_model=self.input_state(self.binding_scope + ':' + key, setter)).id(key):
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
        return UI.TextField(self.input_state(self.binding_scope + ':' + key, commit)).id(key).layout(minWidth=48)

    def content(self):
        _ = self.state.revision
        with UI.Window(title='Labelate — Label Template Editor', size=(1280, 800), maximize=True).id('window'):
            with UI.VBox().layout(padding=10):
                with UI.Tabs(model=self.state('active_tab')).id('tabs').layout(weight=1):
                    with UI.Tab('Label').id('Label'):
                        with UI.HBox().id('toolbar'):
                            for title, action in [('New', self.new), ('Open .lbl', self.open), ('Save .lbl', self.save)]:
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

    def data_panel(self):
        names = variable_names(self.template)
        rows = self.template.get('data_rows', [])
        with UI.HBox():
            self.button('Import XLSX/CSV', self.import_data)
            self.button('Add row', self.add_data_row)
            self.button('Remove selected row', self.remove_data_row,
                        disabled=not any(id(row) == self.state.selected_data_row for row in rows))
            UI.Label(f'{len(rows)} row(s) · one label per row')
            UI.Spacer()
        if not names:
            UI.Label('Add {variables} in the Label tab to create data columns.')
        with UI.Table(columnHeader=names, rowHeader=[str(i + 1) for i in range(len(rows))]).id('data-table').layout(weight=1):
            for i, row in enumerate(rows):
                with UI.TableNode().id(f'data-row-{id(row)}'):
                    for name in names:
                        UI.TableNode(row(name)).id(name).click(self.select_data_row, id(row))

    def import_data(self):
        path = UI.OpenFile(title='Import data', types={'Tables': ['xlsx', 'csv']})
        if not path:
            return
        try:
            rows = read_data(path, variable_names(self.template))
            dumps({**self.snapshot(), 'data_rows': rows})
            prepared = [self.make_data_row(row) for row in rows]
            with self.state:
                target = self.template['data_rows']
                target.clear()
                target.extend(prepared)
                self.state.selected_data_row = None
                self.modified = True
                self.print_message = f'Imported {len(rows)} row(s) from {Path(path).name}.'
                self.notify()
        except Exception as exc:
            self.print_message = f'Import failed: {exc}'
            self.notify()

    def add_data_row(self):
        if (len(self.template.get('data_rows', [])) + 1) * max(1, len(variable_names(self.template))) > 10000:
            self.print_message = 'Data table exceeds 10,000 cells'
            self.notify()
            return
        self.template['data_rows'].append(self.make_data_row(dict(self.template['variables'])))
        self.modified = True
        self.notify()

    def select_data_row(self, event, row_id):
        self.state.selected_data_row = row_id

    def remove_data_row(self):
        rows = self.template['data_rows']
        index = next((i for i, row in enumerate(rows)
                      if id(row) == self.state.selected_data_row), None)
        if index is None:
            return
        with self.state:
            rows.pop(index)
            self.state.selected_data_row = None
            self.modified = True
        self.notify()

    def make_data_row(self, values):
        row = UI.State({name: str(values.get(name, self.template['variables'].get(name, '')))
                        for name in variable_names(self.template)})
        for name in row.keys():
            row(name).change(lambda value: self.data_changed())
        return row

    def data_changed(self):
        self.modified = True
        platform.modified(True)

    def print_panel(self):
        with UI.HBox().id('message-bar'):
            UI.Label(self.print_message or self.status).id('status').layout(weight=1)
            UI.Spacer()
            UI.Label("Output")
            with UI.ComboBox(text_model=self.input_state('brand', self.set_brand),
                             disabled=self.busy).id('printer-brand'):
                for brand in (('File', 'Brother', 'Niim', 'TSC') if platform.PRINTING else ('File',)):
                    UI.ComboBoxItem(brand)
            with UI.ComboBox(text_model=self.input_state('printer', self.set_printer),
                             disabled=self.busy or not self.brand).id('printer-device'):
                UI.ComboBoxItem('PNG' if self.brand == 'File' else 'Scan for printers…')
                for printer in self.printers:
                    UI.ComboBoxItem(printer.display)
                if self.selected_printer():
                    UI.ComboBoxItem('Printer settings…')
            disabled = self.busy or (self.brand != 'File' and not self.selected_printer())
            if self.state.active_tab == 'Label':
                UI.Label('Copies')
                binding = self.state('copies')
                UI.TextField(binding, edit_model=binding).id('copies').layout(width=60)
                self.button('Print Single Label', self.request_print, disabled=disabled)
            else:
                self.button('Print All', self.request_print, disabled=disabled or not self.template.get('data_rows'))

    def selected_printer(self):
        return next((p for p in self.printers if p.display == self.printer_choice), None)

    def set_brand(self, value):
        if self.busy or value not in (('File', 'Brother', 'Niim', 'TSC') if platform.PRINTING else ('File',)):
            return
        self.brand = value
        self.printers = []
        self.printer_choice = 'PNG' if value == 'File' else 'Scan for printers…'
        self.print_message = ''
        if value == 'File':
            self.notify()
        else:
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
        if self.busy or self.brand == 'File' or not self.brand or not platform.PRINTING:
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
        with UI.Modal(self.input_state('print-settings', self.close_settings),
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
                        UI.TextField(self.input_state('printer-gap', lambda value: self.set_print_setting('gap', value)))
                    if self.selected_printer() and self.selected_printer().backend == 'serial':
                        with UI.HBox():
                            UI.Label('Baud rate')
                            UI.TextField(self.input_state('printer-baud', lambda value: self.set_print_setting('baudrate', value)))
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
        if not self.busy and self.brand == 'File':
            self.export()
            return
        if self.busy or not platform.PRINTING or not self.selected_printer():
            return
        from . import printing
        try:
            copies = printing.positive_integer(self.state.copies) if self.state.active_tab == 'Label' else 1
            rows = Unstate(self.template.get('data_rows', [])) if self.state.active_tab == 'Data' else [{}]
            if not rows:
                raise ValueError('No data rows to print')
            config = self.printer_configs.get(self.config_key())
            if not config:
                self.configure_printer(True)
                return
            template_bytes = dumps(self.snapshot())
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
        with UI.HBox().id('dimensions-row'):
            for key, label in [('width_mm', 'Width'), ('height_mm', 'Height')]:
                self.number(label, display_length(canvas[key], unit),
                            lambda v, k=key: self.set_canvas(k, millimetres(v, unit)), key, .001).layout(width=40, minWidth=40)
            self.select('Unit', list(UNIT_MM), unit, self.set_unit, 'unit')
            self.select('Rotation', ['0', '90', '180', '270'], str(canvas.get('rotation', 0)),
                        self.set_rotation, 'rotation')
        with UI.HBox().id('output-row'):
            self.number('DPI', canvas['dpi'], lambda v: self.set_canvas('dpi', round(v)), 'dpi', 36, 2400).layout(width=40, minWidth=40)
            self.select('Mode', ['Greyscale', 'Color'], canvas['mode'].title(), lambda v: self.set_canvas('mode', v.lower()), 'mode')

    def objects_panel(self):
        UI.Label('Objects').style(fontWeight=700)
        with UI.HBox().id('object-toolbar'):
            for kind, label in OBJECT_NAMES.items():
                self.button(label, lambda k=kind: self.add(k))
            UI.Spacer()
            if self.current():
                self.button('Delete selected', self.delete)
        with UI.Scroll().id('object-list').layout(height=125):
            with UI.VBox():
                for obj in self.template['objects']:
                    prefix = '● ' if obj['id'] == self.selected else ''
                    self.button(f"{prefix}{OBJECT_NAMES[obj['type']]}" if obj['type'] == 'image' else f"{prefix}{OBJECT_NAMES[obj['type']]} · {obj['content'][:32]}",
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
            self.object_number(f'X ({unit})', obj, 'x_mm').layout(width=40, minWidth=40)
            self.object_number(f'Y ({unit})', obj, 'y_mm').layout(width=40, minWidth=40)
            self.object_number(f'W ({unit})', obj, 'width_mm').layout(width=40, minWidth=40)
            self.object_number(f'H ({unit})', obj, 'height_mm').layout(width=40, minWidth=40)
        if obj['type'] == 'image':
            with UI.HBox():
                UI.Label('Image')
                self.button('Choose image…', self.browse_image)
        elif obj['type'] != 'rect':
            UI.Label('Content')
            UI.TextEdit(obj('content')).input(self.content_edited).id('content-' + oid).layout(height=90)
        if obj['type'] == 'rect':
            with UI.HBox():
                self.object_number(f'Line width ({unit})', obj, 'stroke_mm')
                self.object_number(f'Corner R ({unit})', obj, 'radius_mm')
        if obj['type'] == 'text':
            platform.font_controls(self, obj, change)
            with UI.HBox().id('typography-row'):
                self.object_number('Size', obj, 'font_size').layout(width=60)
                self.object_select('Style', ['normal', 'italic'], obj, 'font_style')
                self.object_select('Weight', ['normal', 'bold'], obj, 'font_weight')
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
                UI.TextField(self.input_state('variable:' + name, lambda v, k=name: self.set_variable(k, v))).id(name)
        if not names:
            UI.Label('Use {name} in object content.')

    def content_edited(self, event):
        self.modified = True
        platform.modified(True)

    def changed(self):
        self.modified = True
        reconcile_variables(self.template)
        for row in self.template['data_rows']:
            for name in variable_names(self.template):
                if name not in row:
                    row[name] = str(self.template['variables'].get(name, ''))
                    row(name).change(lambda value: self.data_changed())
        for obj in self.state.objects:
            self.sync_object_inputs(obj)
        self.refresh_preview()
        self.notify()

    def set_canvas(self, key, value):
        old = self.template['canvas'][key]
        self.template['canvas'][key] = value
        try:
            dumps(self.snapshot())
        except ValueError as exc:
            self.template['canvas'][key] = old
            self.status = str(exc)
            self.notify()
            return
        self.changed()

    def set_unit(self, unit):
        self.set_canvas('unit', unit)

    def set_rotation(self, value):
        self.drag = None
        self.template['canvas'].setdefault('rotation', 0)
        self.set_canvas('rotation', int(value))

    def set_object(self, key, value, oid=None):
        obj = self.object_by_id(oid if oid is not None else self.selected)
        if obj is None or obj.get(key) == value:
            return
        obj[key] = value

    def set_variable(self, key, value):
        self.template['variables'][key] = value
        self.changed()

    def add(self, kind):
        obj = self.make_object_state(new_object(kind))
        self.state.objects.append(obj)
        self.selected = obj['id']
        self.changed()

    def delete(self):
        obj = self.current()
        if obj is not None:
            self.state.objects.remove(obj)
            self.object_inputs.pop(obj['id'], None)
            self.accepted_objects.pop(obj['id'], None)
        self.selected = None
        self.changed()

    def select_object(self, oid):
        self.selected = oid
        self.notify()

    def refresh_preview(self):
        canvas = self.template['canvas']
        size = tuple(pixels(length, canvas['dpi']) for length in view_size(canvas))
        result = Image.new('RGBA', size, 'white')
        errors = []
        for obj in self.template['objects']:
            try:
                tile = object_image(obj, canvas, self.template['variables'])
            except Exception as exc:
                errors.append(f"{OBJECT_NAMES[obj['type']]}: {exc}")
                tile = Image.new('RGBA', (pixels(obj['width_mm'], canvas['dpi']), pixels(obj['height_mm'], canvas['dpi'])), '#ffe4e6')
                ImageDraw.Draw(tile).rectangle((0, 0, tile.width-1, tile.height-1), outline='red', width=2)
            result.alpha_composite(tile, (round(obj['x_mm'] * canvas['dpi'] / 25.4), round(obj['y_mm'] * canvas['dpi'] / 25.4)))
        if canvas['mode'] == 'greyscale' and not errors:
            result = result.convert('L').convert('RGBA')
        result.thumbnail((1024, 1024), Image.Resampling.NEAREST)
        self.preview = result
        self.status = ' | '.join(errors) if errors else f"{size[0]} × {size[1]} px · {canvas['dpi']} DPI · {canvas.get('rotation', 0)}° view · Drag objects to position them"

    def paint(self, canvas):
        c = self.template['canvas']
        vw, vh = view_size(c)
        padding = 50
        scale = max(.001, min((canvas.width - 2 * padding) / vw,
                             (canvas.height - 2 * padding) / vh))
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
        x, y, scale = self.viewport
        c = self.template['canvas']
        mx, my = from_view((event.x-x)/scale, (event.y-y)/scale, c)
        hit = None
        vw, vh = view_size(c)
        if 0 <= mx <= vw and 0 <= my <= vh:
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
        vw, vh = view_size(c)
        with self.state:
            obj['x_mm'] = max(0, min(max(0, vw-obj['width_mm']), mx-self.drag[0]))
            obj['y_mm'] = max(0, min(max(0, vh-obj['height_mm']), my-self.drag[1]))

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
                candidate = dict(obj, data=data, content='')
                updated = dict(self.snapshot(), objects=[candidate if item is obj else Unstate(item) for item in self.state.objects])
                dumps(updated)
                with self.state:
                    for key, value in candidate.items():
                        obj[key] = value
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
        if not self.modified:
            return True
        if UI.Confirm('Save changes before continuing?', title='Unsaved changes'):
            return self.save()
        return UI.Confirm('Discard unsaved changes and continue?', title='Unsaved changes')

    def new(self):
        if self.confirm_discard():
            self.install_template(new_template())
            self.path, self.selected, self.modified = None, None, False
            self.input_callbacks.clear()
            self.inputs = UI.State({})
            self.project_dir = None
            self.refresh_preview()
            self.notify()

    def load_path(self, path):
        try:
            template, directory = open_document(path)
            template = platform.prepare_template(template)
            self.install_template(template)
            self.project_dir = directory
            self.path, self.selected, self.modified = Path(path), None, False
            self.input_callbacks.clear()
            self.inputs = UI.State({})
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
        path = UI.SaveFile(default='label.lbl', title='Save label', types=['lbl'])
        if not path:
            return False
        try:
            self.status = platform.save_document(self.snapshot(), path, self.project_dir)
            self.modified = False
            self.notify()
            return True
        except (OSError, ValueError) as exc:
            UI.Warning(str(exc), title='Save error')
            return False

    def export(self):
        from io import BytesIO
        from .printing import positive_integer

        try:
            copies = positive_integer(self.state.copies) if self.state.active_tab == 'Label' else 1
            rows = Unstate(self.template.get('data_rows', [])) if self.state.active_tab == 'Data' else [{}]
            if not rows:
                raise ValueError('No data rows to export')
            template = dumps(self.snapshot())
            total = len(rows) * copies
            files = []
            for row in rows:
                image = render(template, row)
                png = BytesIO()
                image.save(png, format='PNG', dpi=image.info['dpi'])
                for _ in range(copies):
                    files.append((f'label-{len(files)+1:04d}.png', png.getvalue()))
            if total == 1:
                path = UI.SaveFile(default='label.png', title='Export PNG', types=['png'])
                if path:
                    Path(path).write_bytes(files[0][1])
            else:
                path = platform.save_pngs(files)
            if path:
                self.print_message = f'Exported {total} PNG label(s) to {path}'
                self.notify()
        except Exception as exc:
            UI.Warning(str(exc), title='Export error')


def main():
    return Labelate().start()
