import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/third_party_licenses.py'
spec = importlib.util.spec_from_file_location('third_party_licenses', SCRIPT)
licenses = importlib.util.module_from_spec(spec)
spec.loader.exec_module(licenses)


def entry(license, files=()):
    return {'name': 'pkg', 'version': '1.0', 'license': license, 'homepage': '', 'files': list(files)}


def test_apache_header_gets_full_text():
    text = licenses.render([entry('Apache-2.0', [('COPYING', 'Licensed under the Apache License, Version 2.0')])])
    assert 'Apache-2.0 full text' in text
    assert licenses.FULL_TEXT_MARKERS['Apache-2.0'][0] in text


def test_lgpl_without_files_gets_lgpl_and_gpl():
    text = licenses.render([entry('LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only')])
    assert 'LGPL-3.0 full text' in text and 'GPL-3.0 full text' in text
    assert 'ships no license file' not in text


def test_libusb_lgpl21_gets_its_own_full_text():
    text = licenses.render([entry('LGPL-2.1-or-later')])
    assert 'LGPL-2.1 full text' in text and 'Version 2.1, February 1999' in text
    # An LGPL-3.0 file does not count as the LGPL-2.1 text.
    lgpl3 = (licenses.STANDARD_TEXTS / 'LGPL-3.0.txt').read_text()
    assert 'LGPL-2.1 full text' in licenses.render([entry('LGPL-2.1-or-later', [('COPYING', lgpl3)])])


def test_mit_with_file_is_embedded_verbatim():
    text = licenses.render([entry('MIT', [('LICENSE', 'MIT License\nCopyright X')])])
    assert 'Copyright X' in text and 'full text' not in text


def test_installed_closure_covers_runtime_dependencies():
    pytest.importorskip('packaging')
    try:
        names = {e['name'].lower().replace('_', '-') for e in licenses.installed_closure('labelate')}
    except Exception:
        pytest.skip('labelate is not installed')
    assert {'pillow', 'qrcode', 'python-barcode', 'msgpack', 'openpyxl', 'et-xmlfile', 'pyside6'} <= names
