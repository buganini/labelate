"""Desktop integrations. The Pyodide build replaces this module, not at runtime."""
import copy
import os
from pathlib import Path

import PUI.PySide6 as UI
from PySide6 import QtCore, QtWidgets

from .model import dumps
from .template_io import asset_fields


class CloseGuard(QtCore.QObject):
    def __init__(self, editor):
        super().__init__(editor.ui)
        self.editor = editor

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.Close and isinstance(watched, QtWidgets.QMainWindow):
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
        UI.TextField(editor.binding(obj['id'] + ':font', lambda: obj.get('font', ''),
                                    lambda value: change('font', value)), placeholder='Default font').id('font')
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
        for field in asset_fields(obj):
            if obj.get(field):
                obj[field] = os.path.relpath(Path(obj[field]).expanduser().resolve(), Path(path).resolve().parent)
    Path(path).write_text(dumps(document), encoding='utf-8')
    return f'Saved {path}'
