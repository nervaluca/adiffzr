# -*- coding: utf-8 -*-
"""
Modulo satellitare per ADIF FZR
================================
Predizione passaggi dei satelliti radioamatoriali (LEO) e utilita' orbitali,
basato su skyfield (SGP4). Le TLE vengono scaricate da Celestrak e messe in
cache locale, cosi' l'app funziona anche offline con l'ultimo set scaricato.

Dipendenze:  pip install skyfield
"""

import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    from skyfield.api import load, wgs84, EarthSatellite
    from skyfield.timelib import Timescale
    SKYFIELD_OK = True
except Exception:
    SKYFIELD_OK = False


# ── Satelliti radioamatoriali piu' usati (nome mostrato -> nome nella TLE Celestrak) ──
# Il download prende l'intero gruppo "amateur", qui teniamo un elenco "preferiti"
# per proporli in cima e per il logging.
SAT_PREFERITI = [
    "ISS (ZARYA)", "SO-50", "AO-91", "PO-101", "RS-44",
    "CAS-4A", "CAS-4B", "FO-29", "JO-97", "MESAT-1",
    "TEVEL-1", "TEVEL-2", "TEVEL-3", "TEVEL-4",
    "TEVEL-5", "TEVEL-6", "TEVEL-7", "TEVEL-8",
]

# URL Celestrak: gruppo satelliti amatoriali, formato TLE
TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=amateur&FORMAT=tle"
# Fonte alternativa (mirror AMSAT) in caso Celestrak non risponda
TLE_URL_ALT = "https://www.amsat.org/tle/current/nasabare.txt"


def _cache_path(cache_dir):
    return os.path.join(cache_dir, "tle_amateur.txt")


def scarica_tle(cache_dir, max_age_ore=6, forza=False):
    """
    Restituisce il percorso del file TLE in cache, scaricandolo se assente,
    piu' vecchio di 'max_age_ore', o se forza=True.
    Ritorna (path, aggiornato, messaggio).
    """
    os.makedirs(cache_dir, exist_ok=True)
    path = _cache_path(cache_dir)

    fresco = False
    if os.path.exists(path) and not forza:
        eta_ore = (time.time() - os.path.getmtime(path)) / 3600.0
        if eta_ore < max_age_ore:
            fresco = True

    if fresco:
        return path, False, "TLE in cache (aggiornate)"

    ultimo_errore = None
    for url in (TLE_URL, TLE_URL_ALT):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ADIF-FZR/2.4"})
            with urllib.request.urlopen(req, timeout=15) as r:
                dati = r.read().decode("utf-8", "replace")
            if dati and "\n" in dati and len(dati) > 100:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(dati)
                return path, True, "TLE scaricate da " + url.split("/")[2]
        except Exception as e:
            ultimo_errore = str(e)

    # download fallito: se ho una vecchia cache la uso comunque
    if os.path.exists(path):
        return path, False, "Download fallito, uso TLE vecchie in cache"
    return None, False, "Impossibile scaricare le TLE: " + (ultimo_errore or "rete assente")


def carica_satelliti(tle_path):
    """Carica gli oggetti EarthSatellite dal file TLE. Ritorna dict {nome: sat}."""
    if not SKYFIELD_OK or not tle_path or not os.path.exists(tle_path):
        return {}
    ts = load.timescale()
    sats = {}
    try:
        with open(tle_path, "r", encoding="utf-8", errors="replace") as f:
            righe = [x.rstrip("\n") for x in f if x.strip()]
        i = 0
        while i + 2 < len(righe) + 1:
            if i + 2 >= len(righe):
                break
            nome = righe[i].strip()
            l1 = righe[i + 1].strip()
            l2 = righe[i + 2].strip()
            if l1.startswith("1 ") and l2.startswith("2 "):
                try:
                    sats[nome] = EarthSatellite(l1, l2, nome, ts)
                except Exception:
                    pass
                i += 3
            else:
                i += 1
    except Exception:
        return sats
    return sats


