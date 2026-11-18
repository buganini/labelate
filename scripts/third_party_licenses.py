"""Collect third-party license texts into a single THIRD_PARTY_LICENSES.txt."""
import email
import importlib.metadata as metadata
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STANDARD_TEXTS = ROOT / 'resources/licenses'
# SPDX ids whose full text must accompany the notice when a package ships none
# (or only a short header pointing at the URL, as msgpack does for Apache-2.0).
STANDARD_IDS = {'Apache-2.0': 'Apache-2.0.txt', 'LGPL-2.1': 'LGPL-2.1.txt', 'LGPL-3.0': 'LGPL-3.0.txt',
                'GPL-3.0': 'GPL-3.0.txt'}
# A shipped file containing all of these texts already carries the full license.
FULL_TEXT_MARKERS = {'Apache-2.0': ('TERMS AND CONDITIONS FOR USE, REPRODUCTION',),
                     'LGPL-2.1': ('GNU LESSER GENERAL PUBLIC LICENSE', 'Version 2.1, February 1999'),
                     'LGPL-3.0': ('GNU LESSER GENERAL PUBLIC LICENSE', 'Version 3, 29 June 2007'),
                     'GPL-3.0': ('GNU GENERAL PUBLIC LICENSE',)}
LICENSE_FILE = re.compile(r'(?i)^(licen[cs]e|copying|notice)')


def _license_expression(meta):
    expression = meta.get('License-Expression')
    if expression:
        return expression
    license = (meta.get('License') or '').strip()
    if license and '\n' not in license and len(license) < 80:
        return license
    classifiers = [c.split('::')[-1].strip() for c in meta.get_all('Classifier') or [] if c.startswith('License ::')]
    return '; '.join(classifiers) or 'UNKNOWN'


def _homepage(meta):
    if meta.get('Home-page'):
        return meta['Home-page']
    for url in meta.get_all('Project-URL') or []:
        label, _, link = url.partition(',')
        if label.strip().lower() in ('homepage', 'home', 'source', 'repository'):
            return link.strip()
    return ''


def _entry(meta, files):
    return {'name': meta['Name'], 'version': meta['Version'], 'license': _license_expression(meta),
            'homepage': _homepage(meta), 'files': files}


def _is_license_file(name):
    return '.dist-info/' in name and LICENSE_FILE.match(name.rsplit('/', 1)[-1])


def from_wheel(path):
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        info = next(n for n in names if n.endswith('.dist-info/METADATA'))
        meta = email.message_from_bytes(wheel.read(info))
        files = [(n.split('.dist-info/', 1)[1], wheel.read(n).decode('utf-8', 'replace'))
                 for n in sorted(names) if _is_license_file(n)]
    return _entry(meta, files)


def from_distribution(dist):
    files = [(str(f).split('.dist-info/', 1)[1], f.locate().read_text(encoding='utf-8', errors='replace'))
             for f in sorted(dist.files or [], key=str) if _is_license_file(str(f))]
    return _entry(dist.metadata, files)


def installed_closure(root, extras=(), skip_extras=('dev',)):
    """Installed distributions required by `root`, following extras.

    Extras of `root` that are not listed but whose requirements are all installed
    (e.g. the optional printer drivers) are included too, because PyInstaller bundles them.
    """
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    def find(name):
        try:
            return metadata.distribution(name)
        except metadata.PackageNotFoundError:
            return None

    root_dist = find(root)
    wanted = set(extras)
    for extra in root_dist.metadata.get_all('Provides-Extra') or []:
        if extra in skip_extras:
            continue
        reqs = [Requirement(r) for r in root_dist.requires or []]
        reqs = [r for r in reqs if r.marker and r.marker.evaluate({'extra': extra})]
        if reqs and all(find(r.name) for r in reqs):
            wanted.add(extra)

    seen = {}
    pending = [(root, frozenset(wanted))]
    while pending:
        name, extras = pending.pop()
        dist = find(name)
        key = canonicalize_name(name)
        if dist is None or (key in seen and extras <= seen[key][1]):
            continue
        seen[key] = (dist, extras | (seen[key][1] if key in seen else frozenset()))
        for text in dist.requires or []:
            req = Requirement(text)
            if req.marker is None or any(req.marker.evaluate({'extra': e}) for e in ({''} | extras)):
                pending.append((req.name, frozenset(req.extras)))
    seen.pop(canonicalize_name(root), None)
    return [from_distribution(dist) for dist, _ in sorted(seen.values(), key=lambda v: v[0].metadata['Name'].lower())]


def render(entries, notes=()):
    rule = '=' * 78
    out = ['Labelate third-party licenses', '',
           'Labelate is distributed under the MIT License (see LICENSE). It includes or',
           'depends on the third-party components listed below.', '']
    out.extend(notes)
    out.append('')
    standard = set()
    for entry in entries:
        out += [rule, f"{entry['name']} {entry['version']}".strip(), f"License: {entry['license']}"]
        if entry['homepage']:
            out.append(f"Homepage: {entry['homepage']}")
        out.append(rule)
        for name, text in entry['files']:
            out += ['', f'--- {name} ---', '', text.rstrip(), '']
        license = entry['license'].replace('Apache Software License', 'Apache-2.0')
        needed = [i for i in STANDARD_IDS if i in license
                  and not any(all(marker in text for marker in FULL_TEXT_MARKERS[i]) for _, text in entry['files'])]
        standard.update(needed)
        if needed:
            out += ['', f"Full text of {', '.join(needed)}: see the end of this file.", '']
        elif not entry['files']:
            out += ['', 'This package ships no license file; see its homepage for the license text.', '']
    for spdx in sorted(standard):
        out += [rule, f'{spdx} full text', rule, '', (STANDARD_TEXTS / STANDARD_IDS[spdx]).read_text().rstrip(), '']
    return '\n'.join(out) + '\n'


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(render(installed_closure('labelate')), encoding='utf-8')
    print(f'Wrote {args.output}')
