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
