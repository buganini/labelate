from pathlib import Path
import zipfile

import pytest
from PIL import Image
from labelate import render
from labelate.model import new_template, new_object, dumps
from labelate.template_io import open_document, portable_document, write_package


def test_zip_roundtrip_and_relative_paths(tmp_path):
    image = tmp_path / 'photo.png'
    Image.new('RGB', (10, 10), 'red').save(image)
    template = new_template()
    obj = new_object('image')
    obj['content'] = str(image)
    template['objects'] = [obj]
    document, assets = portable_document(template)
    relative = document['objects'][0]['content']
    assert relative.startswith('assets/')
    assert not Path(relative).is_absolute()
    assert assets[relative] == image
    archive = tmp_path / 'label.zip'
    write_package(archive, template)
    restored, folder = open_document(archive)
    assert Path(restored['objects'][0]['content']).is_file()
    assert render(dumps(restored), {}).tobytes() == render(dumps(template), {}).tobytes()
    document, _ = portable_document(restored, folder)
    assert document['objects'][0]['content'] == relative


def test_unsafe_zip_and_missing_asset(tmp_path):
    archive = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('../escape.json', '{}')
    with pytest.raises(ValueError, match='Unsafe path'):
        open_document(archive)
    template = new_template()
    obj = new_object('image')
    obj['content'] = str(tmp_path / 'missing.png')
    template['objects'] = [obj]
    with pytest.raises(ValueError, match='Missing asset'):
        write_package(tmp_path / 'missing.zip', template)
