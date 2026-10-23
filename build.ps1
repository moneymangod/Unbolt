# Builds dist\Unbolt.exe (window) and dist\unbolt-cli.exe (command line).
# Usage:  python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt; .\build.ps1
$py = ".\.venv\Scripts\python.exe"
& $py tools\make_icon.py
$common = "--noconfirm", "--onefile", "--collect-all", "imageio_ffmpeg", "--collect-all", "pyflp", "--hidden-import", "zstandard"
& $py -m PyInstaller @common --windowed --name Unbolt --icon assets\icon.ico --add-data "assets\icon.ico;assets" `
    --collect-all tkinterdnd2 run_gui.py
& $py -m PyInstaller @common --console --name unbolt-cli --icon assets\icon.ico `
    --exclude-module tkinter --exclude-module tkinterdnd2 run_cli.py
