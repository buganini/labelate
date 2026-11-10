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
