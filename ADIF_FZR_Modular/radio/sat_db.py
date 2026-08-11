# -*- coding: utf-8 -*-
"""
Database satelliti per ADIF FZR — frequenze e modi per il logging
=================================================================
Per ogni satellite radioamatoriale noto: banda/frequenza di UPLINK (TX),
banda/frequenza di DOWNLINK (RX) e SAT_MODE (coppia lettere banda, es. V/U).
Serve al form "Aggiungi QSO" per auto-compilare la tratta RX e SAT_MODE
quando scegli un satellite, e al ponte dal cruscotto di tracking.

Le frequenze sono i valori standard pubblicati (centro transponder per i
lineari, canale per gli FM). Lo stato dei satelliti cambia nel tempo
(bird spenti/riattivati, transponder commutati): verifica e aggiorna
questa tabella secondo lo stato AMSAT corrente quando serve.

Convenzione lettere banda (SAT_MODE = uplink/downlink):
    H = HF/10m    V = 2m      U = 70cm     L = 23cm
    S = 13cm      C = 6cm     X = 3cm
"""

import re

# Frequenze in MHz (stringa, così vanno dritte nei campi del form).
# up_band / dn_band usano i nomi banda ADIF già usati dall'app.
SAT_DB = {
    # ── FM (voce) ────────────────────────────────────────────────
    "SO-50":   {"up_band": "2m",   "up_freq": "145.850",  "dn_band": "70cm", "dn_freq": "436.795",   "mode": "V/U", "tipo": "FM"},
    "AO-91":   {"up_band": "70cm", "up_freq": "435.250",  "dn_band": "2m",   "dn_freq": "145.960",   "mode": "U/V", "tipo": "FM"},
    "PO-101":  {"up_band": "70cm", "up_freq": "437.500",  "dn_band": "2m",   "dn_freq": "145.900",   "mode": "U/V", "tipo": "FM"},
    "ISS":     {"up_band": "2m",   "up_freq": "145.990",  "dn_band": "70cm", "dn_freq": "437.800",   "mode": "V/U", "tipo": "FM"},

    # ── Lineari (SSB/CW) ─────────────────────────────────────────
    "RS-44":   {"up_band": "2m",   "up_freq": "145.965",  "dn_band": "70cm", "dn_freq": "435.640",   "mode": "V/U", "tipo": "Lineare"},
    "FO-29":   {"up_band": "2m",   "up_freq": "145.950",  "dn_band": "70cm", "dn_freq": "435.850",   "mode": "V/U", "tipo": "Lineare"},
    "CAS-4A":  {"up_band": "70cm", "up_freq": "435.220",  "dn_band": "2m",   "dn_freq": "145.855",   "mode": "U/V", "tipo": "Lineare"},
    "CAS-4B":  {"up_band": "70cm", "up_freq": "435.280",  "dn_band": "2m",   "dn_freq": "145.915",   "mode": "U/V", "tipo": "Lineare"},
    "JO-97":   {"up_band": "70cm", "up_freq": "435.100",  "dn_band": "2m",   "dn_freq": "145.855",   "mode": "U/V", "tipo": "Lineare"},
    "AO-7":    {"up_band": "70cm", "up_freq": "432.150",  "dn_band": "2m",   "dn_freq": "145.950",   "mode": "U/V", "tipo": "Lineare"},  # Mode B

    # ── Geostazionario lineare ───────────────────────────────────
    "QO-100":  {"up_band": "13cm", "up_freq": "2400.175", "dn_band": "3cm",  "dn_freq": "10489.675", "mode": "S/X", "tipo": "Lineare"},
}

# Alias -> nome canonico in SAT_DB. Gestisce grafie diverse e nomi TLE
# (es. "ISS (ZARYA)"). Le varianti QO-100 sono gestite anche via regex sotto.
_ALIAS = {
    "ESHAIL-2": "QO-100", "ES-HAIL-2": "QO-100", "ESHAIL2": "QO-100",
    "ISS(ZARYA)": "ISS", "ZARYA": "ISS", "ARISS": "ISS",
    "RADFXSAT": "AO-91", "FOX-1B": "AO-91",
    "JY1SAT": "JO-97",
    "AO7": "AO-7", "AO-07": "AO-7",
}

_QO100_RE = re.compile(
    r"^\s*(QO[\s\-]?100|ES['`]?HAIL[\s\-]?2A?|ESHAILSAT[\s\-]?2)\s*(\(.*\))?\s*$",
    re.I,
)


def _compatta(nome):
    """Toglie spazi, trattini e parentesi: 'ISS (ZARYA)' -> 'ISS(ZARYA)' senza spazi,
    'rs 44' -> 'RS44'. Usato per il matching tollerante."""
    n = str(nome).strip().upper()
    return re.sub(r"[\s\-]", "", n)


def normalizza(nome):
    """Restituisce il nome canonico del satellite (chiave di SAT_DB) partendo
    da una grafia qualsiasi, o None se non riconosciuto.
    Gestisce i nomi TLE completi ovunque compaia il designatore, anche
    tra parentesi:
      'rs44'                 -> 'RS-44'
      'iss (zarya)'          -> 'ISS'
      'eshail-2'             -> 'QO-100'
      'RS-44 & BREEZE-KM R/B'-> 'RS-44'
      'OSCAR 7 (AO-7)'       -> 'AO-7'
      'AO-91 (RADFXSAT)'     -> 'AO-91'
      'CAS-4A (ZHUHAI-1 01)' -> 'CAS-4A'"""
    if not nome:
        return None
    raw = str(nome).strip()
    if _QO100_RE.match(raw):
        return "QO-100"

    def _match(tok):
        cc = _compatta(tok)
        if not cc:
            return None
        for chiave in SAT_DB:
            if _compatta(chiave) == cc:
                return chiave
        return _ALIAS.get(cc)

    # 1) match diretto sull'intera stringa (nomi già puliti: SO-50, QO-100…)
    r = _match(raw)
    if r:
        return r

    # 2) Raccoglie i candidati da tutto il nome TLE e prova ciascuno:
    #    contenuto tra parentesi, token "designatore" (lettere+cifre),
    #    e tutti i token separati da spazi/&//.
    candidati = []
    candidati += re.findall(r"\(([^)]+)\)", raw)                 # dentro ( )
    candidati += re.findall(r"[A-Za-z]{1,5}-?\d{1,3}[A-Za-z]?", raw)  # es. AO-7, CAS-4A
    candidati += re.split(r"[^A-Za-z0-9\-]+", raw)               # token generici
    for c in candidati:
        r = _match(c)
        if r:
            return r
    return None


def info(nome):
    """Restituisce il dict con up/down/mode/tipo per il satellite, o None.
    Accetta grafie diverse (usa normalizza())."""
    canon = normalizza(nome)
    if not canon:
        return None
    d = dict(SAT_DB[canon])
    d["nome"] = canon
    return d


def banda_uplink(nome):
    """Banda ADIF di uplink (TX) per compatibilità con la vecchia logica.
    Vuoto se il satellite non è noto."""
    d = info(nome)
    return d["up_band"] if d else ""


def nomi_noti():
    """Elenco dei nomi canonici in database (per menu/autocomplete)."""
    return sorted(SAT_DB.keys())
