import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import math
import re

def locator_to_latlon(locator):
    """Convert a 4 or 6 character Maidenhead locator to (lat, lon) in degrees.
    Returns the coordinates of the CENTER of the grid square.
    Raises ValueError if the locator is invalid."""
    loc = (locator or "").strip().upper()
    if len(loc) not in (4, 6, 8):
        raise ValueError("Locator deve avere 4, 6 o 8 caratteri")

    A = ord('A')
    try:
        lon = (ord(loc[0]) - A) * 20.0 - 180.0
        lat = (ord(loc[1]) - A) * 10.0 - 90.0
        lon += int(loc[2]) * 2.0
        lat += int(loc[3]) * 1.0

        if len(loc) >= 6:
            lon += (ord(loc[4]) - A) * (2.0 / 24.0)
            lat += (ord(loc[5]) - A) * (1.0 / 24.0)
            # centro della sotto-cella 5'x2.5'
            lon += (2.0 / 24.0) / 2.0
            lat += (1.0 / 24.0) / 2.0
        else:
            # centro della cella 2°x1°
            lon += 1.0
            lat += 0.5

        if len(loc) == 8:
            lon += int(loc[6]) * (2.0 / 240.0)
            lat += int(loc[7]) * (1.0 / 240.0)
    except (ValueError, IndexError):
        raise ValueError("Locator non valido")

    if not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
        raise ValueError("Locator non valido")

    return lat, lon


def distanza_bearing(loc1, loc2):
    """Calcola distanza (km) e bearing iniziale (gradi, 0-360) da loc1 a loc2.
    loc1, loc2: locator Maidenhead (4 o 6 caratteri)."""
    lat1, lon1 = locator_to_latlon(loc1)
    lat2, lon2 = locator_to_latlon(loc2)

    R = 6371.0  # raggio medio Terra in km
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distanza = R * c

    y = math.sin(dlon) * math.cos(p2)
    x = math.cos(p1)*math.sin(p2) - math.sin(p1)*math.cos(p2)*math.cos(dlon)
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360

    return distanza, bearing


def bearing_to_compass(bearing):
    """Converte un bearing in gradi nella direzione bussola (N, NE, E...)."""
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
            "S","SSW","SW","WSW","W","WNW","NW","NNW"]
    idx = round(bearing / 22.5) % 16
    return dirs[idx]


def estrai_locator_da_testo(testo):
    """Cerca un locator Maidenhead valido (4 o 6 caratteri) in una stringa libera."""
    import re
    testo = (testo or "").upper()
    # 6 caratteri: due lettere, due cifre, due lettere
    m = re.search(r'\b([A-R]{2}[0-9]{2}[A-X]{2})\b', testo)
    if m:
        return m.group(1)
    # 4 caratteri: due lettere, due cifre
    m = re.search(r'\b([A-R]{2}[0-9]{2})\b', testo)
    if m:
        return m.group(1)
    return ""



