from io import BytesIO
from pathlib import Path

from PIL import Image
import PUI.PySide6 as UI
from labelate.app import Labelate
from labelate import platform


def editor():
    app = Labelate()
    app.notify = lambda: None
    app.add('text')
    app.current()['content'] = '{SN}'
    app.template['variables']['SN'] = 'single'
    return app


def test_export_single_and_copies(tmp_path, monkeypatch):
    app = editor()
    dialogs = []
    def save(**kwargs):
        dialogs.append('file')
        return str(tmp_path / 'single.png')
    def folder(**kwargs):
        dialogs.append('folder')
        return str(tmp_path)
    monkeypatch.setattr(UI, 'SaveFile', save)
    monkeypatch.setattr(UI, 'OpenDirectory', folder)
    app.request_print()
    assert dialogs == ['file']
    assert Image.open(tmp_path / 'single.png').format == 'PNG'
    app.state.copies = '2'
    app.request_print()
    assert dialogs == ['file', 'folder']
    assert (tmp_path / 'label-0001.png').read_bytes() == (tmp_path / 'label-0002.png').read_bytes()


def test_export_data_and_cancel_replace(tmp_path, monkeypatch):
    app = editor()
    app.state.active_tab = 'Data'
    app.template['data_rows'].extend([app.make_data_row({'SN':'one'}), app.make_data_row({'SN':'two'})])
    monkeypatch.setattr(UI, 'OpenDirectory', lambda **kwargs: str(tmp_path))
    app.request_print()
    first = (tmp_path / 'label-0001.png').read_bytes()
    second = (tmp_path / 'label-0002.png').read_bytes()
    assert first != second
    monkeypatch.setattr(UI, 'Confirm', lambda *args, **kwargs: False)
    assert platform.save_pngs([('label-0001.png', b'replacement')]) is None
    assert (tmp_path / 'label-0001.png').read_bytes() == first