def _manuali_path(cache_dir):
    return os.path.join(cache_dir, "tle_manuali.txt")


def eta_cache_ore(cache_dir):
    """Ore trascorse dall'ultimo aggiornamento della cache TLE Celestrak,
    o None se il file non esiste."""
    p = _cache_path(cache_dir)
    if not os.path.exists(p):
        return None
    return (time.time() - os.path.getmtime(p)) / 3600.0


def salva_tle_manuale(cache_dir, nome, l1, l2):
    """Valida e salva un TLE inserito a mano in tle_manuali.txt (persistente,
    non toccato dal refresh automatico). Ritorna (ok, messaggio)."""
    nome = (nome or "").strip()
    l1 = (l1 or "").strip()
    l2 = (l2 or "").strip()
    if not nome:
        return False, "Nome satellite mancante."
    if not (l1.startswith("1 ") and l2.startswith("2 ")):
        return False, "Le due righe elementi devono iniziare con '1 ' e '2 ' (formato TLE)."
    if SKYFIELD_OK:
        try:
            ts = load.timescale()
            EarthSatellite(l1, l2, nome, ts)
        except Exception as e:
            return False, "TLE non valido: " + str(e)
    os.makedirs(cache_dir, exist_ok=True)
    path = _manuali_path(cache_dir)
    blocchi = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            righe = [x.rstrip("\n") for x in f if x.strip()]
        for i in range(0, len(righe) - 2, 3):
            if righe[i].strip().upper() != nome.upper():
                blocchi.append((righe[i].strip(), righe[i + 1].strip(), righe[i + 2].strip()))
    blocchi.append((nome, l1, l2))
    with open(path, "w", encoding="utf-8") as f:
        for n, a, b in blocchi:
            f.write(n + "\n" + a + "\n" + b + "\n")
    return True, "TLE salvato per " + nome


def carica_satelliti_e_manuali(cache_dir, path_celestrak):
    """Carica i satelliti Celestrak + quelli manuali, uniti (i manuali hanno
    priorita' in caso di stesso nome)."""
    sats = carica_satelliti(path_celestrak) if path_celestrak else {}
    manuali = carica_satelliti(_manuali_path(cache_dir))
    sats.update(manuali)
    return sats


def prossimi_passaggi(sats, lat, lon, elev_m=0.0, ore=24, elev_min=10.0,
                      solo=None, max_passaggi=200):
    """
    Calcola i passaggi visibili nelle prossime 'ore'.

    sats     : dict {nome: EarthSatellite} (da carica_satelliti)
    lat, lon : coordinate osservatore in gradi
    elev_m   : altitudine osservatore in metri
    elev_min : elevazione minima (gradi) perche' il passaggio conti
    solo     : lista/set di nomi da considerare (None = tutti)

    Ritorna lista di dict ordinata per orario AOS:
      {sat, aos, max, los, durata_min, el_max, az_aos, az_max, az_los}
    con datetime in UTC (timezone-aware).
    """
    if not SKYFIELD_OK or not sats:
        return []

    ts = load.timescale()
    osservatore = wgs84.latlon(lat, lon, elevation_m=elev_m)
    ora = datetime.now(timezone.utc)
    t0 = ts.from_datetime(ora)
    t1 = ts.from_datetime(ora + timedelta(hours=ore))

    risultati = []
    nomi = sats.keys() if solo is None else [n for n in sats.keys() if n in solo]

    for nome in nomi:
        sat = sats[nome]
        try:
            t, eventi = sat.find_events(osservatore, t0, t1, altitude_degrees=elev_min)
        except Exception:
            continue
        diff = sat - osservatore

        aos = maxt = los = None
        az_aos = az_max = az_los = el_max = None
        for ti, ev in zip(t, eventi):
            alt, az, _ = diff.at(ti).altaz()
            if ev == 0:                      # rise
                aos = ti.utc_datetime()
                az_aos = az.degrees
                maxt = los = None
            elif ev == 1:                    # culminate
                maxt = ti.utc_datetime()
                el_max = alt.degrees
                az_max = az.degrees
            elif ev == 2:                    # set
                los = ti.utc_datetime()
                az_los = az.degrees
                if aos and los:
                    durata = (los - aos).total_seconds() / 60.0
                    risultati.append({
                        "sat": nome,
                        "aos": aos, "max": maxt, "los": los,
                        "durata_min": round(durata, 1),
                        "el_max": round(el_max, 1) if el_max is not None else None,
                        "az_aos": round(az_aos, 1) if az_aos is not None else None,
                        "az_max": round(az_max, 1) if az_max is not None else None,
                        "az_los": round(az_los, 1) if az_los is not None else None,
                    })
                aos = maxt = los = None

    risultati.sort(key=lambda p: p["aos"])
    return risultati[:max_passaggi]


