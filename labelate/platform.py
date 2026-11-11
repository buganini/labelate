"""Desktop integrations. The Pyodide build replaces this module, not at runtime."""
import copy
import os
from pathlib import Path

import PUI.PySide6 as UI
from PySide6 import QtCore, QtWidgets

from .model import dumps
from .system_fonts import system_fonts
from PIL import ImageFont

PRINTING = True


class CloseGuard(QtCore.QObject):
    def __init__(self, editor):
        super().__init__(editor.ui)
        self.editor = editor

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.Close and isinstance(watched, QtWidgets.QMainWindow):
            if self.editor.busy:
                self.editor.print_message = "Wait for the printer operation to finish before closing."
                self.editor.notify()
                event.ignore()
                return True
            if not self.editor.confirm_discard():
                event.ignore()
                return True
        return super().eventFilter(watched, event)


def attach(editor):
    if not hasattr(editor, '_close_guard'):
        editor._close_guard = CloseGuard(editor)
        editor.ui.installEventFilter(editor._close_guard)


def modified(value):
    pass


def font_family(obj):
    try:
        return ImageFont.truetype(obj['font'], 12, index=obj.get('font_index', 0)).getname()[0] if obj['font'] else ''
    except (OSError, ValueError):
        return ''


def font_controls(editor, obj, change):
    inputs = editor.object_inputs[obj['id']]

    def select_family(event):
        family = inputs['font_family']
        resolved = system_fonts().get(family)
        if resolved is None:
            editor.status = f'Cannot locate a Pillow-readable font file for {family}. Choose a font file instead.'
            editor.notify()
            return
        path, index = resolved
        with editor.state:
            obj['font_index'] = index
            change('font', path)

    with UI.HBox():
        UI.Label('Font')
        UI.FontComboBox(inputs('font_family')).id('font-family').change(select_family)
    with UI.HBox():
        UI.Label('Font file')
        UI.TextField(obj('font'), placeholder='Default font').id('font')
        def choose():
            path = UI.OpenFile(title='Choose font', types={'Fonts': ['ttf', 'otf', 'ttc']})
            if path:
                with editor.state:
                    obj['font_index'] = 0
                    change('font', str(Path(path).resolve()))
                    try:
                        inputs['font_family'] = ImageFont.truetype(path, 12).getname()[0]
                    except (OSError, ValueError):
                        inputs['font_family'] = ''
        editor.button('Choose font…', choose)


def prepare_template(template):
    return template


def save_document(template, path, project_dir):
    document = copy.deepcopy(template)
    for obj in document['objects']:
        if obj['type'] == 'text' and obj.get('font'):
            obj['font'] = os.path.relpath(Path(obj['font']).expanduser().resolve(), Path(path).resolve().parent)
    Path(path).write_bytes(dumps(document))
    return f'Saved {path}'


def run_background(editor, work, done):
    from threading import Thread
    post = editor.children[0].get_poster()
    def progress(message):
        def update():
            editor.print_message = message
            editor.notify()
        post(update)
    def run():
        try:
            result = work(progress)
        except Exception as exc:
            post(lambda error=exc: done(None, error))
        else:
            post(lambda: done(result, None))
    Thread(target=run, daemon=True, name='labelate-printer').start()


def save_pngs(files):
    directory = UI.OpenDirectory(title='Export PNG labels')
    if not directory:
        return None
    root = Path(directory)
    paths = [root / name for name, data in files]
    if any(path.exists() for path in paths):
        if not UI.Confirm('Replace existing label PNG files in this folder?', title='Replace files'):
            return None
    for path, (_, data) in zip(paths, files):
        path.write_bytes(data)
    return directory
