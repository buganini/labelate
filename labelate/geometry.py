"""Canvas orientation changes the workspace, not object geometry."""


def view_size(canvas):
    w, h = canvas['width_mm'], canvas['height_mm']
    return (h, w) if canvas.get('rotation', 0) in (90, 270) else (w, h)


def to_view(x, y, canvas):
    return x, y


def from_view(x, y, canvas):
    return x, y


def view_box(obj, canvas):
    x, y = obj['x_mm'], obj['y_mm']
    return x, y, x + obj['width_mm'], y + obj['height_mm']


def rotate_vector(x, y, angle):
    from math import radians, sin, cos
    angle = radians(angle)
    return x * cos(angle) - y * sin(angle), x * sin(angle) + y * cos(angle)


def object_point(obj, u, v):
    """Map a normalized point on the unrotated box into label coordinates."""
    w, h = obj['width_mm'], obj['height_mm']
    dx, dy = rotate_vector((u - .5) * w, (v - .5) * h, obj.get('rotation_deg', 0))
    return obj['x_mm'] + w / 2 + dx, obj['y_mm'] + h / 2 + dy


def object_corners(obj):
    return [object_point(obj, u, v) for u, v in ((0, 0), (1, 0), (1, 1), (0, 1))]


def contains_point(obj, x, y):
    w, h = obj['width_mm'], obj['height_mm']
    dx, dy = rotate_vector(x - obj['x_mm'] - w / 2, y - obj['y_mm'] - h / 2,
                           -obj.get('rotation_deg', 0))
    return abs(dx) <= w / 2 and abs(dy) <= h / 2


def resize_corner(obj, corner, x, y):
    """Keep the opposite corner fixed, resizing along the object's local axes."""
    u, v = ((0, 0), (1, 0), (1, 1), (0, 1))[corner]
    ax, ay = object_point(obj, 1 - u, 1 - v)
    angle = obj.get('rotation_deg', 0)
    dx, dy = rotate_vector(x - ax, y - ay, -angle)
    sx, sy = 2 * u - 1, 2 * v - 1
    w, h = max(.1, sx * dx), max(.1, sy * dy)
    cx, cy = rotate_vector(sx * w / 2, sy * h / 2, angle)
    return dict(x_mm=max(0, ax + cx - w / 2), y_mm=max(0, ay + cy - h / 2),
                width_mm=w, height_mm=h)
