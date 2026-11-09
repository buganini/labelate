"""Build a pinned browser-only Python archive; run npm run build afterwards."""
import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUI_COMMIT = '091c24f44916c5bf5796f0bb922380d3cddba1e4'  # upstream tag 1.8


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pui-source', type=Path, default=ROOT / '.build/PUI')
    args = parser.parse_args()
    source = args.pui_source.resolve()
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != PUI_COMMIT:
        parser.error(f'PUI source must be pinned to {PUI_COMMIT} (QPUIQ 1.8)')
    subprocess.run(['git', '-C', str(source), 'diff', '--exit-code', 'HEAD', '--', 'PUI', 'browser-client'], check=True)
    output = ROOT / 'dist/pyodide'
    output.mkdir(parents=True, exist_ok=True)
    wheels = ROOT / '.build/wheels'
    wheels.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, '-m', 'pip', 'download', '--no-deps', '--only-binary=:all:',
                    '--dest', str(wheels), 'qrcode==8.2', 'python-barcode==0.16.1'], check=True)
    with zipfile.ZipFile(output / 'app.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for directory in ('PUI', 'PUI/_browser', 'PUI/pyodide'):
            for path in sorted((source / directory).glob('*.py')):
                archive.write(path, path.relative_to(source))
        for path in sorted((ROOT / 'labelate').glob('*.py')):
            archive.write(path, path.relative_to(ROOT))
        archive.write(ROOT / 'examples/product.json', 'examples/product.json')
        archive.write(ROOT / 'LICENSE', 'LICENSE')
        archive.write(source / 'LICENSE.txt', 'licenses/PUI-MIT.txt')
        for pattern in ('qrcode-8.2-*.whl', 'python_barcode-0.16.1-*.whl'):
            wheel = next(wheels.glob(pattern))
            with zipfile.ZipFile(wheel) as package:
                for name in package.namelist():
                    if not name.endswith('/'):
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
    (output / '.nojekyll').touch()
    (output / 'build-info.json').write_text(json.dumps({
        'qpuiq': '1.8', 'pui_commit': PUI_COMMIT, 'pyodide': '314.0.7',
        'qrcode': '8.2', 'python-barcode': '0.16.1', 'license': 'GPL-3.0-only'
    }, indent=2) + '\n')
    print(f'Prepared {output}')


if __name__ == '__main__':
    main()
