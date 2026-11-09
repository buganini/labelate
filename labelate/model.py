"""Versioned JSON model. All physical geometry is stored in millimetres."""
import json
import math
import re
import uuid

VARIABLE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
KINDS = ("text", "image", "qr", "code128", "rect")
UNIT_MM = {"mm": 1, "cm": 10, "in": 25.4}
LABEL_PRESETS = {
    **{f"{w} × {h} mm": (w, h) for w, h in (
        (20, 10), (25, 15), (30, 20), (40, 20), (40, 30),
        (50, 25), (50, 30), (50, 40), (60, 30), (60, 40),
        (70, 40), (80, 50), (100, 50), (100, 60), (100, 100), (100, 150))},
    **{f"{w} × {h} in": (w * 25.4, h * 25.4) for w, h in (
        (1, 1), (2, 1), (2, 2), (3, 1), (3, 2), (4, 2), (4, 3), (4, 6), (4, 8))},
}


def new_template():
    return {"version": 1, "canvas": {"width_mm": 100, "height_mm": 60,
            "dpi": 300, "mode": "mono", "unit": "mm"}, "objects": [], "variables": {}}


def new_object(kind):
    if kind not in KINDS:
        raise ValueError(f"Unknown object type: {kind}")
    return {"id": uuid.uuid4().hex, "type": kind, "x_mm": 5, "y_mm": 5,
            "width_mm": 30, "height_mm": 15 if kind != "qr" else 30,
            "content": {"text": "Hello {name}", "image": "", "qr": "https://example.com/{id}",
                        "code128": "{sku}", "rect": ""}[kind],
            "stroke_mm": 0.3, "radius_mm": 0,
            "font": "", "font_size": 12, "font_style": "normal",
            "font_weight": "normal", "color": "#000000"}


def variable_names(template):
    return sorted({name for obj in template["objects"]
                   for name in VARIABLE.findall(obj["content"])})


def reconcile_variables(template):
    old = template.get("variables", {})
    template["variables"] = {key: old.get(key, "") for key in variable_names(template)}


def substitute(content, values):
    def replace(match):
        name = match[1]
        if name not in values:
            raise ValueError(f"Missing variable: {name}")
        return str(values[name])
    return VARIABLE.sub(replace, content)


def positive(value, name, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < 0 or (not allow_zero and value == 0):
        raise ValueError(f"{name} must be {'non-negative' if allow_zero else 'positive'}")


def validate(template):
    try:
        if template["version"] != 1:
            raise ValueError("Unsupported template version")
        canvas = template["canvas"]
        for key in ("width_mm", "height_mm", "dpi"):
            positive(canvas[key], key)
        if canvas["mode"] not in ("mono", "color") or canvas["unit"] not in UNIT_MM:
            raise ValueError("Invalid canvas mode or unit")
        w, h = (max(1, round(canvas[k] * canvas["dpi"] / 25.4)) for k in ("width_mm", "height_mm"))
        if w * h > 40_000_000:
            raise ValueError("Canvas exceeds 40 million pixels")
        if not isinstance(template["objects"], list) or not isinstance(template.get("variables", {}), dict):
            raise ValueError("Invalid objects or variables")
        ids = set()
        for obj in template["objects"]:
            if not isinstance(obj["id"], str) or obj["id"] in ids:
                raise ValueError("Object IDs must be unique strings")
            ids.add(obj["id"])
            if obj["type"] not in KINDS or not isinstance(obj["content"], str):
                raise ValueError("Invalid object type or content")
            if obj['type'] == 'image' and obj['content'].startswith('data:'):
                raise ValueError('Embedded images are not supported; choose an image file')
            if obj['type'] == 'rect':
                positive(obj.get('stroke_mm', 0.3), 'stroke_mm')
                positive(obj.get('radius_mm', 0), 'radius_mm', allow_zero=True)
            for key in ("x_mm", "y_mm", "width_mm", "height_mm"):
                positive(obj[key], key, key in ("x_mm", "y_mm"))
            if round(obj["width_mm"] * canvas["dpi"] / 25.4) * round(obj["height_mm"] * canvas["dpi"] / 25.4) > 40_000_000:
                raise ValueError("Object exceeds 40 million pixels")
            if obj["type"] == "text":
                if obj.get("font_style", "normal") not in ("normal", "italic"):
                    raise ValueError("Invalid font style")
                if obj.get("font_weight", "normal") not in ("normal", "bold"):
                    raise ValueError("Invalid font weight")
                positive(obj.get("font_size", 12), "font_size")
                if obj.get("font_size", 12) > 1000:
                    raise ValueError("Font size must not exceed 1000 pt")
        return template
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Invalid template structure: {exc}") from exc


def loads(source):
    try:
        return validate(json.loads(source))
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid template JSON: {exc}") from exc


def dumps(template):
    validate(template)
    return json.dumps(template, ensure_ascii=False, indent=2)


def display_length(mm, unit):
    return mm / UNIT_MM[unit]


def millimetres(value, unit):
    return value * UNIT_MM[unit]
