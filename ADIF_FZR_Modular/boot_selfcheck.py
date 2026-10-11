#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
boot_selfcheck.py — verifica di avvio cross-platform per ADIF FZR.

Importa TUTTI i moduli del pacchetto (senza aprire la GUI) e chiama le
funzioni "a rischio" su piattaforme diverse (percorsi WSJT-X, apertura file).
Serve a collaudare la build su macOS/Linux in CI, SENZA un Mac e senza
interfaccia grafica: se un modulo non si importa o una funzione esplode su
quella piattaforma, lo script esce con codice 1 e la GitHub Action fallisce.

Uso:  cd ADIF_FZR_Modular && python boot_selfcheck.py
"""
import os
import sys
import importlib
import pkgutil
import traceback
import platform

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Non importare l'entrypoint: main.py avvia la GUI (mainloop).
SKIP_BASENAMI = {"main", "boot_selfcheck"}


def _tutti_i_moduli():
    mods = ["config"]
    for pkg in ("gui", "net", "radio", "utils"):
        pkgpath = os.path.join(HERE, pkg)
        if not os.path.isdir(pkgpath):
            continue
        # importa il package e poi cammina i sottomoduli
        mods.append(pkg)
        try:
            for mi in pkgutil.walk_packages([pkgpath], prefix=pkg + "."):
                mods.append(mi.name)
        except Exception:
            traceback.print_exc()
    # dedup mantenendo l'ordine
    visti, out = set(), []
    for m in mods:
        if m not in visti:
            visti.add(m); out.append(m)
    return out


def main():
    print("== ADIF FZR — boot self-check ==")
    print("Python %s su %s %s" % (platform.python_version(),
                                  platform.system(), platform.machine()))
    try:
        import config
        print("Versione app:", getattr(config, "VERSIONE", "?"))
    except Exception:
        traceback.print_exc()

    falliti = []

    # 1) Import di tutti i moduli del pacchetto
    for name in _tutti_i_moduli():
        if name.split(".")[-1] in SKIP_BASENAMI:
            continue
        try:
            importlib.import_module(name)
        except Exception:
            falliti.append(name)
            print("\n[IMPORT FALLITO] %s" % name)
            traceback.print_exc()

    # 2) Funzioni a rischio cross-platform (non-GUI)
    try:
        from net import wsjtx_integra as w
        print("WSJT-X config dir:", w.trova_config_dir())
        print("WSJT-X eseguibile:", w.trova_wsjtx_exe())
        print("WSJT-X ini profilo:", w.ini_profilo())
        w.trova_installazioni()
        w.carica_cfg()
    except Exception:
        falliti.append("net.wsjtx_integra (funzioni)")
        traceback.print_exc()

    try:
        from utils.osutil import apri_path
        # path vuoto -> False, nessun crash e nessuna finestra aperta
        assert apri_path("") is False
        print("utils.osutil.apri_path: OK")
    except Exception:
        falliti.append("utils.osutil.apri_path")
        traceback.print_exc()

    # 3) Tk headless: non fa fallire il job se manca il display (atteso in CI)
    try:
        import tkinter as tk
        r = tk.Tk(); r.withdraw(); r.update(); r.destroy()
        print("Tk: finestra creata e distrutta OK")
    except Exception as e:
        print("Tk headless non disponibile (normale in CI):", str(e)[:140])

    if falliti:
        print("\nRISULTATO: FALLITO")
        for f in falliti:
            print("  - " + f)
        return 1
    print("\nRISULTATO: OK — moduli importati e funzioni cross-platform senza crash")
    return 0


if __name__ == "__main__":
    sys.exit(main())
