"""Build a pinned browser-only Python archive; run npm run build afterwards."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from urllib.request import urlopen
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUI_COMMIT = 'eac5c6397d502c7cce077bd64813c4c615755305'  # QPUIQ 1.10 release
FONT_BASE = 'https://raw.githubusercontent.com/notofonts/noto-cjk/Sans2.004/'
PYODIDE_VERSION = '314.0.7'
WHEELS = ('qrcode==8.2', 'python-barcode==0.16.1', 'msgpack==1.1.2', 'openpyxl==3.1.5', 'et-xmlfile==2.0.0')
CDN_NOTE = (
    f'Loaded at runtime from cdn.jsdelivr.net (not redistributed in this build): Pyodide {PYODIDE_VERSION}',
    '(MPL-2.0, https://github.com/pyodide/pyodide) and its Pillow package (MIT-CMU,',
    'https://github.com/python-pillow/Pillow).',
)


def browser_source(path):
    if path.name == 'platform.py':
        return (ROOT / 'web/platform.py').read_text(encoding='utf-8')
    source = path.read_text(encoding='utf-8')
    if path.name == 'app.py':
        original = 'import PUI.PySide6 as UI'
        if source.count(original) != 1:
            raise ValueError('Expected one direct PySide6 import in app.py')
        source = source.replace(original, 'import PUI.pyodide as UI')
    return source


def font_assets():
    cache = ROOT / '.build/fonts'
    cache.mkdir(parents=True, exist_ok=True)
    for name, remote, checksum in (
        ('NotoSansCJKtc-Regular.otf', 'Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf',
         'dce08bd4fd91aa8aa76ed8fea4b694c2dfb8550f67871e326843212ddbeb88b4'),
        ('OFL.txt', 'LICENSE', '6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2'),
    ):
        path = cache / name
        if not path.exists():
            with urlopen(FONT_BASE + remote, timeout=120) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != checksum:
                raise ValueError(f'Checksum mismatch: {name}')
            path.write_bytes(data)
        if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise ValueError(f'Cached font checksum mismatch: {name}')
        yield path


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from third_party_licenses import from_wheel, render

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pui-source', type=Path, default=ROOT / '.build/PUI')
    args = parser.parse_args()
    source = args.pui_source.resolve()
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != PUI_COMMIT:
        parser.error(f'PUI source must be pinned to {PUI_COMMIT} (QPUIQ 1.10)')
    subprocess.run(['git', '-C', str(source), 'diff', '--exit-code', 'HEAD', '--', 'PUI', 'browser-client'], check=True)
    output = ROOT / 'dist/pyodide'
    output.mkdir(parents=True, exist_ok=True)
    fonts = list(font_assets())
    wheels = ROOT / '.build/wheels'
    wheels.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, '-m', 'pip', 'download', '--no-deps', '--only-binary=:all:',
                    '--dest', str(wheels), *WHEELS], check=True)
    wheel_files = [next(wheels.glob(f"{name.replace('-', '_')}-{version}-*.whl"))
                   for name, version in (spec.split('==') for spec in WHEELS)]
    notices = render([
        {'name': 'PUI (QPUIQ)', 'version': PUI_COMMIT, 'license': 'MIT', 'homepage': 'https://github.com/buganini/PUI',
         'files': [('LICENSE.txt', (source / 'LICENSE.txt').read_text(encoding='utf-8'))]},
        {'name': 'Noto Sans CJK TC Regular', 'version': '2.004', 'license': 'OFL-1.1',
         'homepage': 'https://github.com/notofonts/noto-cjk',
         'files': [('LICENSE', (ROOT / '.build/fonts/OFL.txt').read_text(encoding='utf-8'))]},
        *map(from_wheel, wheel_files),
    ], notes=CDN_NOTE)
    with zipfile.ZipFile(output / 'app.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for directory in ('PUI', 'PUI/_browser', 'PUI/pyodide'):
            for path in sorted((source / directory).glob('*.py')):
                archive.write(path, path.relative_to(source))
        for path in sorted((ROOT / 'labelate').glob('*.py')):
            archive.writestr(str(path.relative_to(ROOT)), browser_source(path))
        archive.write(ROOT / 'labelate/icon.svg', 'labelate/icon.svg')
        archive.write(ROOT / 'examples/product.lbl', 'examples/product.lbl')
        archive.write(ROOT / 'LICENSE', 'LICENSE')
        archive.write(source / 'LICENSE.txt', 'licenses/PUI-MIT.txt')
        archive.writestr('THIRD_PARTY_LICENSES.txt', notices)
        for font in fonts:
            archive.write(font, 'labelate/fonts/' + font.name)
        for wheel in wheel_files:
            with zipfile.ZipFile(wheel) as package:
                for name in package.namelist():
                    if not name.endswith(('/', '.so', '.pyd', '.dll')):
                        archive.writestr(name, package.read(name))
    client = ROOT / '.build/pui-client'
    if client.exists():
        shutil.rmtree(client)
    for folder in ('shared', 'pyodide'):
        shutil.copytree(source / 'browser-client' / folder, client / folder)
    for name in ('index.html', 'host.js'):
        shutil.copyfile(ROOT / 'web' / name, output / name)
    shutil.copyfile(ROOT / 'LICENSE', output / 'LICENSE')
    shutil.copyfile(source / 'LICENSE.txt', output / 'PUI-LICENSE.txt')
    shutil.copyfile(ROOT / '.build/fonts/OFL.txt', output / 'FONT-LICENSE.txt')
    (output / 'THIRD_PARTY_LICENSES.txt').write_text(notices, encoding='utf-8')
    (output / '.nojekyll').touch()
    (output / 'build-info.json').write_text(json.dumps({
        'qpuiq': '1.10', 'pui_commit': PUI_COMMIT, 'pyodide': PYODIDE_VERSION,
        'qrcode': '8.2', 'python-barcode': '0.16.1', 'license': 'MIT',
        'font': 'Noto Sans CJK TC Regular 2.004', 'msgpack': '1.1.2', 'openpyxl': '3.1.5', 'et-xmlfile': '2.0.0'
    }, indent=2) + '\n')
    print(f'Prepared {output}')


if __name__ == '__main__':
    main()
