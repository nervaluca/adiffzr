# -*- coding: utf-8 -*-
"""
Integrazione WSJT-X con ADIF FZR  —  profilo dedicato + CAT condiviso via rigctld.

Idea: ADIF FZR tiene la porta COM della radio ed espone rigctld (TCP
127.0.0.1:4532). WSJT-X non apre la COM: si collega come "Hamlib NET rigctl"
allo stesso rigctld, cosi' i due programmi condividono la radio senza conflitti.
Il PTT passa dal CAT (comando TX via Hamlib).

Per non toccare la configurazione WSJT-X che usi di solito (con JTAlert), si
crea un PROFILO DEDICATO: WSJT-X avviato con  --rig-name=ADIFFZR  legge il file
"WSJT-X - ADIFFZR.ini". Questo file viene creato clonando la tua WSJT-X.ini
(cosi' audio, report, nominativo restano identici) e cambiando solo le chiavi
CAT/UDP.

La sezione CALCOLO/FILE e' indipendente dalla GUI e testabile a parte.
"""
import os
import re
import sys
import json
import shutil
import subprocess

PROFILO = "ADIFFZR"            # nome del profilo dedicato (--rig-name)
RIG_NET = "Hamlib NET rigctl"  # tipo radio in WSJT-X
DEF_HOST = "127.0.0.1"
DEF_PORT = 4532                # porta rigctld di ADIF FZR
UDP_HOST = "127.0.0.1"
UDP_PORT = 2237                # FZR ALERT


# =========================================================================== #
#  CONFIGURAZIONE PERSISTENTE  (~/.adif_fzr_wsjtx.json)
# =========================================================================== #
def cfg_path():
    """File di configurazione dell'integrazione WSJT-X (stile ADIF FZR)."""
    return os.path.join(os.path.expanduser("~"), ".adif_fzr_wsjtx.json")


def carica_cfg():
    """Ritorna il dict salvato (exe, host, port, ...) o {} se assente."""
    try:
        with open(cfg_path(), "r", encoding="utf-8") as fh:
            d = json.load(fh)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def salva_cfg(d):
    """Salva/aggiorna il dict di configurazione. Ritorna True/False."""
    try:
        cur = carica_cfg()
        cur.update({k: v for k, v in d.items() if v is not None})
        with open(cfg_path(), "w", encoding="utf-8") as fh:
            json.dump(cur, fh, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# =========================================================================== #
#  RILEVAMENTO
# =========================================================================== #
def trova_wsjtx_exe():
    """Percorso di wsjtx.exe, o None.

    Prima il percorso salvato in configurazione (se ancora valido), poi il
    registro di Windows e i path tipici."""
    salvato = carica_cfg().get("exe")
    if salvato and os.path.isfile(salvato):
        return salvato
    cand = []
    # Registro (Windows): chiavi di disinstallazione e App Paths
    if os.name == "nt":
        try:
            import winreg
            chiavi = [
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\wsjtx.exe"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\wsjtx.exe"),
            ]
            for root, path in chiavi:
                try:
                    with winreg.OpenKey(root, path) as k:
                        val, _ = winreg.QueryValueEx(k, None)
                        if val and os.path.isfile(val):
                            return val
                except OSError:
                    pass
            # Uninstall: cerca InstallLocation di WSJT-X
            for root in (winreg.HKEY_LOCAL_MACHINE,):
                for sub in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
                    try:
                        with winreg.OpenKey(root, sub) as k:
                            i = 0
                            while True:
                                try:
                                    nome = winreg.EnumKey(k, i); i += 1
                                except OSError:
                                    break
                                if "wsjt" not in nome.lower():
                                    continue
                                try:
                                    with winreg.OpenKey(k, nome) as kk:
                                        loc, _ = winreg.QueryValueEx(kk, "InstallLocation")
                                        exe = os.path.join(loc, "bin", "wsjtx.exe")
                                        if os.path.isfile(exe):
                                            return exe
                                except OSError:
                                    pass
                    except OSError:
                        pass
        except Exception:
            pass
    # Path tipici
    home = os.path.expanduser("~")
    basi = [
        r"C:\WSJT-X\bin\wsjtx.exe",
        r"C:\Program Files\WSJT-X\bin\wsjtx.exe",
        r"C:\Program Files (x86)\WSJT-X\bin\wsjtx.exe",
        r"C:\WSJT-X-improved\bin\wsjtx.exe",
        r"C:\Program Files\WSJT-X-improved\bin\wsjtx.exe",
        # macOS: binario dentro il bundle .app
        "/Applications/wsjtx.app/Contents/MacOS/wsjtx",
        "/Applications/WSJT-X.app/Contents/MacOS/wsjtx",
        os.path.join(home, "Applications/wsjtx.app/Contents/MacOS/wsjtx"),
        # Linux / Homebrew / MacPorts
        "/usr/bin/wsjtx", "/usr/local/bin/wsjtx",
        "/opt/homebrew/bin/wsjtx", "/opt/local/bin/wsjtx",
    ]
    for p in basi:
        if os.path.isfile(p):
            return p
    # macOS: scansiona /Applications per qualsiasi bundle *wsjt*.app
    if sys.platform == "darwin":
        import glob
        for radice in ("/Applications", os.path.join(home, "Applications")):
            for app in glob.glob(os.path.join(radice, "*[Ww][Ss][Jj][Tt]*.app")):
                exe = os.path.join(app, "Contents", "MacOS", "wsjtx")
                if os.path.isfile(exe):
                    return exe
    return None


