# -*- mode: python ; coding: utf-8 -*-
#
# ADIF FZR 2.4 — build PyInstaller per la struttura a moduli
# Compilazione:  pyinstaller ADIF_FZR.spec --clean --noconfirm
#
import os
from PyInstaller.utils.hooks import collect_all

BASE = os.path.abspath(os.getcwd())

datas = []
binaries = []
hiddenimports = []

# --- Librerie di terze parti che PyInstaller NON raccoglie da solo ---
# customtkinter carica i suoi file-tema all'avvio: se mancano, l'exe muore subito.
for pkg in ("customtkinter", "reportlab", "PIL", "adif_io", "openpyxl"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print("Attenzione: collect_all fallito per", pkg, "->", e)

# --- Moduli spesso invisibili all'analisi automatica ---
hiddenimports += [
    # pywin32 (OmniRig) — l'app funziona anche senza, ma se pywin32 c'e' lo includiamo
    "win32com", "win32com.client", "pythoncom", "pywintypes",
    # porte seriali (CAT/rig)
    "serial", "serial.tools", "serial.tools.list_ports",
    # vari
    "sqlite3", "xml", "xml.etree.ElementTree", "html.parser",
    "urllib.request", "urllib.parse", "email",
]

# --- FORZA l'inclusione di TUTTI i tuoi moduli divisi ---
hiddenimports += [
    "config", "main", "theme",
    "gui", "gui.main_window", "gui.widgets",
    "gui.dialogs", "gui.dialogs.charts", "gui.dialogs.dupe_check",
    "gui.dialogs.filters", "gui.dialogs.merge", "gui.dialogs.online_dialogs",
    "gui.dialogs.preferences", "gui.dialogs.qsl_designer",
    "net", "net.dxcluster", "net.hamqth", "net.uploaders", "net.wsjtx",
    "pdf", "pdf.canvas",
    "radio", "radio.bandplan", "radio.omnirig", "radio.sdrconsole",
    "radio.satellite", "radio.sat_db",
    "gui.dialogs.satellite", "gui.dialogs.sat_map",
    "utils", "utils.dxcc", "utils.formatting", "utils.maidenhead", "utils.tooltip",
]

# --- Risorse dell'app (icona, splash, banner, logo): incluse se presenti ---
for res in ("adif_fzr.ico", "icon.ico", "logo.ico",
            "splash.png", "splash.bmp", "splash.jpg",
            "banner.png", "logo.png"):
    if os.path.exists(os.path.join(BASE, res)):
        datas.append((res, "."))

icona = None
for ic in ("adif_fzr.ico", "icon.ico", "logo.ico", "app.ico"):
    if os.path.exists(os.path.join(BASE, ic)):
        icona = ic
        break

a = Analysis(
    ["main.py"],
    pathex=[BASE],           # <-- indispensabile: fa risolvere gli import 'from config import ...'
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ADIF_FZR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX a volte fa insospettire l'antivirus: meglio off
    runtime_tmpdir=None,
    console=False,           # <-- niente finestra nera. Per DEBUG mettere True e ricompilare.
    disable_windowed_traceback=False,
    icon=icona,
)
