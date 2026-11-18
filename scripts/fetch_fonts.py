"""Download the bundled fonts into labelate/fonts/ (ignored by git) and verify them.

Both the desktop package and the browser archive ship these files. Source checkouts
can run this once; without it the renderer falls back to installed system fonts.
"""
import hashlib
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / 'labelate/fonts'
CJK_BASE = 'https://raw.githubusercontent.com/notofonts/noto-cjk/Sans2.004/'
MONO_COMMIT = '15f23a0fd72c87285f50e890af8cf64d82d588a3'  # notofonts.github.io
MONO_BASE = f'https://raw.githubusercontent.com/notofonts/notofonts.github.io/{MONO_COMMIT}/fonts/NotoSansMono/hinted/ttf/'
MONO_LICENSE = 'https://raw.githubusercontent.com/notofonts/latin-greek-cyrillic/NotoSansMono-v2.014/OFL.txt'

FILES = (
    ('NotoSansCJKtc-Regular.otf', CJK_BASE + 'Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf',
     'dce08bd4fd91aa8aa76ed8fea4b694c2dfb8550f67871e326843212ddbeb88b4'),
    ('OFL.txt', CJK_BASE + 'LICENSE', '6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2'),
    ('NotoSansMono-Regular.ttf', MONO_BASE + 'NotoSansMono-Regular.ttf',
     '65b5e2b2c4a1fba9ae8be1f026cb35b03dcb8886d9b2a4147054fde12f7e767d'),
    ('NotoSansMono-OFL.txt', MONO_LICENSE, 'cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a'),
)

NOTICES = (
    {'name': 'Noto Sans CJK TC Regular', 'version': '2.004', 'license': 'OFL-1.1',
     'homepage': 'https://github.com/notofonts/noto-cjk', 'license_file': 'OFL.txt'},
    {'name': 'Noto Sans Mono Regular', 'version': f'notofonts.github.io@{MONO_COMMIT}', 'license': 'OFL-1.1',
     'homepage': 'https://github.com/notofonts/latin-greek-cyrillic', 'license_file': 'NotoSansMono-OFL.txt'},
)


def fetch(directory=FONT_DIR):
    """Return the verified font and license paths, downloading missing ones."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, url, checksum in FILES:
        path = directory / name
        if not path.exists():
            with urlopen(url, timeout=120) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != checksum:
                raise ValueError(f'Checksum mismatch: {name}')
            path.write_bytes(data)
        if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise ValueError(f'Font checksum mismatch: {path}; delete it and retry')
        paths.append(path)
    return paths


def notices(directory=FONT_DIR):
    """License entries for scripts/third_party_licenses.render."""
    return [{key: value for key, value in entry.items() if key != 'license_file'} |
            {'files': [('LICENSE', (directory / entry['license_file']).read_text(encoding='utf-8'))]}
            for entry in NOTICES]


if __name__ == '__main__':
    for path in fetch():
        print(path.relative_to(ROOT))
