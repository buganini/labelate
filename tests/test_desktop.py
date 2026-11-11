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
    from labelate.system_fonts import system_fonts
    from labelate.renderer import load_font
    picker = next(n for n in nodes(app) if n._id == 'font-family')
    family = next(name for name in system_fonts() if picker.ui.findText(name) >= 0)
    picker.choose(picker.ui.findText(family))
    flush()
    obj = app.current()
    assert load_font(obj['font'], 12, obj['font_index']).getname()[0] == family
    assert app.object_inputs[obj['id']]['font_family'] == family
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
    from labelate import printing
    import time
    device = printing.Printer('TSC', 'test', 'pyusb', 'Test printer')
    monkeypatch.setattr(printing, 'discover', lambda brand: ([device], []))
    app.set_brand('TSC')
    deadline = time.monotonic() + 3
    while app.busy and time.monotonic() < deadline:
        flush()
        time.sleep(.005)
    assert not app.busy and app.selected_printer() == device
    monkeypatch.setattr(printing, 'models', lambda brand: ['TTP-342'])
    app.configure_printer(False)
    flush()
    assert app.settings_open
    app.set_print_setting('model', 'TTP-342')
    app.apply_print_settings()
    app.add('text')
    app.current()['content'] = 'Order {order}'
    app.state('active_tab').value = 'Data'
    app.add_data_row()
    app.template['data_rows'][0]('order').value = 'A001'
    flush()
    assert any(isinstance(n, UI.Button) and n.text == 'Print All' for n in nodes(app))
    assert not any(isinstance(n, UI.Button) and n.text == 'Print Single Label' for n in nodes(app))
    sent = []
    def print_labels(printer, config, data, rows, copies, progress):
        sent.append((loads(data), rows, copies))
        progress('Printing…')
        return 'Printed.'
    monkeypatch.setattr(printing, 'print_labels', print_labels)
    app.request_print()
    deadline = time.monotonic() + 3
    while app.busy and time.monotonic() < deadline:
        flush()
        time.sleep(.005)
    assert not app.busy and app.print_message == 'Printed.'
    assert sent[-1][1:] == ([{'SN':'', 'order':'A001'}], 1)
    app.state('active_tab').value = 'Label'
    app.state('copies').value = '2'
    app.current()['content'] = 'Updated {order}'
    app.request_print()
    app.request_print()  # Busy guard prevents double submission.
    deadline = time.monotonic() + 3
    while app.busy and time.monotonic() < deadline:
        flush()
        time.sleep(.005)
    assert len(sent) == 2 and sent[-1][2] == 2
    assert sent[-1][0]['objects'][-1]['content'] == 'Updated {order}'
    app.state('copies').value = '0'
    app.request_print()
    assert 'positive integer' in app.print_message and len(sent) == 2
    app.modified = False
    next(n for n in nodes(app) if isinstance(n, UI.Window)).ui.close()
    flush()
    output = capsys.readouterr()
    assert 'Traceback' not in output.out + output.err
