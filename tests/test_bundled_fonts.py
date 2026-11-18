from pathlib import Path
import tomllib

import pytest

from labelate import renderer
from labelate.model import dumps, loads, new_template
from labelate.renderer import BUNDLED_FONTS, DEFAULT_FAMILY, bundled_family, bundled_reference, load_font
from labelate.template_io import open_document
from scripts import fetch_fonts

ROOT = Path(__file__).resolve().parents[1]


def test_bundled_references():
    assert DEFAULT_FAMILY == 'Noto Sans CJK TC'
    assert bundled_reference(DEFAULT_FAMILY) == ''
    assert bundled_reference('Noto Sans Mono') == 'bundled:Noto Sans Mono'
    assert bundled_family('bundled:Noto Sans Mono') == 'Noto Sans Mono'
    assert bundled_family('bundled:Comic Sans') is None
    assert bundled_family('/fonts/mono.ttf') is None


def test_fetch_script_covers_every_bundled_font():
    names = {name for name, _, _ in fetch_fonts.FILES}
    assert set(BUNDLED_FONTS.values()) <= names
    package_data = tomllib.loads((ROOT / 'pyproject.toml').read_text())['tool']['setuptools']['package-data']
    assert 'fonts/*' in package_data['labelate']
    assert fetch_fonts.FONT_DIR == Path(renderer.__file__).with_name('fonts')


@pytest.mark.skipif(not all((renderer.FONT_DIR / name).is_file() for name in BUNDLED_FONTS.values()),
                    reason='run scripts/fetch_fonts.py first')
def test_bundled_fonts_load_from_package():
    assert load_font('', 12).getname()[0] == 'Noto Sans CJK TC'
    font = load_font('bundled:Noto Sans Mono', 12)
    assert font.getname()[0] == 'Noto Sans Mono'
    assert font.getlength('i') == font.getlength('W')


def test_missing_bundled_font_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(renderer, 'FONT_DIR', tmp_path)
    monkeypatch.setattr(renderer, 'DEFAULT_FONT', tmp_path / 'missing.otf')
    assert load_font('bundled:Noto Sans Mono', 12) is not None


def test_bundled_reference_survives_open_and_save(tmp_path):
    template = new_template()
    from labelate.model import new_object
    text = new_object('text')
    text['font'] = 'bundled:Noto Sans Mono'
    template['objects'] = [text]
    path = tmp_path / 'mono.lbl'
    path.write_bytes(dumps(template))
    opened, _ = open_document(path)
    assert opened['objects'][0]['font'] == 'bundled:Noto Sans Mono'
    from labelate import platform
    target = tmp_path / 'saved' / 'mono.lbl'
    target.parent.mkdir()
    platform.save_document(opened, target, tmp_path)
    assert loads(target.read_bytes())['objects'][0]['font'] == 'bundled:Noto Sans Mono'
