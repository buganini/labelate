from pathlib import Path
import tomllib

from labelate.app import Labelate

ROOT = Path(__file__).resolve().parents[1]


def test_window_icon_ships_inside_the_package():
    # The browser backend reads the icon file at startup, so it must travel with
    # the labelate package (app.zip, wheel, PyInstaller) rather than live in resources/.
    icon = Path(Labelate().icon)
    assert icon.is_file()
    assert icon.parent == ROOT / 'labelate'
    package_data = tomllib.loads((ROOT / 'pyproject.toml').read_text())['tool']['setuptools']['package-data']
    assert icon.name in package_data['labelate']
    assert f"'labelate/{icon.name}'" in (ROOT / 'scripts/build_pyodide.py').read_text()
