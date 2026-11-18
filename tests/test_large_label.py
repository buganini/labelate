import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PUI._rgba import RGBAImage

from labelate.app import Labelate


def test_large_labels_keep_a_paintable_preview():
    # A 200 mm square at 300 DPI is 2362 px wide; PUI's loadRGBA rejects more than
    # 1048576 px, which used to break every repaint of the canvas.
    app = Labelate()
    for width, height in ((200, 200), (530, 530), (2000, 5)):
        app.template['canvas'].update(width_mm=width, height_mm=height, dpi=300)
        app.refresh_preview()
        preview = app.preview
        assert preview.width * preview.height <= Labelate.PREVIEW_PIXELS
        assert Labelate.preview_paintable(preview)
        RGBAImage(preview.width, preview.height, preview.tobytes())
        assert abs(preview.width / preview.height - width / height) < .05 * width / height + 1 / preview.height


def test_paint_skips_an_unpaintable_preview():
    from PIL import Image
    app = Labelate()
    app.preview = Image.new('RGBA', (2048, 2048), 'white')
    assert not Labelate.preview_paintable(app.preview)
    calls = []

    class Canvas:
        width, height = 800, 600
        def drawRect(self, *args, **kwargs): calls.append('rect')
        def loadRGBA(self, *args): raise AssertionError('loadRGBA must not be called')
        def drawImage(self, *args): calls.append('image')
    app.paint(Canvas())
    assert calls == ['rect']


def nodes(root):
    yield root
    for child in root.children:
        yield from nodes(child)


def test_rejected_size_shows_a_red_error_after_the_file_buttons():
    from PySide6 import QtCore, QtWidgets
    from PUI.dom import recur_delete
    app = Labelate()
    if QtWidgets.QApplication.instance():
        app.ui = QtWidgets.QApplication.instance()
    try:
        check_error_label(app)
    finally:
        qtapp = QtWidgets.QApplication.instance()
        recur_delete(app, app, True)
        if qtapp:
            qtapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)


def check_error_label(app):
    app.sync()
    flush = lambda: [app.ui.processEvents() for _ in range(3)]
    flush()
    assert not any(n._id == 'error' for n in nodes(app))
    # 2000 x 2000 mm at 300 DPI is far beyond the 40 million pixel canvas limit.
    app.set_canvas('width_mm', 2000)
    app.set_canvas('height_mm', 2000)
    flush()
    assert app.template['canvas']['height_mm'] != 2000
    assert 'million pixels' in app.error
    toolbar = next(n for n in nodes(app) if n._id == 'toolbar')
    labels = [n for n in toolbar.children if n._id == 'error']
    assert labels and labels[0].text == app.error and labels[0].style_color == 0xdc2626
    ids = [n._id for n in toolbar.children]
    assert ids.index('error') > ids.index('Save .lbl')
    app.set_canvas('height_mm', 50)
    flush()
    assert app.error == ''
    assert not any(n._id == 'error' for n in nodes(app))
