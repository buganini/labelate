from types import SimpleNamespace
import pytest
from PIL import ImageChops

from labelate.app import Labelate
from labelate.geometry import object_point, contains_point, resize_corner
from labelate.model import new_template, new_object, dumps, loads
from labelate.renderer import render


@pytest.mark.parametrize('angle', [0, 30, 90, 180, 270])
def test_resize_keeps_opposite_corner(angle):
    obj = dict(new_object('rect'), x_mm=40, y_mm=40, rotation_deg=angle)
    opposite = object_point(obj, 0, 0)
    target = object_point(obj, 1.4, 1.6)
    resized = {**obj, **resize_corner(obj, 2, *target)}
    assert object_point(resized, 0, 0) == pytest.approx(opposite)
    assert resized['width_mm'] == pytest.approx(42)
    assert resized['height_mm'] == pytest.approx(24)
    assert contains_point(resized, *object_point(resized, .5, .5))
    assert not contains_point(resized, *object_point(resized, 1.1, .5))


def test_pointer_resize_and_rotate_persist():
    app = Labelate()
    app.notify = lambda: None
    app.add('rect')
    obj = app.current()
    obj['x_mm'], obj['y_mm'] = 30, 30
    app.viewport = (0, 0, 10)
    corners, handle = app.transform_handles(obj)
    app.pointer_down(SimpleNamespace(button=1, x=corners[2][0], y=corners[2][1]))
    app.pointer_move(SimpleNamespace(x=corners[2][0]+100, y=corners[2][1]+50))
    app.pointer_up(None)
    assert (obj['width_mm'], obj['height_mm']) == (40, 20)
    corners, handle = app.transform_handles(obj)
    cx, cy = object_point(obj, .5, .5)
    radius = cy*10-handle[1]
    app.pointer_down(SimpleNamespace(button=1, x=handle[0], y=handle[1]))
    app.pointer_move(SimpleNamespace(x=cx*10+radius, y=cy*10))
    app.pointer_up(None)
    assert obj['rotation_deg'] == pytest.approx(90)
    assert app.object_inputs[obj['id']]['rotation_deg'] == '90'
    assert loads(dumps(app.snapshot()))['objects'][0]['rotation_deg'] == pytest.approx(90)


def test_render_rotates_about_center_and_restores_label_orientation():
    template = new_template()
    template['canvas'].update(width_mm=80, height_mm=80, dpi=254)
    obj = dict(new_object('rect'), x_mm=30, y_mm=35, width_mm=20, height_mm=10, rotation_deg=90)
    template['objects'] = [obj]
    result = render(dumps(template), {})
    assert ImageChops.invert(result).getbbox() == (350, 300, 450, 500)
    template['canvas']['rotation'] = 90
    assert render(dumps(template), {}).tobytes() == result.rotate(-90, expand=True).tobytes()


@pytest.mark.parametrize('angle', [float('nan'), float('inf'), -1, 361, True])
def test_invalid_angles_rejected(angle):
    template = new_template()
    template['objects'] = [dict(new_object('rect'), rotation_deg=angle)]
    with pytest.raises(ValueError, match='rotation'):
        dumps(template)
