"""Resolve desktop font families to Pillow-readable files without native dependencies."""
import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont


@lru_cache(maxsize=1)
def system_fonts():
    roots = [
        Path('/System/Library/Fonts'), Path('/Library/Fonts'), Path.home() / 'Library/Fonts',
        Path('/usr/share/fonts'), Path('/usr/local/share/fonts'),
        Path.home() / '.fonts', Path.home() / '.local/share/fonts',
        Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts',
        Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Microsoft/Windows/Fonts',
    ]
    families = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob('*')):
            if path.suffix.lower() not in ('.ttf', '.otf', '.ttc', '.otc'):
                continue
            for index in range(256 if path.suffix.lower() in ('.ttc', '.otc') else 1):
                try:
                    font = ImageFont.truetype(str(path), 12, index=index)
                    family, style = font.getname()
                except (OSError, ValueError):
                    break
                if family not in families or style.lower() in ('regular', 'normal', 'book'):
                    families[family] = (str(path), index)
    return families
