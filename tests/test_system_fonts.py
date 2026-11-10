from PIL import ImageFont
from labelate.system_fonts import system_fonts
from labelate.renderer import load_font


def test_discovered_families_render_with_collection_index():
    fonts = system_fonts()
    assert fonts
    family, (path, index) = next(iter(fonts.items()))
    assert load_font(path, 20, index).getname()[0] == family
    collection = next(((name, path, index) for name, (path, index) in fonts.items() if index), None)
    if collection:
        name, path, index = collection
        assert ImageFont.truetype(path, 20, index=index).getname()[0] == name
