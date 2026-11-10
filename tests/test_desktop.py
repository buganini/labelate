import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import PUI.PySide6 as UI
from PIL import Image
from labelate.app import Labelate
from labelate.model import loads


def nodes(root):
    yield root
    for child in root.children:
        yield from nodes(child)


def test_desktop_font_and_relative_save(tmp_path, monkeypatch, capsys):
    app = Labelate()
    app.sync()
    def flush():
        for _ in range(3):
            app.ui.processEvents()
    flush()
    app.add('text')
    flush()
    font_button = next(n for n in nodes(app) if isinstance(n, UI.Button) and n.text == 'Choose font…')
    monkeypatch.setattr(UI, 'OpenFile', lambda **kwargs: '/custom/font.ttf')
    font_button.ui.click()
    flush()
    assert app.current()['font'] == '/custom/font.ttf'
    # A template save does not require the selected font to exist on this machine.
    target = tmp_path / 'label.lbl'
    monkeypatch.setattr(UI, 'SaveFile', lambda **kwargs: str(target))
    assert app.save()
    saved = loads(target.read_bytes())
    assert not Path(saved['objects'][0]['font']).is_absolute()
    app.load_path(target)
    assert app.template['objects'][0]['font'] == '/custom/font.ttf'
    asset = tmp_path / 'image.png'
    Image.new('RGB', (8,8), 'red').save(asset)
    app.add('image')
    monkeypatch.setattr(UI, 'OpenFile', lambda **kwargs: str(asset))
    app.browse_image()
    assert app.save()
    assert loads(target.read_bytes())['objects'][-1]['data'] == asset.read_bytes()
    app.modified = False
    app.drafts.clear()
    next(n for n in nodes(app) if isinstance(n, UI.Window)).ui.close()
    flush()
    output = capsys.readouterr()
    assert 'Traceback' not in output.out + output.err
