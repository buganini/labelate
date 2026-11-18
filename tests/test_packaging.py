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


def test_running_the_directory_does_not_shadow_stdlib_platform():
    # `python labelate` used to expose labelate/platform.py as the stdlib `platform`,
    # breaking printer drivers ("attempted relative import with no known parent package").
    import subprocess
    import sys
    code = (
        "import runpy, sys; sys.argv=['labelate']; "
        f"sys.path.insert(0, {str(ROOT / 'labelate')!r}); "
        f"runpy.run_path({str(ROOT / 'labelate')!r}, run_name='labelate_test'); "
        "import platform; print(platform.__file__); platform.system()"
    )
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True,
                            env={'QT_QPA_PLATFORM': 'offscreen', 'PATH': ''})
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip().splitlines()[-1]) != ROOT / 'labelate' / 'platform.py'
