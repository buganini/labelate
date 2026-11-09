import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PIL import Image
from PySide6 import QtCore as C, QtGui as G, QtTest
import PUI.PySide6 as UI
from labelate.app import Labelate
from labelate.model import loads


def nodes(root):
    yield root
    for child in root.children:
        yield from nodes(child)


def find(app, cls, key=None):
    return next(n for n in nodes(app) if isinstance(n, cls) and (key is None or n.key.endswith('#id=' + key)))


def flush(app):
    for _ in range(3):
        app.ui.processEvents()


def test_declarative_editor(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(UI, 'Confirm', lambda *args, **kwargs: False)
    app = Labelate()
    app.sync()
    flush(app)
    assert find(app, UI.Canvas)
    assert find(app, UI.ComboBox, 'unit')
    assert not any(isinstance(n, UI.Button) and n.text == 'Delete selected' for n in nodes(app))
    find(app, UI.Button, 'Text').ui.click()
    flush(app)
    first = app.current()
    content = find(app, UI.TextEdit, 'content-' + first['id'])
    content.ui.setFocus()
    content.ui.selectAll()
    content.ui.insertPlainText('Hello {customer}')
    content.ui.focusOutEvent(G.QFocusEvent(C.QEvent.Type.FocusOut))
    flush(app)
    assert first['content'] == 'Hello {customer}'
    app.set_variable('customer', 'Ada')
    flush(app)
    find(app, UI.ComboBox, 'unit').ui.setCurrentText('cm')
    flush(app)
    assert app.template['canvas']['unit'] == 'cm'
    assert app.template['canvas']['width_mm'] == 100
    width = find(app, UI.TextField, 'width_mm')
    # Both label and object width fields exist: use the one in dimensions-row.
    width = next(n for n in nodes(app) if isinstance(n, UI.TextField) and n.key.endswith('#id=width_mm') and n.model.value == '10')
    width.ui.setText('12')
    width.ui.editingFinished.emit()
    flush(app)
    assert app.template['canvas']['width_mm'] == 120
    find(app, UI.ComboBox, 'style').ui.setCurrentText('italic')
    find(app, UI.ComboBox, 'weight').ui.setCurrentText('bold')
    flush(app)
    assert first['font_style'] == 'italic'
    assert first['font_weight'] == 'bold'
    canvas = find(app, UI.Canvas).ui
    assert canvas.grab().toImage().pixelColor(0, 0).name() == '#000000'
    x, y, scale = app.viewport
    start = C.QPoint(round(x + 6*scale), round(y + 6*scale))
    end = start + C.QPoint(round(5*scale), round(7*scale))
    QtTest.QTest.mousePress(canvas, C.Qt.MouseButton.LeftButton, pos=start)
    QtTest.QTest.mouseMove(canvas, end)
    QtTest.QTest.mouseRelease(canvas, C.Qt.MouseButton.LeftButton, pos=end)
    flush(app)
    assert first['x_mm'] == pytest.approx(10, abs=.2)
    assert first['y_mm'] == pytest.approx(12, abs=.2)
    find(app, UI.Button, 'Delete selected').ui.click()
    flush(app)
    assert app.template['objects'] == []
    assert app.template['variables'] == {}
    asset = tmp_path / 'image.png'
    Image.new('RGB', (10, 10), 'red').save(asset)
    app.add('image')
    flush(app)
    assert find(app, UI.TextEdit, 'image-path').readonly
    assert not any(isinstance(n, UI.TextEdit) and not n.readonly for n in nodes(app))
    monkeypatch.setattr(UI, 'OpenFile', lambda **kwargs: str(asset))
    app.browse_image()
    folder = tmp_path / 'templates'
    folder.mkdir()
    app.path = folder / 'label.json'
    assert app.save()
    assert loads(app.path.read_text())['objects'][0]['content'] == '../image.png'
    assert not app.modified
    monkeypatch.setattr(UI, 'OpenFile', lambda **kwargs: str(folder / 'label.json'))
    app.open()
    assert app.template['objects'][0]['content'] == str(asset)
    monkeypatch.setattr(UI, 'SaveFile', lambda **kwargs: str(tmp_path / 'copy.json'))
    assert app.save(True)
    assert loads(app.path.read_text())['objects'][0]['content'] == 'image.png'
    # Saving while content is still focused must commit the draft.
    app.add('text')
    flush(app)
    text_id = app.selected
    field = find(app, UI.TextEdit, 'content-' + text_id).ui
    field.selectAll()
    field.insertPlainText('Pending {order}')
    assert app.save()
    assert loads(app.path.read_text())['objects'][-1]['content'] == 'Pending {order}'
    app.add('rect')
    app.set_object('radius_mm', 2)
    flush(app)
    assert find(app, UI.TextField, 'radius_mm')
    app.modified = False
    app.drafts.clear()
    find(app, UI.Window).ui.close()
    flush(app)
    output = capsys.readouterr()
    assert 'Traceback' not in output.err + output.out
    assert '<ERROR' not in output.err + output.out
