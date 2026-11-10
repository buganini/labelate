"""Desktop integrations. The Pyodide build replaces this module, not at runtime."""
import copy
import os
from pathlib import Path

import PUI.PySide6 as UI
from PySide6 import QtCore, QtWidgets

from .model import dumps

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


def font_controls(editor, obj, change):
    with UI.HBox():
        UI.Label('Font file')
        UI.TextField(obj('font'), placeholder='Default font').id('font')
        def choose():
            path = UI.OpenFile(title='Choose font', types={'Fonts': ['ttf', 'otf', 'ttc']})
            if path:
                change('font', str(Path(path).resolve()))
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
