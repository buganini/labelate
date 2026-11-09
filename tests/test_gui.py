"""Browser backend model/lifecycle tests; real DOM interactions live in web.spec.mjs."""
import asyncio
import sys
from types import SimpleNamespace

import PUI.pyodide as UI
from PUI.pyodide.runtime import Runtime
from PIL import Image

from labelate.app import Labelate
from labelate.model import loads


def nodes(root):
    yield root
    for child in root.children:
        yield from nodes(child)


def test_browser_app(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, '_labelate_bridge', SimpleNamespace(modified=lambda value: None))
    monkeypatch.setattr(UI, 'Confirm', lambda *args, **kwargs: False)
    async def scenario():
        runtime = Runtime(asyncio.get_running_loop(), lambda m: None, epoch='test', build='test')
        app = Labelate()
        app.start()
        async def settle():
            for _ in range(6):
                await asyncio.sleep(0)
        try:
            await settle()
            assert any(isinstance(n, UI.Canvas) for n in nodes(app))
            app.add('text')
            await settle()
            oid = app.selected
            field = next(n for n in nodes(app) if isinstance(n, UI.TextEdit) and not n.readonly)
            field.edit_model.value = 'Pending {customer}'
            assert app.current()['content'] != 'Pending {customer}'
            download = tmp_path / 'download-without-extension'
            monkeypatch.setattr(UI, 'SaveFile', lambda **kwargs: str(download))
            assert app.save()
            assert loads(download.read_text())['objects'][0]['content'] == 'Pending {customer}'
            app.set_variable('customer', 'Ada')
            app.set_unit('cm')
            app.set_object('font_style', 'italic')
            app.set_object('font_weight', 'bold')
            await settle()
            assert app.template['canvas']['width_mm'] == 100
            field = next(n for n in nodes(app) if isinstance(n, UI.TextEdit) and not n.readonly)
            old_binding = field.model
            app.set_variable('customer', 'Bob')
            await settle()
            field = next(n for n in nodes(app) if isinstance(n, UI.TextEdit) and not n.readonly)
            assert field.model is old_binding
            assert app.object_by_id(oid)['font_weight'] == 'bold'
            app.viewport = (0, 0, 10)
            app.pointer_down(SimpleNamespace(button=1, x=60, y=60))
            app.pointer_move(SimpleNamespace(x=110, y=130))
            app.pointer_up(SimpleNamespace())
            assert app.current()['x_mm'] == 10
            assert app.current()['y_mm'] == 12
            app.delete()
            assert app.template['variables'] == {}
            asset = tmp_path / 'red.png'
            Image.new('RGB', (20, 20), 'red').save(asset)
            app.add('image')
            monkeypatch.setattr(UI, 'OpenFile', lambda **kwargs: str(asset))
            app.browse_image()
            await settle()
            assert all(n.readonly for n in nodes(app) if isinstance(n, UI.TextEdit))
            package = tmp_path / 'label.zip'
            monkeypatch.setattr(UI, 'SaveFile', lambda **kwargs: str(package))
            assert app.save_package()
            app.load_path(package)
            assert app.preview.getbbox()
            app.add('rect')
            app.set_object('radius_mm', 2)
            await settle()
            runtime.snapshot()  # Binding values and serialized canvas props must be valid.
            assert not runtime.task.done()
        finally:
            app.quit()
            await asyncio.wait_for(runtime.task, 2)
    asyncio.run(scenario())
