"""Browser backend model/lifecycle tests; real DOM interactions live in web.spec.mjs."""
import asyncio
import sys
from types import SimpleNamespace

import PUI.pyodide as UI
from PUI.pyodide.runtime import Runtime
from PIL import Image

from pathlib import Path
from types import ModuleType
from scripts.build_pyodide import browser_source
from labelate.model import loads, dumps
from PUI.state import StateList, StateDict, BaseBinding


def nodes(root):
    yield root
    for child in root.children:
        yield from nodes(child)


def test_browser_app(tmp_path, monkeypatch):
    # Exercise exactly the sources placed in the browser archive, in an isolated package.
    root = Path(__file__).resolve().parents[1] / 'labelate'
    package = ModuleType('labelate_web_test')
    package.__path__ = [str(root)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    for name in ('platform', 'app'):
        module = ModuleType(package.__name__ + '.' + name)
        module.__package__ = package.__name__
        module.__file__ = str(root / (name + '.py'))
        monkeypatch.setitem(sys.modules, module.__name__, module)
        exec(compile(browser_source(root / (name + '.py')), module.__file__, 'exec'), module.__dict__)
        setattr(package, name, module)
    Labelate = package.app.Labelate
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
            assert isinstance(app.state.objects, StateList)
            assert app.template['objects'] is app.state.objects
            assert isinstance(app.current(), StateDict)
            field = next(n for n in nodes(app) if isinstance(n, UI.TextEdit) and not n.readonly)
            field.edit_model.value = 'Pending {customer}'
            assert app.current()['content'] != 'Pending {customer}'
            download = tmp_path / 'download-without-extension'
            monkeypatch.setattr(UI, 'SaveFile', lambda **kwargs: str(download))
            assert app.save()
            assert loads(download.read_bytes())['objects'][0]['content'] == 'Pending {customer}'
            legacy = loads(download.read_bytes())
            legacy['objects'][0]['font'] = '/missing/custom.ttf'
            download.write_bytes(dumps(legacy))
            app.load_path(download)
            assert app.template['objects'][0]['font'] == ''
            app.select_object(oid)
            app.set_variable('customer', 'Ada')
            app.set_unit('cm')
            app.set_object('font_style', 'italic')
            app.set_object('font_weight', 'bold')
            await settle()
            assert app.template['canvas']['width_mm'] == 100
            field = next(n for n in nodes(app) if isinstance(n, UI.TextEdit) and not n.readonly)
            old_binding = field.model
            assert isinstance(old_binding, BaseBinding)
            assert old_binding.state is app.current()
            app.set_variable('customer', 'Bob')
            await settle()
            field = next(n for n in nodes(app) if isinstance(n, UI.TextEdit) and not n.readonly)
            assert field.model.state is old_binding.state and field.model.key == old_binding.key
            assert app.object_by_id(oid)['font_weight'] == 'bold'
            from labelate import render
            from PIL import Image
            original = render(dumps(app.snapshot()), {})
            for angle in (0, 90, 180, 270):
                start, end = (60, 60), (110, 130)
                app.set_object('x_mm', 5)
                app.set_object('y_mm', 5)
                app.set_rotation(str(angle))
                dimensions = original.size[::-1] if angle in (90, 270) else original.size
                expected = Image.new('RGBA', dimensions, 'white')
                expected.alpha_composite(original.convert('RGBA'))
                expected.thumbnail((1024, 1024), Image.Resampling.NEAREST)
                assert app.preview.size == expected.size
                assert app.preview.tobytes() == expected.tobytes()
                app.viewport = (0, 0, 10)
                app.pointer_down(SimpleNamespace(button=1, x=start[0], y=start[1]))
                assert app.selected == oid
                app.pointer_move(SimpleNamespace(x=end[0], y=end[1]))
                app.pointer_up(SimpleNamespace())
                assert app.current()['x_mm'] == 10
                assert app.current()['y_mm'] == 12
            obj = app.current()
            # Direct State writes update the form/preview; native numeric bindings retain fractions.
            app.modified = False
            obj('x_mm').value = 12.34567
            await settle()
            assert obj['x_mm'] == 12.34567
            assert app.object_inputs[oid]['x_mm'] == '1.235'  # Display unit is cm.
            assert app.modified
            app.object_inputs[oid]('x_mm').value = '2.75'
            assert obj['x_mm'] == 27.5
            app.object_inputs[oid]('x_mm').value = 'nan'
            assert obj['x_mm'] == 27.5
            assert app.object_inputs[oid]['x_mm'] == '2.75'
            before = app.preview.tobytes()
            width = obj['width_mm']
            obj('width_mm').value = 0
            assert obj['width_mm'] == width
            assert app.preview.tobytes() == before
            assert 'positive' in app.status
            obj('content').value = 'State {state_value}'
            assert app.template['variables'] == {'state_value': ''}
            assert app.drafts[oid] == 'State {state_value}'
            stale = obj('content')
            assert app.save()
            app.load_path(download)
            app.select_object(oid)
            assert app.object_inputs[oid]['x_mm'] == '2.75'
            stale.value = 'Must not change the reloaded object'
            assert app.current()['content'] == 'State {state_value}'
            app.delete()
            assert app.template['variables'] == {}
            asset = tmp_path / 'red.png'
            Image.new('RGB', (20, 20), 'red').save(asset)
            app.add('image')
            monkeypatch.setattr(UI, 'OpenFile', lambda **kwargs: str(asset))
            app.browse_image()
            await settle()
            assert all(n.readonly for n in nodes(app) if isinstance(n, UI.TextEdit))
            package = tmp_path / 'label.lbl'
            monkeypatch.setattr(UI, 'SaveFile', lambda **kwargs: str(package))
            assert app.save()
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
