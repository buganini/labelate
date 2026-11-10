"""Editor view transforms; saved geometry always uses the unrotated label axes."""


def view_size(canvas):
    w, h = canvas['width_mm'], canvas['height_mm']
    return (h, w) if canvas.get('rotation', 0) in (90, 270) else (w, h)


def to_view(x, y, canvas):
    w, h = canvas['width_mm'], canvas['height_mm']
    angle = canvas.get('rotation', 0)
    if angle == 90:
        return h-y, x
    if angle == 180:
        return w-x, h-y
    if angle == 270:
        return y, w-x
    return x, y


def from_view(x, y, canvas):
    w, h = canvas['width_mm'], canvas['height_mm']
    angle = canvas.get('rotation', 0)
    if angle == 90:
        return y, h-x
    if angle == 180:
        return w-x, h-y
    if angle == 270:
        return w-y, x
    return x, y


def view_box(obj, canvas):
    x, y = obj['x_mm'], obj['y_mm']
    a, b = to_view(x, y, canvas), to_view(x+obj['width_mm'], y+obj['height_mm'], canvas)
    return min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])