def _norm(p):
    """Path normalizzato per confronti (case-insensitive su Windows)."""
    try:
        q = os.path.normcase(os.path.normpath(os.path.abspath(p)))
        return q
    except Exception:
        return p or ""


def trova_installazioni():
    """Elenca TUTTE le installazioni di WSJT-X trovate.

    Utile quando sul PC ci sono piu' versioni (standard, -improved, build
    diverse): ritorna una lista di dict ordinata, senza duplicati:
        {"exe": percorso, "label": "Nome vX.Y", "fonte": "registro|path|config|manuale"}
    L'eventuale percorso salvato in configurazione e' sempre il primo.
    """
    trovate = []
    visti = set()

    def _aggiungi(exe, label, fonte):
        if not exe or not os.path.isfile(exe):
            return
        key = _norm(exe)
        if key in visti:
            return
        visti.add(key)
        trovate.append({"exe": exe, "label": label or os.path.basename(os.path.dirname(os.path.dirname(exe))) or "WSJT-X",
                        "fonte": fonte})

    # 0) Config salvata
    salvato = carica_cfg().get("exe")
    if salvato and os.path.isfile(salvato):
        _aggiungi(salvato, "Salvata (ultima usata)", "config")

    # 1) Registro Windows: Uninstall (DisplayName + DisplayVersion + InstallLocation)
    if os.name == "nt":
        try:
            import winreg
            viste_reg = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            ]
            for hive, sub in viste_reg:
                try:
                    with winreg.OpenKey(hive, sub) as k:
                        i = 0
                        while True:
                            try:
                                nome = winreg.EnumKey(k, i); i += 1
                            except OSError:
                                break
                            try:
                                with winreg.OpenKey(k, nome) as kk:
                                    def _rv(key):
                                        try: return winreg.QueryValueEx(kk, key)[0]
                                        except OSError: return ""
                                    dn = str(_rv("DisplayName") or "")
                                    if "wsjt" not in dn.lower() and "wsjt" not in nome.lower():
                                        continue
                                    dv = str(_rv("DisplayVersion") or "")
                                    loc = str(_rv("InstallLocation") or "")
                                    exe = ""
                                    if loc:
                                        for c in (os.path.join(loc, "bin", "wsjtx.exe"),
                                                  os.path.join(loc, "wsjtx.exe")):
                                            if os.path.isfile(c):
                                                exe = c; break
                                    lbl = (dn or "WSJT-X").strip()
                                    if dv and dv not in lbl:
                                        lbl = "%s %s" % (lbl, dv)
                                    _aggiungi(exe, lbl, "registro")
                            except OSError:
                                pass
                except OSError:
                    pass
            # App Paths (default)
            for sub in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\wsjtx.exe",
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\wsjtx.exe"):
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub) as k:
                        val, _ = winreg.QueryValueEx(k, None)
                        _aggiungi(val, "WSJT-X (App Paths)", "registro")
                except OSError:
                    pass
        except Exception:
            pass

    # 2) Path tipici + scansione cartelle comuni per varianti
    import glob
    home = os.path.expanduser("~")
    basi = [
        r"C:\WSJT-X\bin\wsjtx.exe",
        r"C:\Program Files\WSJT-X\bin\wsjtx.exe",
        r"C:\Program Files (x86)\WSJT-X\bin\wsjtx.exe",
        r"C:\WSJT-X-improved\bin\wsjtx.exe",
        r"C:\Program Files\WSJT-X-improved\bin\wsjtx.exe",
        "/Applications/wsjtx.app/Contents/MacOS/wsjtx",
        "/Applications/WSJT-X.app/Contents/MacOS/wsjtx",
        os.path.join(home, "Applications/wsjtx.app/Contents/MacOS/wsjtx"),
        "/usr/bin/wsjtx", "/usr/local/bin/wsjtx",
        "/opt/homebrew/bin/wsjtx", "/opt/local/bin/wsjtx",
    ]
    def _etich_mac(exe):
        # da .../Nome.app/Contents/MacOS/wsjtx -> "Nome.app"
        p = exe
        for _ in range(3):
            p = os.path.dirname(p)
        return os.path.basename(p) or "WSJT-X"
    for p in basi:
        if os.path.isfile(p):
            if ".app/Contents/MacOS" in p.replace("\\", "/"):
                _aggiungi(p, _etich_mac(p), "path")
            else:
                _aggiungi(p, os.path.basename(os.path.dirname(os.path.dirname(p))), "path")
    if os.name == "nt":
        for radice in (r"C:\Program Files", r"C:\Program Files (x86)", "C:\\"):
            try:
                for exe in glob.glob(os.path.join(radice, "*WSJT*", "bin", "wsjtx.exe")):
                    _aggiungi(exe, os.path.basename(os.path.dirname(os.path.dirname(exe))), "path")
            except Exception:
                pass
    elif sys.platform == "darwin":
        for radice in ("/Applications", os.path.join(home, "Applications")):
            try:
                for app in glob.glob(os.path.join(radice, "*[Ww][Ss][Jj][Tt]*.app")):
                    exe = os.path.join(app, "Contents", "MacOS", "wsjtx")
                    if os.path.isfile(exe):
                        _aggiungi(exe, os.path.basename(app), "path")
            except Exception:
                pass

    return trovate


