"""Declarative QPUIQ editor, including its canvas and input controls."""
import math
import zipfile
from pathlib import Path

import PUI.pyodide as UI
from PIL import Image, ImageDraw, ImageColor

from .model import (new_template, new_object, variable_names, reconcile_variables,
                    dumps, display_length, millimetres, LABEL_PRESETS, UNIT_MM)
from .renderer import render, object_image, pixels
from .template_io import open_document, portable_document, write_package


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
        self.drafts = {}
        self.drag = None
        self.viewport = (0, 0, 1)
        self.preview = None
        self.status = ''
        self.project_dir = None
        self.bindings = {}
        self.binding_scope = "label"
        self.refresh_preview()

    def binding(self, key, get, set):
        binding = self.bindings.get(key)
        if binding is None:
            binding = self.bindings[key] = Binding(get, set)
        else:
            binding.get, binding.set = get, set
        return binding

    def notify(self):
        self.state.revision += 1
        from _labelate_bridge import modified
        modified(self.modified or any(self.object_by_id(k) and self.object_by_id(k)['content'] != v
                                      for k, v in self.drafts.items()))

    def current(self):
        return self.object_by_id(self.selected)

    def object_by_id(self, key):
        return next((obj for obj in self.template['objects'] if obj['id'] == key), None)

    def button(self, text, action, key=None):
        return UI.Button(text).id(key or text).click(lambda event: action())

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
                with UI.HBox().id('toolbar'):
                    for title, action in [('New', self.new), ('Open JSON / ZIP', self.open), ('Open folder', self.open_folder),
                                          ('Save JSON', self.save), ('Save ZIP', self.save_package), ('Export PNG', self.export)]:
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
                UI.Label(self.status).id('status')

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
            self.button('Rotate', self.rotate_label)
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
                    self.button(f"{prefix}{obj['type']} · {obj['content'][:32]}",
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
            UI.TextEdit(self.binding(oid + ':image-path', lambda: obj['content'], lambda v: None), readonly=True).id('image-path').layout(height=50)
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
            with UI.HBox():
                UI.Label('Font file')
                UI.TextField(self.binding(oid + ':font', lambda: obj.get('font', ''), lambda v: change('font', v)), placeholder='Default font').id('font')
                self.button('Choose font…', self.browse_font)
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
        from _labelate_bridge import modified
        modified(True)

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

    def rotate_label(self):
        canvas = self.template['canvas']
        canvas['width_mm'], canvas['height_mm'] = canvas['height_mm'], canvas['width_mm']
        self.changed()

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
        result.thumbnail((1024, 1024), Image.Resampling.NEAREST)
        self.preview = result
        self.status = ' | '.join(errors) if errors else f"{size[0]} × {size[1]} px · {canvas['dpi']} DPI · Drag objects to position them"

    def paint(self, canvas):
        c = self.template['canvas']
        scale = max(.001, min((canvas.width-24)/c['width_mm'], (canvas.height-24)/c['height_mm']))
        w, h = c['width_mm']*scale, c['height_mm']*scale
        x, y = (canvas.width-w)/2, (canvas.height-h)/2
        self.viewport = x, y, scale
        canvas.drawRect(0, 0, canvas.width, canvas.height, fill=0x000000)
        resource = canvas.loadRGBA(self.preview.width, self.preview.height, self.preview.tobytes())
        canvas.drawImage(resource, x, y, w, h)
        obj = self.current()
        if obj:
            canvas.push()
            canvas.clipRect(x, y, w, h)
            left, top = x+obj['x_mm']*scale, y+obj['y_mm']*scale
            canvas.drawRect(left, top, left+obj['width_mm']*scale, top+obj['height_mm']*scale, stroke=0x2563eb, width=2)
            canvas.pop()

    def pointer_down(self, event):
        if event.button != 1:
            return
        self.commit_content()
        x, y, scale = self.viewport
        mx, my = (event.x-x)/scale, (event.y-y)/scale
        c = self.template['canvas']
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
        obj['x_mm'] = max(0, min(max(0, c['width_mm']-obj['width_mm']), (event.x-x)/scale-self.drag[0]))
        obj['y_mm'] = max(0, min(max(0, c['height_mm']-obj['height_mm']), (event.y-y)/scale-self.drag[1]))
        self.changed()

    def pointer_up(self, event):
        self.drag = None

    def browse_image(self):
        path = UI.OpenFile(title='Choose image', types={'Images': ['png', 'jpg', 'jpeg', 'bmp', 'gif', 'webp']})
        if path:
            self.apply_content(str(Path(path).resolve()))

    def browse_font(self):
        path = UI.OpenFile(title='Choose font', types={'Fonts': ['ttf', 'otf', 'ttc']})
        if path:
            self.set_object('font', str(Path(path).resolve()))

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
            self.template, self.project_dir = template, directory
            self.path, self.selected, self.modified = Path(path), None, False
            self.drafts.clear()
            self.bindings.clear()
            self.refresh_preview()
            self.notify()
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            UI.Warning(str(exc), title='Open error')

    def open(self):
        if not self.confirm_discard():
            return
        path = UI.OpenFile(title='Open template', types=['json', 'zip'])
        if path:
            self.load_path(path)

    def open_folder(self):
        if not self.confirm_discard():
            return
        folder = UI.OpenDirectory(title='Open template folder')
        if folder:
            candidates = sorted(Path(folder).rglob('*.json'))
            if len(candidates) != 1:
                UI.Warning('Choose a folder containing exactly one JSON template and its assets.', title='Open folder')
            else:
                self.load_path(candidates[0])

    def save(self):
        self.commit_content()
        path = UI.SaveFile(default='label.json', title='Save JSON', types=['json'])
        if not path:
            return False
        try:
            document, assets = portable_document(self.template, self.project_dir)
            # Write the exact allocated download path; changing its suffix breaks PUI's download registry.
            Path(path).write_text(dumps(document), encoding='utf-8')
            self.modified = False
            self.status = 'JSON ready to download. Use Save ZIP to include referenced images and fonts.' if assets else 'JSON ready to download.'
            self.notify()
            return True
        except (OSError, ValueError) as exc:
            UI.Warning(str(exc), title='Save error')
            return False

    def save_package(self):
        self.commit_content()
        path = UI.SaveFile(default='label.zip', title='Save ZIP', types=['zip'])
        if not path:
            return False
        try:
            write_package(path, self.template, self.project_dir)
            self.modified = False
            self.status = 'Template ZIP ready to download, including referenced images and fonts.'
            self.notify()
            return True
        except (OSError, ValueError) as exc:
            UI.Warning(str(exc), title='ZIP export error')
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