def posizione_attuale(sat, lat, lon, elev_m=0.0):
    """Posizione istantanea di un satellite vista dall'osservatore: (el, az, dist_km).
    Ritorna None se sotto l'orizzonte o errore."""
    if not SKYFIELD_OK:
        return None
    try:
        ts = load.timescale()
        osservatore = wgs84.latlon(lat, lon, elevation_m=elev_m)
        alt, az, dist = (sat - osservatore).at(ts.now()).altaz()
        return (round(alt.degrees, 1), round(az.degrees, 1), round(dist.km, 0))
    except Exception:
        return None


def punto_cardinale(azimut):
    """Converte un azimut in gradi nel punto cardinale (N, NE, E...)."""
    if azimut is None:
        return ""
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((azimut % 360) / 22.5 + 0.5) % 16]


# ══════════════════════════════════════════════════════════════════
#  FOOTPRINT e TRACCIA (per la mappa animata)
# ══════════════════════════════════════════════════════════════════
import math as _math

R_TERRA_KM = 6371.0


def subpoint(sat, quando_dt):
    """Punto a terra sotto il satellite (sub-satellite point) a un dato istante.
    quando_dt: datetime UTC aware. Ritorna (lat, lon, alt_km) o None."""
    if not SKYFIELD_OK:
        return None
    try:
        ts = load.timescale()
        t = ts.from_datetime(quando_dt)
        geo = sat.at(t)
        sp = wgs84.subpoint(geo)
        return (sp.latitude.degrees, sp.longitude.degrees, sp.elevation.km)
    except Exception:
        return None


def raggio_footprint_km(alt_km):
    """Raggio dell'impronta a terra (km) dato l'altitudine del satellite."""
    try:
        alpha = _math.acos(R_TERRA_KM / (R_TERRA_KM + float(alt_km)))
        return _math.radians(_math.degrees(alpha)) * R_TERRA_KM  # = alpha_rad * R
    except Exception:
        return 0.0


def cerchio_footprint(lat0, lon0, raggio_km, punti=90):
    """Restituisce i punti (lat, lon) del cerchio di footprint attorno al
    sub-satellite point, tenendo conto della curvatura terrestre.
    Utile per disegnare l'impronta sulla mappa."""
    pts = []
    if raggio_km <= 0:
        return pts
    ang = raggio_km / R_TERRA_KM  # raggio angolare in radianti
    lat0r = _math.radians(lat0)
    lon0r = _math.radians(lon0)
    for i in range(punti + 1):
        brg = 2 * _math.pi * i / punti
        lat = _math.asin(_math.sin(lat0r) * _math.cos(ang) +
                         _math.cos(lat0r) * _math.sin(ang) * _math.cos(brg))
        lon = lon0r + _math.atan2(
            _math.sin(brg) * _math.sin(ang) * _math.cos(lat0r),
            _math.cos(ang) - _math.sin(lat0r) * _math.sin(lat))
        pts.append((_math.degrees(lat), (_math.degrees(lon) + 540) % 360 - 180))
    return pts