def trova_config_dir():
    """Cartella di configurazione WSJT-X (dove stanno i file WSJT-X[.ini]).

    - Windows: %LOCALAPPDATA%\\WSJT-X
    - macOS:   ~/Library/Preferences  (Qt ConfigLocation)
    - Linux:   ~/.config
    Il file di config e' <dir>/WSJT-X.ini (e <dir>/WSJT-X - NOME.ini per i
    profili --rig-name). Si prova a rilevare la cartella che contiene davvero
    WSJT-X.ini, con fallback al default dell'OS."""
    home = os.path.expanduser("~")
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
        return os.path.join(base, "WSJT-X")
    if sys.platform == "darwin":
        cand = [os.path.join(home, "Library", "Preferences"),
                os.path.join(home, "Library", "Application Support", "WSJT-X"),
                os.path.join(home, ".config")]
    else:
        cand = [os.path.join(home, ".config"),
                os.path.join(home, ".config", "WSJT-X")]
    for d in cand:
        if os.path.isfile(os.path.join(d, "WSJT-X.ini")):
            return d
    return cand[0]


def ini_principale(config_dir=None):
    """Percorso della WSJT-X.ini 'normale' (quella che usi con JTAlert)."""
    cd = config_dir or trova_config_dir()
    return os.path.join(cd, "WSJT-X.ini")


def ini_profilo(config_dir=None, profilo=PROFILO):
    """Percorso della ini del profilo dedicato (--rig-name=<profilo>)."""
    cd = config_dir or trova_config_dir()
    return os.path.join(cd, "WSJT-X - %s.ini" % profilo)


def versione_wsjtx(exe):
    """Versione di WSJT-X (best effort via --version). '' se non determinabile."""
    if not exe or not os.path.isfile(exe):
        return ""
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True,
                             timeout=6)
        s = (out.stdout or "") + (out.stderr or "")
        m = re.search(r"(\d+\.\d+(\.\d+)?)", s)
        return m.group(1) if m else s.strip().splitlines()[0][:40] if s.strip() else ""
    except Exception:
        return ""


