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
