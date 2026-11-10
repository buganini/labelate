"""Pure Pillow rendering; no QApplication or display server required."""
from pathlib import Path
from io import BytesIO

import barcode
import qrcode
from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

from .model import loads, substitute

DEFAULT_FONT = Path(__file__).with_name('fonts') / 'NotoSansCJKtc-Regular.otf'

def pixels(mm, dpi):
    return max(1, round(mm * dpi / 25.4))


def load_font(path, size):
    if path:
        return ImageFont.truetype(path, size)
    if DEFAULT_FONT.is_file():
        return ImageFont.truetype(str(DEFAULT_FONT), size)
    for candidate in ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                      "/System/Library/Fonts/Supplemental/Arial.ttf",
                      "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def object_image(obj, canvas, values):
    dpi = canvas["dpi"]
    size = (pixels(obj["width_mm"], dpi), pixels(obj["height_mm"], dpi))
    content = substitute(obj["content"], values) if obj["type"] in ("text", "qr", "code128") else ""
    tile = Image.new("RGBA", size, (255, 255, 255, 0))
    kind = obj["type"]
    if kind == "rect":
        width = min(pixels(obj.get('stroke_mm', 0.3), dpi), (min(size) + 1) // 2)
        radius = min(round(obj.get('radius_mm', 0) * dpi / 25.4), min(size) // 2)
        ImageDraw.Draw(tile).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1),
                                              radius=radius, outline='black', width=width)
    elif kind == "text":
        font_pixels = max(1, round(obj.get("font_size", 12) * dpi / 72))
        font = load_font(obj.get("font", ""), font_pixels)
        color = obj.get("color", "#000000") if canvas["mode"] == "color" else "#000000"
        ImageColor.getrgb(color)
        stroke = max(1, round(font_pixels / 30)) if obj.get("font_weight", "normal") == "bold" else 0
        draw = ImageDraw.Draw(tile)
        # Pillow does not support the top ("t") anchor for multiline text.
        # Offset the ascender-anchored bounding box to keep visible ink at (0, 0).
        bounds = draw.multiline_textbbox((0, 0), content, font=font, spacing=0,
                                         anchor='la', stroke_width=stroke)
        draw.multiline_text((-bounds[0], -bounds[1]), content, font=font, fill=color,
                           spacing=0, anchor='la', stroke_width=stroke, stroke_fill=color)
        if obj.get("font_style", "normal") == "italic":
            bounds = tile.getbbox()
            if bounds:
                # Apply a consistent 12-degree slant to any chosen font file.
                shear = 0.21256
                tile = tile.transform(size, Image.Transform.AFFINE,
                                      (1, shear, -shear * bounds[3], 0, 1, 0),
                                      resample=Image.Resampling.BICUBIC)
    elif kind == "image":
        if not obj.get("data"):
            raise ValueError("Choose an image file")
        source = BytesIO(obj["data"])
        with Image.open(source) as image:
            fitted = ImageOps.contain(image.convert("RGBA"), size, Image.Resampling.LANCZOS)
        tile.alpha_composite(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    elif kind == "qr":
        qr = qrcode.QRCode(box_size=1, border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(content)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
        scale = min(size) // image.width
        if scale < 1:
            raise ValueError("QR object is too small at this DPI")
        image = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
        tile.alpha_composite(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    else:
        if not content or any(ord(c) > 127 for c in content):
            raise ValueError("Code 128 requires non-empty ASCII content")
        bits = barcode.get("code128", content).build()[0]
        quiet = 10
        scale = size[0] // (len(bits) + quiet * 2)
        if scale < 1:
            raise ValueError("Code 128 object is too narrow at this DPI")
        width = (len(bits) + quiet * 2) * scale
        draw = ImageDraw.Draw(tile)
        left = (size[0] - width) // 2
        draw.rectangle((left, 0, left + width - 1, size[1] - 1), fill="white")
        for index, bit in enumerate(bits):
            if bit == "1":
                x = left + (quiet + index) * scale
                draw.rectangle((x, 0, x + scale - 1, size[1] - 1), fill="black")
    return tile


def render(lbl_bytes, variables):
    """Render a v2 MessagePack template to RGB or 8-bit greyscale PIL.Image.Image.

    Explicit variables override template defaults. Missing variables, invalid
    assets and unrenderable barcodes raise ValueError with object context.
    Relative font paths are resolved against the working directory.
    Canvas rotation is editor-only: output always uses the original label axes.
    """
    template = loads(lbl_bytes)
    canvas = template["canvas"]
    values = {**template.get("variables", {}), **variables}
    result = Image.new("RGBA", (pixels(canvas["width_mm"], canvas["dpi"]),
                                 pixels(canvas["height_mm"], canvas["dpi"])), "white")
    for obj in template["objects"]:
        try:
            tile = object_image(obj, canvas, values)
            result.alpha_composite(tile, (round(obj["x_mm"] * canvas["dpi"] / 25.4),
                                         round(obj["y_mm"] * canvas["dpi"] / 25.4)))
        except Exception as exc:
            raise ValueError(f"Object {obj['id']} ({obj['type']}): {exc}") from exc
    result = result.convert("RGB")
    if canvas["mode"] == "greyscale":
        result = result.convert("L")
    result.info["dpi"] = (canvas["dpi"], canvas["dpi"])
    return result
