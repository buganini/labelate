import io
from types import SimpleNamespace

import pytest
from PIL import Image

from labelate.app import Labelate
from labelate.model import KINDS, new_template, new_object, dumps, loads, draw_order
from labelate.renderer import render


@pytest.mark.parametrize('kind', KINDS)
def test_every_kind_has_integer_z(kind):
    assert new_object(kind)['z'] == 0


def test_old_files_without_z_keep_list_order():
    a, b = new_object('rect'), new_object('text')
    for obj in (a, b):
        del obj['z']
    template = new_template()
    template['objects'] = [a, b]
    restored = loads(dumps(template))
    assert [o['id'] for o in draw_order(restored['objects'])] == [a['id'], b['id']]


def test_draw_order_sorts_by_z_and_keeps_ties_stable():
    objs = [dict(id='a', z=1), dict(id='b', z=0), dict(id='c'), dict(id='d', z=-2)]
    assert [o['id'] for o in draw_order(objs)] == ['d', 'b', 'c', 'a']


@pytest.mark.parametrize('z', [1.5, True, '1', 2_000_000])
def test_invalid_z_rejected(z):
    template = new_template()
    template['objects'] = [dict(new_object('rect'), z=z)]
    with pytest.raises(ValueError):
        dumps(template)


def test_renderer_draws_higher_z_on_top():
    template = new_template()
    template['canvas'].update(width_mm=10, height_mm=10, dpi=100, mode='color')
    png = io.BytesIO()
    Image.new('RGB', (8, 8), '#ff0000').save(png, 'PNG')
    square = dict(x_mm=0, y_mm=0, width_mm=10, height_mm=10)
    # Rects are black outlines; a 5 mm stroke on a 10 mm square inks the centre pixel.
    black = dict(new_object('rect'), **square, stroke_mm=5, z=0)
    red = dict(new_object('image'), **square, data=png.getvalue(), z=1)
    template['objects'] = [red, black]  # list order says black on top; z must win
    centre = (20, 20)
    assert render(dumps(template), {}).getpixel(centre) == (255, 0, 0)
    red['z'], black['z'] = 0, 1
    assert render(dumps(template), {}).getpixel(centre) == (0, 0, 0)


def make_app():
    app = Labelate()
    app.notify = lambda: None
    return app


def test_add_places_new_object_on_top_and_restack():
    app = make_app()
    app.add('rect')
    first = app.current()
    app.add('text')
    second = app.current()
    assert second['z'] > first['z']

    app.selected = first['id']
    app.to_front()
    assert first['z'] > second['z']
    z = first['z']
    app.to_front()
    assert first['z'] == z  # already in front: no drift
    app.to_back()
    assert first['z'] < second['z']
    assert app.object_inputs[first['id']]['z'] == str(first['z'])
    assert loads(dumps(app.snapshot()))['objects'][0]['z'] == first['z']


def test_hit_test_picks_highest_z():
    app = make_app()
    app.add('rect')
    low = app.current()
    app.add('rect')
    high = app.current()
    app.selected = high['id']
    app.to_back()
    app.selected = None
    app.viewport = (0, 0, 10)
    app.pointer_down(SimpleNamespace(button=1, x=100, y=100))
    assert app.selected == low['id']


def test_z_text_field_accepts_integers_only():
    app = make_app()
    app.add('rect')
    obj = app.current()
    inputs = app.object_inputs[obj['id']]
    inputs['z'] = '7'
    assert obj['z'] == 7 and type(obj['z']) is int
    inputs['z'] = '1.5'
    assert obj['z'] == 7
    assert inputs['z'] == '7'
