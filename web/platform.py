"""Build-time replacement for desktop integrations in the Pyodide archive."""
from pathlib import Path
import PUI.pyodide as UI
from .model import dumps

PRINTING = False


def attach(editor):
    pass


def modified(value):
    from _labelate_bridge import modified as publish
    publish(value)


def font_family(obj):
    return ''


def font_controls(editor, obj, change):
    with UI.HBox():
        UI.Label('Font')
        UI.Label('Noto Sans CJK TC')


def prepare_template(template):
    for obj in template['objects']:
        if obj['type'] == 'text':
            obj['font'] = ''
    return template


def save_document(template, path, project_dir):
    Path(path).write_bytes(dumps(template))
    return 'Label ready to download, including image bytes.'


def run_background(editor, work, done):
    done(None, RuntimeError('Printing is available in the desktop app.'))


def save_pngs(files):
    from pyodide.ffi import run_sync, to_js
    from _labelate_bridge import save_pngs as save
    return run_sync(save(to_js(files)))
