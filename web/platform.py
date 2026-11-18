"""Build-time replacement for desktop integrations in the Pyodide archive."""
from pathlib import Path
import PUI.pyodide as UI
from .model import dumps
from .renderer import BUNDLED_FONTS, DEFAULT_FAMILY, bundled_family, bundled_reference

PRINTING = False
DESKTOP_DOWNLOAD = 'https://github.com/buganini/labelate/releases'


def attach(editor):
    pass


def modified(value):
    from _labelate_bridge import modified as publish
    publish(value)


def font_family(obj):
    return bundled_family(obj['font']) or DEFAULT_FAMILY


def font_controls(editor, obj, change):
    inputs = editor.object_inputs[obj['id']]

    def select_family(event):
        with editor.state:
            obj['font_index'] = 0
            change('font', bundled_reference(inputs['font_family']))

    with UI.HBox():
        UI.Label('Font')
        UI.FontComboBox(inputs('font_family'), fonts=list(BUNDLED_FONTS)).id('font-family').change(select_family)


def prepare_template(template):
    # Desktop font files do not exist in the browser; keep only bundled fonts.
    for obj in template['objects']:
        if obj['type'] == 'text':
            obj['font'] = bundled_reference(bundled_family(obj.get('font')) or DEFAULT_FAMILY)
            obj['font_index'] = 0
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