def traccia_passaggio(sat, aos_dt, los_dt, passi=60, oss_lat=None, oss_lon=None):
    """Campiona la traccia del satellite durante il passaggio.
    Ritorna lista di dict: {t, lat, lon, alt_km, raggio_km}.
    Se oss_lat/oss_lon sono dati, ogni campione ha anche 'az' ed 'el'
    visti dall'osservatore (per lo sky plot polare).
    Utile per animare footprint + ground track sulla mappa."""
    if not SKYFIELD_OK or aos_dt is None or los_dt is None:
        return []
    durata = (los_dt - aos_dt).total_seconds()
    if durata <= 0:
        return []
    istanti = [aos_dt + timedelta(seconds=durata * i / passi) for i in range(passi + 1)]
    try:
        ts = _timescale()
        t = ts.from_datetimes(istanti)
        geo = sat.at(t)
        sp = wgs84.subpoint(geo)
        lats = sp.latitude.degrees
        lons = sp.longitude.degrees
        alts = sp.elevation.km
        azs = els = None
        if oss_lat is not None and oss_lon is not None:
            oss = wgs84.latlon(oss_lat, oss_lon)
            alt, az, _ = (sat - oss).at(t).altaz()
            els, azs = alt.degrees, az.degrees
    except Exception:
        return []
    campioni = []
    for i, ti in enumerate(istanti):
        c = {
            "t": ti, "lat": float(lats[i]), "lon": float(lons[i]),
            "alt_km": round(float(alts[i]), 1),
            "raggio_km": round(raggio_footprint_km(float(alts[i])), 0),
        }
        if azs is not None:
            c["az"] = float(azs[i])
            c["el"] = float(els[i])
        campioni.append(c)
    return campioni


# ══════════════════════════════════════════════════════════════════
#  TRACCIA ORBITA (mappa del cruscotto)
# ══════════════════════════════════════════════════════════════════
_TS = None


def _timescale():
    """Timescale skyfield condiviso: evita di ricrearlo a ogni chiamata."""
    global _TS
    if _TS is None:
        _TS = load.timescale()
    return _TS


def traccia_orbita(sat, centro_dt, minuti_prima=10, minuti_dopo=95, passo_s=30):
    """Ground track attorno a un istante: da 'minuti_prima' prima a
    'minuti_dopo' dopo 'centro_dt' (circa un'orbita LEO in avanti).
    Ritorna (passato, futuro): due liste di (lat, lon)."""
    if not SKYFIELD_OK or sat is None or centro_dt is None:
        return [], []
    n_prima = max(1, int(minuti_prima * 60 / passo_s))
    n_dopo = max(1, int(minuti_dopo * 60 / passo_s))
    istanti = [centro_dt + timedelta(seconds=passo_s * k)
               for k in range(-n_prima, n_dopo + 1)]
    try:
        t = _timescale().from_datetimes(istanti)
        sp = wgs84.subpoint(sat.at(t))
        lats = sp.latitude.degrees
        lons = sp.longitude.degrees
    except Exception:
        return [], []
    punti = [(float(lats[i]), float(lons[i])) for i in range(len(istanti))]
    return punti[:n_prima + 1], punti[n_prima:]


def azel_da(sat, lat, lon, quando_dt, elev_m=0.0):
    """Azimut ed elevazione del satellite visti da (lat, lon) in un istante.
    Ritorna (el, az, dist_km) o None."""
    if not SKYFIELD_OK or sat is None:
        return None
    try:
        oss = wgs84.latlon(lat, lon, elevation_m=elev_m)
        t = _timescale().from_datetime(quando_dt)
        alt, az, dist = (sat - oss).at(t).altaz()
        return (float(alt.degrees), float(az.degrees), float(dist.km))
    except Exception:
        return None
