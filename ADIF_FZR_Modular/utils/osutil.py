# -*- coding: utf-8 -*-
"""Utility multipiattaforma per aprire file/cartelle con l'app predefinita.

Su Windows usa os.startfile; su macOS il comando `open`; altrove `xdg-open`.
Evita il crash che avrebbe os.startfile fuori da Windows (non esiste)."""
import os
import sys
import subprocess


def apri_path(path):
    """Apre `path` (file o cartella) con l'applicazione predefinita dell'OS.
    Ritorna True se il comando e' stato lanciato, False in caso di errore."""
    if not path:
        return False
    try:
        if os.name == "nt":
            os.startfile(os.path.abspath(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False
