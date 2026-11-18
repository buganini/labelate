"""Exercise real converters offline and mock only device I/O."""
import copy
from types import SimpleNamespace

import pytest
from labelate import printing as p
from labelate.model import new_template, new_object, dumps, loads


def fixture(brand='TSC'):
    printer = p.Printer(brand, 'device-id', {'TSC': 'pyusb', 'Brother': 'pyusb', 'Niim': 'bleak'}[brand], 'Test')
    config = p.settings(brand)
    config['model'] = {'TSC': 'TTP-342', 'Brother': 'QL-800', 'Niim': 'M2_H'}[brand]
    template = new_template()
    template['canvas'].update(width_mm=62 if brand == 'Brother' else 40, height_mm=30)
    return printer, config, template


@pytest.mark.parametrize('brand', ['Brother', 'Niim', 'TSC'])
def test_real_conversion_without_device(brand):
    pytest.importorskip(p.PACKAGES[brand])
    printer, config, template = fixture(brand)
    assert config['model'] in p.models(brand)
    original = copy.deepcopy(template)
    job = p.prepare(printer, config, dumps(template), {})
    assert template == original
    if brand == 'TSC':
        assert b'BITMAP 0,0,60,360,' in job  # 40 x 30 mm at exactly 12 dots/mm
    elif brand == 'Niim':
        assert (job.pages[0].width, job.pages[0].height) == (472, 354)
    else:
        assert isinstance(job, bytes) and len(job) > 100


def test_data_roundtrip_and_validation():
    template = new_template()
    template['data_rows'] = [{'name': 'Coffee'}, {'name': 'Tea'}]
    assert loads(dumps(template))['data_rows'] == template['data_rows']
    template['data_rows'][0]['name'] = 123
    with pytest.raises(ValueError, match='Data rows'):
        dumps(template)


@pytest.mark.parametrize('value', ['0', '-1', '1.5', 'nan', '', '２'])
def test_invalid_copies(value):
    with pytest.raises(ValueError, match='positive integer'):
        p.positive_integer(value)


def test_batch_preflights_all_rows_and_stops_on_error(monkeypatch):
    printer, config, template = fixture()
    calls = []
    def prepare(*args):
        row = args[-1]
        calls.append(('prepare', row['name']))
        if row['name'] == 'bad':
            raise ValueError('bad row')
        return row['name']
    monkeypatch.setattr(p, 'prepare', prepare)
    def send(*args):
        calls.append(('send', args[-1]))
        if args[-1] == 'second':
            raise OSError('disconnected')
        return {'outcome': 'sent'}
    monkeypatch.setattr(p, 'send', send)
    with pytest.raises(ValueError, match='bad row'):
        p.print_labels(printer, config, dumps(template), [{'name':'first'}, {'name':'bad'}], 1)
    assert not any(c[0] == 'send' for c in calls)
    calls.clear()
    with pytest.raises(RuntimeError, match='Stopped after 2/4'):
        p.print_labels(printer, config, dumps(template), [{'name':'first'}, {'name':'second'}], 2)
    assert calls[:2] == [('prepare','first'), ('prepare','second')]
    assert [c for c in calls if c[0] == 'send'] == [('send','first'), ('send','first'), ('send','second')]


def test_cups_preserves_queue_and_reports_submission(monkeypatch):
    printer, config, template = fixture()
    printer = p.Printer('TSC', 'cups://test', 'cups', 'Test')
    sent = []
    helper = SimpleNamespace(send=lambda *a, **kw: sent.append(kw) or {'outcome':'queued'})
    monkeypatch.setattr(p, 'module', lambda *args: helper)
    monkeypatch.setattr(p, 'prepare', lambda *args: b'job')
    result = p.print_labels(printer, config, dumps(template), [{}], 2)
    assert len(sent) == 2
    assert all(row['recreate_queue'] is False for row in sent)
    assert 'physical printing not confirmed' in result


