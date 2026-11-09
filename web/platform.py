"""Build-time replacement for desktop integrations in the Pyodide archive."""
from pathlib import Path
import PUI.pyodide as UI
from .model import dumps
from .template_io import portable_document


def attach(editor):
    pass


def modified(value):
    from _labelate_bridge import modified as publish
    publish(value)


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
    document, assets = portable_document(template, project_dir)
    # Preserve the path allocated by PUI's download registry exactly.
    Path(path).write_text(dumps(document), encoding='utf-8')
    return ('JSON ready to download. Use Save ZIP to include referenced images.'
            if assets else 'JSON ready to download.')
