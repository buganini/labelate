from io import BytesIO

import msgpack
from msgpack import fallback
import pytest
from PIL import Image
from labelate import render
from labelate.model import new_template, new_object, dumps, loads
from labelate.template_io import open_document


def test_binary_image_roundtrip_without_source(tmp_path):
    data = BytesIO()
    Image.new('RGB', (12, 12), 'red').save(data, format='PNG')
    raw = data.getvalue()
    template = new_template()
    obj = new_object('image')
    obj.update(data=raw, image_name='sample.png')
    template['objects'] = [obj]
    encoded = dumps(template)
    assert isinstance(encoded, bytes)
    assert msgpack.unpackb(encoded, raw=False)['objects'][0]['data'] == raw
    assert fallback.unpackb(encoded, raw=False)['objects'][0]['data'] == raw
    assert loads(fallback.Packer(use_bin_type=True).pack(template)) == template
    file = tmp_path / 'test.lbl'
    file.write_bytes(encoded)
    restored, _ = open_document(file)
    assert restored['objects'][0]['data'] == raw
    assert restored['objects'][0]['image_name'] == 'sample.png'
    assert render(dumps(restored), {}).tobytes() == render(encoded, {}).tobytes()


def test_invalid_image_data_and_old_json():
    with pytest.raises(ValueError):
        loads(b'{"version":1}')
    template = new_template()
    obj = new_object('image')
    obj['data'] = 'not bytes'
    template['objects'] = [obj]
    with pytest.raises(ValueError, match='bytes'):
        dumps(template)
