# -*- coding: utf-8 -*-
"""
propagazione.py — dati di propagazione solare da HamQSL (N0NBH).

Fonte: https://www.hamqsl.com/solarxml.php  (XML pubblico, aggiornato ~ogni ora).
Nessuna dipendenza esterna: urllib + xml.etree della stdlib.

Uso tipico:
    d = scarica_propagazione()          # dict, o None se offline/errore
    d['sfi'], d['kindex'], d['geomag'], d['bande']['80m-40m']['day'] ...
"""

import urllib.request
import xml.etree.ElementTree as ET

URL_HAMQSL = "https://www.hamqsl.com/solarxml.php"


def _txt(el):
    return (el.text or "").strip() if el is not None else ""


def parse_propagazione(xml_bytes):
    """Converte l'XML HamQSL in un dizionario. Ritorna None se non valido."""
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return None
    sd = root.find("solardata")
    if sd is None:
        return None

    def g(tag):
        return _txt(sd.find(tag))

    d = {
        "updated":   g("updated"),
        "sfi":       g("solarflux"),
        "sn":        g("sunspots"),
        "aindex":    g("aindex"),
        "kindex":    g("kindex"),
        "xray":      g("xray"),
        "aurora":    g("aurora"),
        "solarwind": g("solarwind"),
        "geomag":    g("geomagfield"),
        "muf":       g("muf"),
        "signalnoise": g("signalnoise"),
        "bande": {},        # {"80m-40m": {"day": "...", "night": "..."}, ...}
        "vhf": {},          # {"E-Skip europe": "...", ...}
    }

    cc = sd.find("calculatedconditions")
    if cc is not None:
        for b in cc.findall("band"):
            nome = (b.get("name") or "").strip()
            tempo = (b.get("time") or "").strip().lower()
            val = _txt(b)
            if nome and tempo:
                d["bande"].setdefault(nome, {})[tempo] = val

    vc = sd.find("calculatedvhfconditions")
    if vc is not None:
        for p in vc.findall("phenomenon"):
            nome = (p.get("name") or "").strip()
            loc = (p.get("location") or "").strip()
            chiave = (nome + " " + loc).strip()
            if chiave:
                d["vhf"][chiave] = _txt(p)

    return d


def scarica_propagazione(timeout=8):
    """Scarica e interpreta i dati HamQSL. Ritorna dict o None (offline/errore)."""
    try:
        req = urllib.request.Request(
            URL_HAMQSL,
            headers={"User-Agent": "ADIF-FZR (+https://iw1fzr.it)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
        return parse_propagazione(raw)
    except Exception:
        return None


# Colori indicativi per lo stato banda (Good/Fair/Poor)
def colore_condizione(valore):
    v = (valore or "").strip().lower()
    if v.startswith("good"):
        return "#48BB78"   # verde
    if v.startswith("fair"):
        return "#F6C177"   # ambra
    if v.startswith("poor"):
        return "#E06C6C"   # rosso
    return "#8fa2c0"       # neutro


def colore_kindex(kindex):
    """K basso = quiete (verde), alto = tempesta (rosso)."""
    try:
        k = float(str(kindex).strip())
    except Exception:
        return "#8fa2c0"
    if k <= 2:
        return "#48BB78"
    if k <= 4:
        return "#F6C177"
    return "#E06C6C"


if __name__ == "__main__":
    import sys
    d = scarica_propagazione()
    print(d if d else "offline / errore")