def test_discovery_preserves_backend_and_warnings(monkeypatch):
    helper = SimpleNamespace(discover=lambda: [
        {'identifier':'device', 'description':'Adapter', 'backend':'serial'},
        {'identifier':'device', 'description':'Adapter', 'backend':'serial'},
        {'kind':'warning', 'message':'USB unavailable'},
    ])
    monkeypatch.setattr(p, 'module', lambda *args: helper)
    devices, warnings = p.discover('TSC')
    assert len(devices) == 1 and devices[0].backend == 'serial'
    assert warnings == ['USB unavailable']


def test_brother_rejects_marks_in_margin():
    pytest.importorskip('brother_ql')
    printer, config, template = fixture('Brother')
    obj = new_object('rect')
    obj.update(x_mm=0, y_mm=0, width_mm=62, height_mm=30)
    template['objects'] = [obj]
    with pytest.raises(ValueError, match='unprintable margins'):
        p.prepare(printer, config, dumps(template), {})


def test_module_error_distinguishes_missing_from_broken(monkeypatch):
    import importlib
    from labelate import printing

    def missing(name):
        raise ModuleNotFoundError(f"No module named '{name.split('.')[0]}'", name=name.split('.')[0])
    monkeypatch.setattr(importlib, 'import_module', missing)
    with pytest.raises(RuntimeError, match=r"pip install -e '\.\[niim\]'"):
        printing.module('Niim', 'models')

    def broken(name):
        raise ImportError('attempted relative import with no known parent package')
    monkeypatch.setattr(importlib, 'import_module', broken)
    with pytest.raises(RuntimeError, match='restart Labelate') as info:
        printing.module('Niim', 'models')
    assert 'pip install' not in str(info.value)

    def dependency(name):
        raise ModuleNotFoundError("No module named 'bleak'", name='bleak')
    monkeypatch.setattr(importlib, 'import_module', dependency)
    with pytest.raises(RuntimeError, match="pyniim is installed but failed to import: No module named 'bleak'"):
        printing.module('Niim', 'models')


def test_discovered_niim_model_prefills_and_skips_settings():
    pytest.importorskip('pyniim')
    found = p.Printer('Niim', 'AA:BB', 'bleak', 'M2_H-1234', 'M2_H')
    config = p.settings('Niim', found)
    assert config['model'] == 'M2_H'
    assert not p.needs_settings('Niim', config)
    # Unknown or missing models still ask, and Brother/TSC always ask the first time.
    assert p.settings('Niim', p.Printer('Niim', 'AA:BB', 'bleak', 'X', 'NOPE'))['model'] == ''
    assert p.needs_settings('Niim', p.settings('Niim'))
    assert p.needs_settings('TSC', {'model': 'TTP-342'})
    assert p.needs_settings('Brother', {'model': 'QL-800'})


def test_app_prints_niim_without_modal(monkeypatch):
    pytest.importorskip('pyniim')
    from labelate.app import Labelate
    from labelate import platform as desktop
    app = Labelate()
    app.notify = lambda: None
    app.brand = 'Niim'
    found = p.Printer('Niim', 'AA:BB', 'bleak', 'M2_H-1234', 'M2_H')
    app.printers, app.printer_choice = [found], found.display
    started = []
    monkeypatch.setattr(desktop, 'PRINTING', True)
    monkeypatch.setattr(app, 'run_task', lambda message, work, complete: started.append(message))
    app.request_print()
    assert not app.settings_open
    assert started == ['Preparing print…']
    assert app.printer_configs[app.config_key()]['model'] == 'M2_H'
    # The model can still be changed afterwards, starting from the remembered value.
    app.configure_printer(False)
    assert app.settings_open and app.settings_draft['model'] == 'M2_H'


def test_app_still_asks_when_model_unknown(monkeypatch):
    pytest.importorskip('pyniim')
    from labelate.app import Labelate
    from labelate import platform as desktop
    app = Labelate()
    app.notify = lambda: None
    app.brand = 'Niim'
    found = p.Printer('Niim', 'AA:BB', 'bleak', 'Mystery')
    app.printers, app.printer_choice = [found], found.display
    monkeypatch.setattr(desktop, 'PRINTING', True)
    monkeypatch.setattr(app, 'run_task', lambda *a: pytest.fail('printed without a model'))
    app.request_print()
    assert app.settings_open and app.pending_print and app.settings_draft['model'] == ''