# =========================================================================== #
#  EDIT INI (per-sezione, senza toccare il resto)
# =========================================================================== #
def set_ini_key(testo, sezione, chiave, valore):
    """Imposta chiave=valore dentro [sezione] del testo .ini (Qt-style).
    Se la sezione o la chiave non esistono le crea. Ritorna il nuovo testo.
    Preserva tutto il resto (commenti, altre sezioni, ordine)."""
    righe = testo.splitlines()
    out = []
    i = 0
    n = len(righe)
    sez_header = "[%s]" % sezione
    in_target = False
    fatto = False
    sez_trovata = False
    while i < n:
        r = righe[i]
        stripped = r.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            # entrando in una nuova sezione: se stavo nella target e non ho
            # ancora scritto la chiave, aggiungila prima di chiudere
            if in_target and not fatto:
                out.append("%s=%s" % (chiave, valore))
                fatto = True
            in_target = (stripped == sez_header)
            if in_target:
                sez_trovata = True
            out.append(r)
            i += 1
            continue
        if in_target and not fatto:
            m = re.match(r"\s*([^=\s]+)\s*=", r)
            if m and m.group(1) == chiave:
                out.append("%s=%s" % (chiave, valore))
                fatto = True
                i += 1
                continue
        out.append(r)
        i += 1
    if in_target and not fatto:
        out.append("%s=%s" % (chiave, valore))
        fatto = True
    if not sez_trovata:
        if out and out[-1].strip() != "":
            out.append("")
        out.append(sez_header)
        out.append("%s=%s" % (chiave, valore))
    return "\n".join(out) + ("\n" if testo.endswith("\n") else "")


def _applica_cat(testo, host, port, mycall="", mygrid=""):
    """Imposta nel testo ini le chiavi per CAT via rigctld NET + PTT CAT + UDP."""
    hp = "%s:%d" % (host, int(port))
    coppie = [
        ("Configuration", "Rig", RIG_NET),
        ("Configuration", "PTTMethod", "CAT"),
        # Chiave di rete: a seconda della versione WSJT-X cambia nome: le
        # scriviamo entrambe, WSJT-X legge quella che usa (l'altra e' innocua).
        ("Configuration", "CATNetworkPort", hp),
        ("Configuration", "CATSerialPort", hp),
        # Reporting -> UDP verso FZR ALERT
        ("Configuration", "UDPServer", UDP_HOST),
        ("Configuration", "UDPServerPort", str(UDP_PORT)),
        ("Configuration", "AcceptUDPRequests", "true"),
    ]
    if mycall:
        coppie.append(("Configuration", "MyCall", mycall))
    if mygrid:
        coppie.append(("Configuration", "MyGrid", mygrid))
    for sez, k, v in coppie:
        testo = set_ini_key(testo, sez, k, v)
    return testo


def crea_profilo(config_dir=None, host=DEF_HOST, port=DEF_PORT,
                 mycall="", mygrid="", profilo=PROFILO):
    """Crea/aggiorna la ini del profilo dedicato clonando la WSJT-X.ini
    esistente e impostando CAT via rigctld. Ritorna (path, clonata_bool).
    Se non esiste una WSJT-X.ini di base, crea una ini minimale."""
    cd = config_dir or trova_config_dir()
    os.makedirs(cd, exist_ok=True)
    src = ini_principale(cd)
    dst = ini_profilo(cd, profilo)
    clonata = False
    if os.path.isfile(src):
        try:
            with open(src, "r", encoding="utf-8", errors="replace") as f:
                testo = f.read()
            clonata = True
        except Exception:
            testo = ""
    else:
        testo = ""
    if not testo.strip():
        testo = "[Configuration]\n"
    testo = _applica_cat(testo, host, port, mycall, mygrid)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(testo)
    return dst, clonata


def avvia_wsjtx(exe, profilo=PROFILO):
    """Avvia WSJT-X col profilo dedicato (--rig-name). Ritorna il processo."""
    if not exe or not os.path.isfile(exe):
        raise FileNotFoundError("wsjtx.exe non trovato")
    cmd = [exe, "--rig-name=%s" % profilo]
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008  # DETACHED_PROCESS
    return subprocess.Popen(cmd, cwd=os.path.dirname(exe) or None, **kw)


