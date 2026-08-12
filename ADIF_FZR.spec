# -*- mode: python ; coding: utf-8 -*-
# Build ONEFILE di ADIF FZR 2.4 (struttura a moduli)
# Lancio:  python -m PyInstaller ADIF_FZR.spec --clean --noconfirm
import os
from PyInstaller.utils.hooks import collect_all

BASE = os.path.abspath(os.getcwd())
PKG  = os.path.join(BASE, "ADIF_FZR_Modular")

datas = []
binaries = []
hiddenimports = []

for pkg in ("customtkinter", "reportlab", "PIL", "adif_io", "openpyxl", "skyfield", "sgp4", "matplotlib"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:
        print("collect_all fallito per", pkg, "->", e)

hiddenimports += [
    "win32com", "win32com.client", "pythoncom", "pywintypes",
    "serial", "serial.tools", "serial.tools.list_ports",
    "sqlite3", "xml", "xml.etree.ElementTree", "html.parser",
    "urllib.request", "urllib.parse", "email",
    "skyfield", "skyfield.api", "sgp4", "sgp4.api", "numpy",
    "matplotlib", "matplotlib.backends.backend_tkagg",
    "config", "main", "theme",
    "gui", "gui.main_window", "gui.widgets",
    "gui.dialogs", "gui.dialogs.charts", "gui.dialogs.dupe_check",
    "gui.dialogs.filters", "gui.dialogs.merge", "gui.dialogs.online_dialogs",
    "gui.dialogs.preferences", "gui.dialogs.qsl_designer", "gui.dialogs.satellite", "gui.dialogs.sat_map",
    "net", "net.dxcluster", "net.hamqth", "net.uploaders", "net.wsjtx",
    "pdf", "pdf.canvas",
    "radio", "radio.bandplan", "radio.omnirig", "radio.sdrconsole", "radio.satellite", "radio.coastlines", "radio.sat_db",
    "utils", "utils.dxcc", "utils.formatting", "utils.maidenhead", "utils.tooltip",
]

# Risorse: le cerco sia nella cartella genitore sia dentro ADIF_FZR_Modular.
def trova(nome):
    for d in (BASE, PKG):
        p = os.path.join(d, nome)
        if os.path.exists(p):
            return p
    return None

for nome in ("splash.png", "splash.jpg", "banner.png", "logo.png",
             "icon.ico", "adif_fzr.ico"):
    p = trova(nome)
    if p:
        datas.append((p, "."))   # in Python il ';' non serve: si usa la tupla

icona = None
for ic in ("icon.ico", "adif_fzr.ico"):
    p = trova(ic)
    if p:
        icona = p
        break

a = Analysis(
    [os.path.join(PKG, "main.py")],
    pathex=[PKG, BASE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="ADIF_FZR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=icona,
)
