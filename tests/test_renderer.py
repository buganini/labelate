
import pytest
from PIL import Image

from labelate import render
from labelate.model import (new_template, new_object, dumps, loads, variable_names,
                            reconcile_variables, display_length, millimetres)


@pytest.mark.parametrize('unit', ['mm', 'cm', 'in'])
def test_units_and_dimensions(unit):
    template = new_template()
    template['canvas'].update(width_mm=25.4, height_mm=50.8, dpi=300, unit=unit)
    image = render(dumps(template), {})
    assert image.size == (300, 600)
    assert image.mode == '1'
    assert millimetres(display_length(123.456, unit), unit) == pytest.approx(123.456)
    assert display_length(100, 'cm') == 10
    assert millimetres(10, 'cm') == 100
    assert loads(dumps(template)) == template


def test_variables_all_types_and_cleanup():
    template = new_template()
    for kind in ('text', 'image', 'qr', 'code128'):
        obj = new_object(kind)
        obj['content'] = '{shared}/{' + kind + '}'
        template['objects'].append(obj)
    template['variables'] = {'shared': 'kept', 'unused': 'removed'}
    reconcile_variables(template)
    assert variable_names(template) == ['code128', 'image', 'qr', 'shared', 'text']
    assert template['variables']['shared'] == 'kept'
    assert 'unused' not in template['variables']


def test_all_objects_and_override(tmp_path):
    template = new_template()
    template['canvas'].update(mode='color', dpi=300)
    asset = tmp_path / 'red.png'
    Image.new('RGB', (20, 20), 'red').save(asset)
    for i, kind in enumerate(('text', 'image', 'qr', 'code128')):
        obj = new_object(kind)
        obj.update(content={'text': '{name}', 'image': '{asset}', 'qr': '{url}', 'code128': '{sku}'}[kind],
                   x_mm=1, y_mm=i * 14, width_mm=80, height_mm=12)
        template['objects'].append(obj)
    values = {'name': 'Test', 'asset': str(asset), 'url': 'abc', 'sku': '12345'}
    result = render(dumps(template), values)
    assert result.mode == 'RGB'
    assert result.getbbox()
    assert result.getpixel((round(41 * 300 / 25.4), round(20 * 300 / 25.4))) == (255, 0, 0)
    template['variables']['name'] = 'Default'
    assert render(dumps(template), values).tobytes() == result.tobytes()


def test_image_path_and_mono(tmp_path):
    path = tmp_path / 'black.png'
    Image.new('RGB', (5, 5), 'black').save(path)
    template = new_template()
    obj = new_object('image')
    obj['content'] = str(path)
    template['objects'].append(obj)
    image = render(dumps(template), {})
    assert image.mode == '1'
    assert image.getextrema() == (0, 255)


def test_errors():
    template = new_template()
    template['objects'].append(new_object('text'))
    with pytest.raises(ValueError, match='Missing variable: name'):
        render(dumps(template), {})
    template['objects'] = [new_object('code128')]
    with pytest.raises(ValueError, match='ASCII'):
        render(dumps(template), {'sku': '中文'})
    template['objects'][0]['width_mm'] = .1
    with pytest.raises(ValueError, match='too narrow'):
        render(dumps(template), {'sku': '123'})
    template['canvas']['dpi'] = -1
    with pytest.raises(ValueError, match='positive'):
        dumps(template)


@pytest.mark.parametrize('value', ['null', '[]', '{}', '{invalid'])
def test_bad_json(value):
    with pytest.raises(ValueError):
        loads(value)


def test_text_style_weight_and_legacy_defaults():
    template = new_template()
    obj = new_object('text')
    obj.update(content='Style test', width_mm=80, height_mm=20)
    template['objects'] = [obj]
    regular = render(dumps(template), {})
    variants = {regular.tobytes()}
    for style, weight in [('normal', 'bold'), ('italic', 'normal'), ('italic', 'bold')]:
        obj.update(font_style=style, font_weight=weight)
        restored = loads(dumps(template))
        assert restored['objects'][0]['font_style'] == style
        image = render(dumps(restored), {})
        assert image.size == regular.size
        variants.add(image.tobytes())
    assert len(variants) == 4
    del obj['font_style'], obj['font_weight']
    assert render(dumps(template), {}).tobytes() == regular.tobytes()
    obj['font_weight'] = 'invalid'
    with pytest.raises(ValueError, match='font weight'):
        dumps(template)


def test_rect_outline_radius_and_validation():
    template = new_template()
    template['canvas'].update(dpi=254, width_mm=20, height_mm=20)
    obj = new_object('rect')
    obj.update(x_mm=0, y_mm=0, width_mm=20, height_mm=20, stroke_mm=1, radius_mm=0)
    template['objects'] = [obj]
    image = render(dumps(template), {})
    assert image.getpixel((0, 0)) == 0
    assert image.getpixel((100, 9)) == 0
    assert image.getpixel((100, 10)) == 255
    assert image.getpixel((100, 100)) == 255
    obj['radius_mm'] = 5
    rounded = render(dumps(template), {})
    assert rounded.getpixel((0, 0)) == 255
    assert rounded.getpixel((100, 0)) == 0
    obj['radius_mm'] = -1
    with pytest.raises(ValueError, match='radius_mm'):
        dumps(template)


@pytest.mark.parametrize('style,weight', [('normal','normal'), ('normal','bold'), ('italic','normal'), ('italic','bold')])
def test_multiline_text_has_multiple_ink_rows(style, weight):
    from labelate.renderer import object_image
    template = new_template()
    obj = new_object('text')
    obj.update(content='Hello {name}\nSecond line', width_mm=80, height_mm=30,
               font_style=style, font_weight=weight)
    template['objects'] = [obj]
    template['variables'] = {'name': 'Ada'}
    image = render(dumps(template), {})
    assert image.mode == '1'
    tile = object_image(obj, template['canvas'], template['variables'])
    alpha = tile.getchannel('A')
    occupied = [alpha.crop((0, y, alpha.width, y + 1)).getbbox() is not None for y in range(alpha.height)]
    runs = sum(value and (index == 0 or not occupied[index - 1]) for index, value in enumerate(occupied))
    assert runs >= 2
    assert alpha.getbbox()[1] == 0