# =========================================================================== #
#  GUI
# =========================================================================== #
def apri_wsjtx_integra(parent, app=None):
    """Finestra per creare il profilo dedicato e avviare WSJT-X con CAT
    condiviso via rigctld di ADIF FZR."""
    import customtkinter as ctk
    from tkinter import messagebox, filedialog

    # Endpoint rigctld dal backend Hamlib dell'app (se disponibile)
    host, port = DEF_HOST, DEF_PORT
    hl = getattr(app, "_hamlib", None)
    if hl is not None:
        host = getattr(hl, "host", host) or host
        try:
            port = int(getattr(hl, "port", port) or port)
        except Exception:
            port = DEF_PORT
    # Nominativo / locatore dai campi stazione
    mycall = mygrid = ""
    try:
        mycall = app.entry_owner.get().strip().upper()
    except Exception:
        pass
    try:
        g = app.entry_details.get().strip()
        mygrid = g.split()[0].upper() if g else ""
    except Exception:
        pass

    config_dir = trova_config_dir()
    var_exe = ctk.StringVar(value=trova_wsjtx_exe() or "")

    win = ctk.CTkToplevel(parent)
    win.title("Integrazione WSJT-X — profilo ADIF FZR")
    win.geometry("720x560")
    win.minsize(640, 480)
    win.grab_set(); win.lift(); win.focus_force()

    ctk.CTkLabel(win, text="📡 WSJT-X con il rig control di ADIF FZR",
                 font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(12, 2))
    ctk.CTkLabel(win, text="ADIF FZR tiene la radio (rigctld); WSJT-X si collega "
                           "allo stesso rigctld come 'Hamlib NET rigctl'.\n"
                           "Si crea un profilo dedicato: la tua config con JTAlert "
                           "resta intatta.",
                 font=ctk.CTkFont(size=11), text_color="#9fb6d4",
                 justify="left").pack(padx=16, pady=(0, 6))

    # Fondo fisso (Chiudi) impacchettato prima del contenuto
    bottom = ctk.CTkFrame(win, fg_color="transparent")
    bottom.pack(side="bottom", fill="x")
    ctk.CTkButton(bottom, text="Chiudi", command=win.destroy,
                  fg_color="#718096", width=100).pack(pady=(4, 10))

    body = ctk.CTkScrollableFrame(win, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=14, pady=6)

    def _card(titolo):
        c = ctk.CTkFrame(body, corner_radius=10, fg_color="#0f1b2d",
                         border_width=1, border_color="#223b55")
        c.pack(fill="x", pady=6)
        ctk.CTkLabel(c, text=titolo, font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#8fc0ff").pack(anchor="w", padx=12, pady=(8, 2))
        return c

    # --- Rilevamento ---
    c1 = _card("1 · Rilevamento WSJT-X")

    # Mappa label -> exe di tutte le installazioni trovate
    _mappa = {}        # label visibile -> percorso exe
    def _etichetta(inst):
        return "%s   —   %s" % (inst["label"], inst["exe"])

    riga0 = ctk.CTkFrame(c1, fg_color="transparent"); riga0.pack(fill="x", padx=12, pady=(2, 2))
    ctk.CTkLabel(riga0, text="Installazioni:", width=90, anchor="w").pack(side="left")
    var_sel = ctk.StringVar(value="")
    combo = ctk.CTkOptionMenu(riga0, variable=var_sel, values=["(nessuna)"],
                              dynamic_resizing=False, width=460,
                              command=lambda _=None: var_exe.set(_mappa.get(var_sel.get(), var_exe.get())))
    combo.pack(side="left", fill="x", expand=True, padx=4)

    def _ricarica(preseleziona=None):
        insts = trova_installazioni()
        _mappa.clear()
        vals = []
        for it in insts:
            et = _etichetta(it)
            _mappa[et] = it["exe"]
            vals.append(et)
        if not vals:
            combo.configure(values=["(nessuna trovata — usa Sfoglia)"])
            var_sel.set("(nessuna trovata — usa Sfoglia)")
        else:
            combo.configure(values=vals)
            # preseleziona: il percorso richiesto, o quello gia' nel campo, o il primo
            target = preseleziona or var_exe.get().strip()
            scelto = None
            if target:
                for et, ex in _mappa.items():
                    if _norm(ex) == _norm(target):
                        scelto = et; break
            scelto = scelto or vals[0]
            var_sel.set(scelto)
            var_exe.set(_mappa[scelto])
        lbl_trov.configure(text="Trovate %d installazioni." % len(_mappa) if _mappa
                           else "Nessuna installazione rilevata automaticamente.")

    ctk.CTkButton(riga0, text="↻", width=34, command=lambda: _ricarica()).pack(side="left")

    riga = ctk.CTkFrame(c1, fg_color="transparent"); riga.pack(fill="x", padx=12, pady=2)
    ctk.CTkLabel(riga, text="Eseguibile:", width=90, anchor="w").pack(side="left")
    e_exe = ctk.CTkEntry(riga, textvariable=var_exe)
    e_exe.pack(side="left", fill="x", expand=True, padx=4)

    def _sfoglia():
        p = filedialog.askopenfilename(parent=win, title="Seleziona wsjtx.exe",
                                       filetypes=[("wsjtx", "wsjtx.exe"), ("Tutti", "*.*")])
        if p:
            var_exe.set(p)
            # aggiungi la scelta manuale alla tendina e selezionala
            et = "Manuale   —   %s" % p
            _mappa[et] = p
            vals = list(combo.cget("values"))
            if et not in vals:
                vals = [v for v in vals if not v.startswith("(nessuna")] + [et]
                combo.configure(values=vals)
            var_sel.set(et)
    ctk.CTkButton(riga, text="Sfoglia", width=70, command=_sfoglia).pack(side="left")

    lbl_trov = ctk.CTkLabel(c1, text="", font=ctk.CTkFont(size=10), text_color="#9fb6d4")
    lbl_trov.pack(anchor="w", padx=12, pady=(0, 2))

    riga2 = ctk.CTkFrame(c1, fg_color="transparent"); riga2.pack(fill="x", padx=12, pady=(0, 2))

    def _salva_cfg():
        exe = var_exe.get().strip()
        if exe and not os.path.isfile(exe):
            messagebox.showwarning("WSJT-X", "Il percorso indicato non esiste.", parent=win)
            return
        ok = salva_cfg({"exe": exe, "host": host, "port": port})
        lbl_cfg.configure(text=("Configurazione salvata in:\n%s" % cfg_path()) if ok
                          else "Impossibile salvare la configurazione.")
    ctk.CTkButton(riga2, text="💾 Salva configurazione", command=_salva_cfg,
                  fg_color="#2B6CB0", width=180).pack(side="left")
    ctk.CTkLabel(riga2, text="(ricorda il percorso di wsjtx.exe per l'avvio rapido)",
                 font=ctk.CTkFont(size=10), text_color="#9fb6d4").pack(side="left", padx=8)

    lbl_cfg = ctk.CTkLabel(c1, text="", font=ctk.CTkFont(size=11),
                           text_color="#cdd9ea", justify="left")
    lbl_cfg.pack(anchor="w", padx=12, pady=(2, 10))
    src = ini_principale(config_dir)
    lbl_cfg.configure(text="Config: %s\nWSJT-X.ini di base: %s"
                      % (config_dir, "trovata" if os.path.isfile(src) else "NON trovata (verra' creata minimale)"))

    # Popola la tendina con tutte le installazioni trovate
    _ricarica(var_exe.get())

    # --- Radio ---
    c2 = _card("2 · Controllo radio (condiviso)")
    be = "?"
    try:
        be = getattr(app, "cat_backend", None) or getattr(app, "_cat_backend", None) or ""
    except Exception:
        be = ""
    testo_radio = ("WSJT-X usera': Hamlib NET rigctl  →  %s:%d\nPTT: CAT (via rigctld)\n"
                   "Report UDP: %s:%d (FZR ALERT)" % (host, port, UDP_HOST, UDP_PORT))
    ctk.CTkLabel(c2, text=testo_radio, font=ctk.CTkFont(size=11),
                 text_color="#cdd9ea", justify="left").pack(anchor="w", padx=12, pady=(2, 2))
    ctk.CTkLabel(c2, text="NB: in ADIF FZR imposta il backend CAT su Hamlib e avvia "
                          "rigctld (Impostazioni → Controllo radio), altrimenti WSJT-X "
                          "non trova la radio.",
                 font=ctk.CTkFont(size=10), text_color="#e0a53a",
                 justify="left", wraplength=640).pack(anchor="w", padx=12, pady=(0, 10))

    # --- Azioni ---
    c3 = _card("3 · Profilo dedicato e avvio")
    stato = ctk.CTkLabel(c3, text="", font=ctk.CTkFont(size=11),
                         text_color="#8fc0ff", justify="left", wraplength=660)
    stato.pack(anchor="w", padx=12, pady=(2, 4))

    def _crea():
        try:
            dst, clon = crea_profilo(config_dir=config_dir, host=host, port=port,
                                     mycall=mycall, mygrid=mygrid)
        except Exception as ex:
            messagebox.showerror("WSJT-X", "Errore creando il profilo:\n%s" % ex, parent=win)
            return
        stato.configure(text=("Profilo creato: %s\n%s\nOra premi 'Avvia WSJT-X'."
                              % (os.path.basename(dst),
                                 "(clonato dalla tua WSJT-X.ini)" if clon else
                                 "(creata config minimale)")))

    def _avvia():
        exe = var_exe.get().strip()
        if not exe or not os.path.isfile(exe):
            messagebox.showwarning("WSJT-X", "Eseguibile WSJT-X non valido. Usa 'Sfoglia'.",
                                   parent=win)
            return
        # crea/aggiorna il profilo prima di avviare
        try:
            crea_profilo(config_dir=config_dir, host=host, port=port,
                         mycall=mycall, mygrid=mygrid)
            salva_cfg({"exe": exe, "host": host, "port": port})
            avvia_wsjtx(exe, PROFILO)
            stato.configure(text="WSJT-X avviato con profilo '%s'.\n"
                                 "Percorso memorizzato per l'avvio rapido." % PROFILO)
        except Exception as ex:
            messagebox.showerror("WSJT-X", "Errore nell'avvio:\n%s" % ex, parent=win)

    br = ctk.CTkFrame(c3, fg_color="transparent"); br.pack(fill="x", padx=12, pady=(0, 10))
    ctk.CTkButton(br, text="Crea / aggiorna profilo", command=_crea,
                  fg_color="#2B6CB0").pack(side="left", padx=(0, 8))
    ctk.CTkButton(br, text="▶ Avvia WSJT-X (profilo ADIF FZR)", command=_avvia,
                  fg_color="#1f9d57", hover_color="#17a74a").pack(side="left")

    # --- Checklist ---
    c4 = _card("Valori impostati (verifica in WSJT-X → Impostazioni → Radio)")
    ck = ("Rig:  Hamlib NET rigctl\n"
          "Network Server:  %s:%d\n"
          "PTT Method:  CAT\n"
          "Reporting → UDP Server:  %s   Port:  %d   (Accept UDP requests: ON)"
          % (host, port, UDP_HOST, UDP_PORT))
    ctk.CTkLabel(c4, text=ck, font=ctk.CTkFont(size=11), text_color="#cdd9ea",
                 justify="left").pack(anchor="w", padx=12, pady=(2, 10))


def lancia(app=None):
    """Crea/aggiorna il profilo dedicato e avvia WSJT-X (--rig-name=ADIFFZR).
    Legge host/port del rigctld e call/locatore dall'app se passata.
    Ritorna (ok: bool, messaggio: str)."""
    exe = trova_wsjtx_exe()
    if not exe:
        return (False, "wsjtx.exe non trovato. Apri 'WSJT-X (profilo ADIF FZR)' "
                       "dal menu e usa 'Sfoglia' per indicarlo.")
    host, port = DEF_HOST, DEF_PORT
    hl = getattr(app, "_hamlib", None)
    if hl is not None:
        host = getattr(hl, "host", host) or host
        try:
            port = int(getattr(hl, "port", port) or port)
        except Exception:
            port = DEF_PORT
    mycall = mygrid = ""
    try:
        mycall = app.entry_owner.get().strip().upper()
    except Exception:
        pass
    try:
        g = app.entry_details.get().strip()
        mygrid = g.split()[0].upper() if g else ""
    except Exception:
        pass
    try:
        crea_profilo(host=host, port=port, mycall=mycall, mygrid=mygrid)
        avvia_wsjtx(exe, PROFILO)
    except Exception as ex:
        return (False, "Errore nell'avvio di WSJT-X:\n%s" % ex)
    return (True, "WSJT-X avviato con profilo '%s'." % PROFILO)
