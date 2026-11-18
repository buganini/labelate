"""MessagePack template files; images are already stored as raw bytes."""
from pathlib import Path
from .model import loads
from .renderer import bundled_family


def open_document(path):
    path = Path(path)
    if path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError('Template exceeds 128 MiB')
    template = loads(path.read_bytes())
    for obj in template['objects']:
        if obj['type'] == 'text' and obj.get('font') and not bundled_family(obj['font']):
            obj['font'] = str((path.resolve().parent / Path(obj['font']).expanduser()).resolve())
    return template, path.resolve().parent
