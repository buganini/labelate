"""Portable JSON/ZIP templates with file references, never embedded image data."""
import copy
import hashlib
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .model import dumps, loads, VARIABLE

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024


def open_document(path):
    path = Path(path)
    if path.suffix.lower() == '.zip':
        folder = Path(tempfile.mkdtemp(prefix='labelate-'))
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > 1000 or sum(m.file_size for m in members) > MAX_ARCHIVE_BYTES:
                raise ValueError('Template ZIP exceeds the import limit')
            for member in members:
                name = PurePosixPath(member.filename)
                if name.is_absolute() or '..' in name.parts or '\\' in member.filename or ':' in member.filename:
                    raise ValueError('Unsafe path in template ZIP')
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Symbolic links are not supported in template ZIPs')
            archive.extractall(folder)
        candidates = sorted(folder.rglob('*.json'))
        preferred = folder / 'label.json'
        if preferred.is_file():
            path = preferred
        elif len(candidates) == 1:
            path = candidates[0]
        else:
            raise ValueError('Template ZIP must contain label.json or exactly one JSON template')
    template = loads(path.read_text(encoding='utf-8'))
    for obj in template['objects']:
        for field in asset_fields(obj):
            value = obj.get(field, '')
            if value:
                obj[field] = str((path.resolve().parent / Path(value).expanduser()).resolve())
    return template, path.resolve().parent


def asset_fields(obj):
    return ('content',) if obj['type'] == 'image' else ('font',) if obj['type'] == 'text' else ()


def portable_document(template, base_dir=None):
    document, assets = copy.deepcopy(template), {}
    for obj in document['objects']:
        for field in asset_fields(obj):
            value = obj.get(field, '')
            if not value:
                continue
            source = Path(value).expanduser().resolve()
            relative = None
            if base_dir:
                try:
                    relative = source.relative_to(Path(base_dir).resolve()).as_posix()
                except ValueError:
                    pass
            if relative is None:
                # Stable names do not expose browser temporary upload directories.
                digest = hashlib.sha256(str(source).encode()).hexdigest()[:12]
                relative = f'assets/{digest}-{source.name}'
            obj[field] = relative
            assets[relative] = source
    return document, assets


def write_package(path, template, base_dir=None):
    document, assets = portable_document(template, base_dir)
    for relative, source in assets.items():
        if VARIABLE.search(str(source)):
            raise ValueError('ZIP export requires concrete image/font paths; choose a file first')
        if not source.is_file():
            raise ValueError(f'Missing asset: {source.name}')
    if sum(p.stat().st_size for p in assets.values()) > MAX_ARCHIVE_BYTES:
        raise ValueError('Template assets exceed the ZIP export limit')
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('label.json', dumps(document))
        for relative, source in assets.items():
            archive.write(source, relative)
