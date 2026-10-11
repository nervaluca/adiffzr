# -*- coding: utf-8 -*-
"""
Dashboard statistiche  —  ADIF FZR 2.6
Finestra unica con riepilogo attività, ripartizioni per banda/modo/anno,
rate operativo e avanzamento award (DXCC/WAS/WAZ/IOTA) con conferme LoTW/eQSL.

Il layer di calcolo (sezione CALCOLO) e' indipendente dalla GUI e testabile a
parte. La resa grafica usa Canvas tkinter, come gui/dialogs/charts.py, senza
dipendenze esterne (matplotlib non richiesto).
"""
import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import customtkinter as ctk
import tkinter as tk
from utils.osutil import apri_path

# Ordinamento bande (riusa quello di was_status se disponibile)
try:
    from gui.was_status import BAND_ORDER
except Exception:
    BAND_ORDER = ['160m', '80m', '60m', '40m', '30m', '20m', '17m',
                  '15m', '12m', '10m', '6m', '4m', '2m', '70cm',
                  '23cm', '13cm', '3cm']

# Keyfn award + flag conferme (riusa awards.py per coerenza con la finestra Award)
try:
    from gui.awards import (_kf_dxcc, _kf_was, _kf_waz, _kf_wac, _kf_iota,
                            _kf_wpx, _kf_vucc, _kf_cnty, _kf_waja, _flags,
                            AWARD_INFO, CONT_NAMES, WAC_CONTS)
    from gui.was_status import _default_getter as _GET, STATE_NAMES, US_STATES
    _AWARDS_OK = True
except Exception:
    _AWARDS_OK = False
    AWARD_INFO = {
        'DXCC': ("DX Century Club", "entita' DXCC", 100),
        'WAS':  ("Worked All States", "stati USA", 50),
        'WAZ':  ("Worked All Zones", "zone CQ", 40),
        'WAC':  ("Worked All Continents", "continenti", 6),
        'IOTA': ("Islands On The Air", "riferimenti isola", 100),
    }


# =========================================================================== #
#  CALCOLO (indipendente dalla GUI)
# =========================================================================== #
def _s(qso, k):
    return str(qso.get(k, "") or "").strip()


def _is_lotw(qso):
    r = _s(qso, "lotw_qsl_rcvd").upper()
    d = _s(qso, "lotw_qslrdate")
    return r in ("Y", "V") or (not r and d and d != "00000000")


def _is_eqsl(qso):
    r = _s(qso, "eqsl_qsl_rcvd").upper()
    d = _s(qso, "eqsl_qslrdate")
    return r == "Y" or (not r and d and d != "00000000")


def _is_paper(qso):
    return _s(qso, "qsl_rcvd").upper() in ("Y", "V")


def _is_sat(qso):
    """QSO via satellite: prop_mode=SAT oppure sat_name valorizzato."""
    return _s(qso, "prop_mode").upper() == "SAT" or bool(_s(qso, "sat_name"))


_CUR_DXCC_CACHE = None


def _codici_dxcc_attuali():
    """Set (int) dei codici DXCC delle entità ATTUALI, da utils.dxcc_countries.
    Vuoto se la tabella non è disponibile (allora non si distinguono i deleted)."""
    global _CUR_DXCC_CACHE
    if _CUR_DXCC_CACHE is not None:
        return _CUR_DXCC_CACHE
    s = set()
    try:
        from utils.dxcc_countries import DXCC_ENTITIES
        for v in DXCC_ENTITIES.values():
            try:
                c = int(str(v[0]).strip())
            except Exception:
                continue
            if c > 0:  # esclude il codice 0 ("[None]", non è un'entità)
                s.add(c)
    except Exception:
        pass
    _CUR_DXCC_CACHE = s
    return s


def _dxcc_int(qso):
    """Codice DXCC del QSO come int, o None se assente/zero."""
    d = _s(qso, "dxcc")
    if not d:
        return None
    try:
        n = int(float(d))
    except Exception:
        return None
    return n if n > 0 else None


def calc_overview(qsos):
    """Riepilogo generale. Ritorna un dict di aggregati.
    'dxcc' = entità ATTUALI distinte (esclude i deleted); i deleted e i QSO
    senza codice DXCC sono riportati a parte per diagnosi/coerenza."""
    per_anno, per_banda, per_modo, per_cont = {}, {}, {}, {}
    cur_codes = _codici_dxcc_attuali()
    dxcc = set()            # entità attuali (codici validi e presenti in tabella)
    dxcc_deleted = set()    # codici lavorati non presenti tra le attuali (deleted)
    dxcc_senza_codice = set()  # country di QSO privi di codice DXCC
    sat_codes = set()       # entità attuali lavorate via satellite
    sat_conf = set()        # entità attuali confermate via satellite (LoTW/cartacea)
    qso_sat = 0
    date_attive = set()
    lotw = eqsl = paper = 0
    dmin, dmax = None, None

    for q in qsos:
        d = _s(q, "qso_date")
        if len(d) == 8 and d.isdigit():
            per_anno[d[:4]] = per_anno.get(d[:4], 0) + 1
            date_attive.add(d)
            if dmin is None or d < dmin:
                dmin = d
            if dmax is None or d > dmax:
                dmax = d
        b = _s(q, "band").lower()
        if b:
            per_banda[b] = per_banda.get(b, 0) + 1
        m = _s(q, "mode").upper()
        if m:
            per_modo[m] = per_modo.get(m, 0) + 1
        c = _s(q, "cont").upper()
        if c in ("EU", "NA", "SA", "AS", "AF", "OC"):
            per_cont[c] = per_cont.get(c, 0) + 1
        # Entità DXCC: conta per CODICE (come il tab Award e il vero DXCC), e
        # distingue attuali vs deleted usando la tabella delle entità attuali.
        # Non mischiare col nome-paese: i QSO senza codice gonfierebbero il conto.
        n = _dxcc_int(q)
        if n is not None:
            if cur_codes and n not in cur_codes:
                dxcc_deleted.add(n)
            else:
                dxcc.add(n)
        else:
            cc = _s(q, "country").upper()
            if cc:
                dxcc_senza_codice.add(cc)
        # Satellite
        if _is_sat(q):
            qso_sat += 1
            if n is not None and (not cur_codes or n in cur_codes):
                sat_codes.add(n)
                if _is_lotw(q) or _is_paper(q):
                    sat_conf.add(n)
        if _is_lotw(q):
            lotw += 1
        if _is_eqsl(q):
            eqsl += 1
        if _is_paper(q):
            paper += 1

    tot = len(qsos)
    return {
        "totale": tot,
        "dxcc": len(dxcc),
        "dxcc_deleted": len(dxcc_deleted),
        "dxcc_deleted_codici": sorted(dxcc_deleted),
        "dxcc_senza_codice": sorted(dxcc_senza_codice),
        "qso_sat": qso_sat,
        "dxcc_sat": len(sat_codes),
        "dxcc_sat_conf": len(sat_conf),
        "bande": len(per_banda),
        "modi": len(per_modo),
        "lotw": lotw,
        "eqsl": eqsl,
        "paper": paper,
        "lotw_pct": (100.0 * lotw / tot) if tot else 0.0,
        "eqsl_pct": (100.0 * eqsl / tot) if tot else 0.0,
        "per_anno": per_anno,
        "per_banda": per_banda,
        "per_modo": per_modo,
        "per_cont": per_cont,
        "giorni_attivi": len(date_attive),
        "data_min": dmin,
        "data_max": dmax,
    }


# Entità DXCC DELETED (ARRL "Deleted Entities" feb 2022, 62 voci): code -> (nome, cont)
_DELETED_DXCC = {
    2: ("Abu Ail Is.", "AS"),
    8: ("Aldabra", "AF"),
    19: ("Bajo Nuevo", "NA"),
    23: ("Blenheim Reef", "AF"),
    25: ("British North Borneo", "OC"),
    26: ("British Somaliland", "AF"),
    28: ("Canal Zone", "NA"),
    30: ("Celebe & Molucca Is.", "OC"),
    39: ("Comoros", "AF"),
    42: ("Damao, Diu", "AS"),
    44: ("Desroches", "AF"),
    55: ("Farquhar", "AF"),
    57: ("French Equatorial Africa", "AF"),
    58: ("French Indo-China", "AS"),
    59: ("French West Africa", "AF"),
    67: ("French India", "AS"),
    68: ("Kuwait/Saudi Arabia Neutral Zone", "AS"),
    81: ("Germany", "EU"),
    85: ("Bonaire, Curacao", "SA"),
    93: ("Geyser Reef", "AF"),
    101: ("Goa", "AS"),
    102: ("Gold Coast, Togoland", "AF"),
    113: ("Ifni", "AF"),
    115: ("Italian Somaliland", "AF"),
    119: ("Java", "OC"),
    127: ("Kamaran Is.", "AS"),
    128: ("Karelo-Finnish Republic", "EU"),
    134: ("Kingman Reef", "OC"),
    139: ("Kuria Muria I.", "AS"),
    151: ("Malyj Vysotskij I.", "EU"),
    154: ("Yemen Arab Republic", "AS"),
    155: ("Malaya", "AS"),
    164: ("Manchuria", "AS"),
    178: ("Minerva Reef", "OC"),
    183: ("Netherlands Borneo", "OC"),
    184: ("Netherlands New Guinea", "OC"),
    186: ("Newfoundland, Labrador", "NA"),
    193: ("Okinawa (Ryukyu Is.)", "AS"),
    194: ("Okino Tori-shima", "AS"),
    196: ("Palestine", "AS"),
    198: ("Papua Territory", "OC"),
    200: ("Portuguese Timor", "OC"),
    208: ("Ruanda-Urundi", "AF"),
    210: ("Saar", "EU"),
    218: ("Czechoslovakia", "EU"),
    220: ("Sarawak", "OC"),
    226: ("Saudi Arabia/Iraq Neutral Zone", "AS"),
    228: ("Serrana Bank & Roncador Cay", "NA"),
    229: ("German Democratic Republic", "EU"),
    231: ("Sikkim", "AS"),
    243: ("People's Democratic Rep. of Yemen", "AS"),
    244: ("Southern Sudan", "AF"),
    255: ("St. Maarten, Saba, St. Eustatius", "NA"),
    258: ("Sumatra", "OC"),
    261: ("Swan Is.", "NA"),
    264: ("Tangier", "AF"),
    267: ("Territory of New Guinea", "OC"),
    268: ("Tibet", "AS"),
    271: ("Trieste", "EU"),
    307: ("Zanzibar", "AF"),
    488: ("Walvis Bay", "AF"),
    493: ("Penguin Is.", "AF"),
}


def calc_dxcc_table(qsos):
    """Entità DXCC nei 4 gruppi: ATTUALI lavorate/mancanti e DELETED
    lavorate/mancanti, con conferme LoTW/eQSL.
    Riga: {code, nome, cont, kind('cur'|'del'), worked, qso, lotw, eqsl, conf}."""
    cur_info = {}   # code -> (nome, continente)  entità attuali
    try:
        from utils.dxcc_countries import DXCC_ENTITIES
        for nome, v in DXCC_ENTITIES.items():
            try:
                c = int(str(v[0]).strip())
            except Exception:
                continue
            if c > 0 and c not in cur_info:  # esclude il codice 0 ("[None]")
                cur_info[c] = (nome, (v[1] if len(v) > 1 else ""))
    except Exception:
        pass
    del_info = dict(_DELETED_DXCC)

    acc = {}          # code -> [qso, lotw, eqsl, paper]  (solo lavorati)
    for q in qsos:
        n = _dxcc_int(q)
        if n is None:
            continue
        cell = acc.setdefault(n, [0, 0, 0, 0])
        cell[0] += 1
        cell[1] += 1 if _is_lotw(q) else 0
        cell[2] += 1 if _is_eqsl(q) else 0
        cell[3] += 1 if _is_paper(q) else 0

    def _row(code, nome, cont, kind):
        c = acc.get(code)
        lo = bool(c and c[1])
        eq = bool(c and c[2])
        pa = bool(c and c[3])
        worked = c is not None
        # Per il DXCC la conferma valida è LoTW o QSL cartacea (NON eQSL)
        conf = lo or pa
        if not worked:
            stato = "miss"
        elif conf:
            stato = "conf"
        else:
            stato = "todo"   # lavorato ma da confermare
        return {"code": code, "nome": nome, "cont": cont, "kind": kind,
                "worked": worked, "qso": (c[0] if c else 0),
                "lotw": lo, "eqsl": eq, "paper": pa, "conf": conf, "stato": stato}

    cur_rows = [_row(code, n, co, "cur") for code, (n, co) in cur_info.items()]
    del_rows = [_row(code, n, co, "del") for code, (n, co) in del_info.items()]
    # eventuali codici lavorati non in nessuna tabella: in coda ai deleted
    noti = set(cur_info) | set(del_info)
    for code in sorted(acc):
        if code not in noti:
            del_rows.append(_row(code, "DXCC %d" % code, "", "del"))
    cur_rows.sort(key=lambda r: r["nome"])
    del_rows.sort(key=lambda r: r["nome"])

    def _st(rows):
        return {"lav": sum(1 for r in rows if r["worked"]),
                "conf": sum(1 for r in rows if r["stato"] == "conf"),
                "todo": sum(1 for r in rows if r["stato"] == "todo"),
                "manc": sum(1 for r in rows if r["stato"] == "miss"),
                "lotw": sum(1 for r in rows if r["lotw"])}
    cs = _st(cur_rows)
    ds = _st(del_rows)

    return {
        "rows": cur_rows + del_rows,
        "cur_tot": len(cur_rows), "cur_lav": cs["lav"], "cur_conf": cs["conf"],
        "cur_todo": cs["todo"], "cur_manc": cs["manc"], "cur_lotw": cs["lotw"],
        "del_tot": len(del_rows), "del_lav": ds["lav"], "del_conf": ds["conf"],
        "del_todo": ds["todo"], "del_manc": ds["manc"], "del_lotw": ds["lotw"],
        "has_table": bool(cur_info),
    }


# Award con insieme di riferimento ENUMERABILE (si può mostrare anche il "mancante")
def _award_kf(kind):
    if not _AWARDS_OK:
        return None
    return {"WAS": _kf_was, "WAZ": _kf_waz, "WAC": _kf_wac, "IOTA": _kf_iota,
            "WPX": _kf_wpx, "VUCC": _kf_vucc, "USACA": _kf_cnty,
            "WAJA": _kf_waja}.get(kind)


def _award_universe(kind):
    """Insieme completo id->descrizione per gli award enumerabili, altrimenti None."""
    if not _AWARDS_OK:
        return None
    if kind == "WAS":
        return {st: STATE_NAMES.get(st, st) for st in US_STATES}
    if kind == "WAZ":
        return {str(z): "Zona %d" % z for z in range(1, 41)}
    if kind == "WAC":
        return {c: CONT_NAMES.get(c, c) for c in WAC_CONTS}
    return None


def calc_award_table(qsos, kind):
    """Lista award generica con tre stati (confermato/da confermare/mancante).
    Per WAS/WAZ/WAC include anche i 'mancanti' (insieme completo noto);
    per IOTA/WPX/VUCC mostra solo i lavorati (universo non enumerabile)."""
    kf = _award_kf(kind)
    if kf is None:
        return None
    uni = _award_universe(kind)
    acc = {}      # id -> [qso, lotw, eqsl, paper]
    name = {}
    for q in qsos:
        try:
            rid, lbl = kf(q, _GET)
        except Exception:
            rid = None
        if not rid:
            continue
        c = acc.setdefault(rid, [0, 0, 0, 0])
        c[0] += 1
        c[1] += 1 if _is_lotw(q) else 0
        c[2] += 1 if _is_eqsl(q) else 0
        c[3] += 1 if _is_paper(q) else 0
        if rid not in name:
            name[rid] = lbl or str(rid)

    ids = list(uni.keys()) if uni else list(acc.keys())
    rows = []
    for rid in ids:
        c = acc.get(rid)
        lo = bool(c and c[1]); eq = bool(c and c[2]); pa = bool(c and c[3])
        worked = c is not None
        conf = lo or pa
        stato = "miss" if not worked else ("conf" if conf else "todo")
        nome = (uni.get(rid) if uni else None) or name.get(rid) or str(rid)
        rows.append({"id": str(rid), "nome": nome, "worked": worked,
                     "qso": (c[0] if c else 0), "lotw": lo, "eqsl": eq,
                     "paper": pa, "conf": conf, "stato": stato})
    if kind == "WAZ":
        rows.sort(key=lambda r: int(r["id"]) if r["id"].isdigit() else 999)
    else:
        rows.sort(key=lambda r: r["nome"])

    lav = sum(1 for r in rows if r["worked"])
    return {"rows": rows, "kind": kind, "has_universe": bool(uni),
            "nome_award": AWARD_INFO.get(kind, (kind,))[0],
            "tot": (len(rows) if uni else lav), "lav": lav,
            "conf": sum(1 for r in rows if r["stato"] == "conf"),
            "todo": sum(1 for r in rows if r["stato"] == "todo"),
            "manc": sum(1 for r in rows if r["stato"] == "miss")}


def calc_rate(qsos):
    """Rate operativo: giorni attivi, media QSO/giorno, miglior giorno/mese/anno."""
    per_giorno, per_mese, per_anno = {}, {}, {}
    for q in qsos:
        d = _s(q, "qso_date")
        if len(d) == 8 and d.isdigit():
            per_giorno[d] = per_giorno.get(d, 0) + 1
            per_mese[d[:6]] = per_mese.get(d[:6], 0) + 1
            per_anno[d[:4]] = per_anno.get(d[:4], 0) + 1
    giorni = len(per_giorno)
    tot = sum(per_giorno.values())

    def _best(dz):
        if not dz:
            return (None, 0)
        k = max(dz, key=lambda x: dz[x])
        return (k, dz[k])

    bg_k, bg_v = _best(per_giorno)
    bm_k, bm_v = _best(per_mese)
    ba_k, ba_v = _best(per_anno)
    return {
        "giorni_attivi": giorni,
        "media_giorno": (tot / giorni) if giorni else 0.0,
        "best_day": (bg_k, bg_v),
        "best_month": (bm_k, bm_v),
        "best_year": (ba_k, ba_v),
    }


def calc_award_progress(qsos):
    """Avanzamento di tutti gli award (worked e conferme), coerente con la
    finestra Award. Fallback minimale se awards.py non è disponibile."""
    ordine = ["DXCC", "WAS", "WAZ", "WAC", "VUCC", "WPX", "IOTA", "USACA", "WAJA"]
    out = []

    if _AWARDS_OK:
        kf = {"DXCC": _kf_dxcc, "WAS": _kf_was, "WAZ": _kf_waz, "WAC": _kf_wac,
              "VUCC": _kf_vucc, "WPX": _kf_wpx, "IOTA": _kf_iota,
              "USACA": _kf_cnty, "WAJA": _kf_waja}
        worked = {a: set() for a in ordine}
        c_lotw = {a: set() for a in ordine}
        c_eqsl = {a: set() for a in ordine}
        c_any = {a: set() for a in ordine}
        for q in qsos:
            lo, eq, pa = _flags(_GET, q)
            for a in ordine:
                try:
                    rid, _ = kf[a](q, _GET)
                except Exception:
                    rid = None
                if not rid:
                    continue
                worked[a].add(rid)
                if lo:
                    c_lotw[a].add(rid)
                if eq:
                    c_eqsl[a].add(rid)
                if lo or eq or pa:
                    c_any[a].add(rid)
        for a in ordine:
            tgt = AWARD_INFO.get(a, ("", "", 100))[2]
            out.append({
                "award": a,
                "nome": AWARD_INFO.get(a, (a,))[0],
                "worked": len(worked[a]),
                "lotw": len(c_lotw[a]),
                "eqsl": len(c_eqsl[a]),
                "conf": len(c_any[a]),
                "target": tgt,
            })
        return out

    # Fallback minimale (senza awards.py)
    for a in ordine:
        out.append({"award": a, "nome": a, "worked": 0, "lotw": 0,
                    "eqsl": 0, "conf": 0, "target": AWARD_INFO.get(a, ("", "", 100))[2]})
    return out


def _fmt_data(d):
    return f"{d[6:8]}/{d[4:6]}/{d[0:4]}" if d and len(d) == 8 else "—"


def _fmt_mese(ym):
    _MESI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
             "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
    if not ym or len(ym) != 6:
        return "—"
    try:
        return f"{_MESI[int(ym[4:6]) - 1]} {ym[:4]}"
    except Exception:
        return ym


# =========================================================================== #
#  MAPPA (calcolo posizioni + figura matplotlib, testabile con backend Agg)
# =========================================================================== #
def grid_to_latlon(grid):
    """Maidenhead -> (lat, lon) al centro del quadrato. None se non valido."""
    g = str(grid or "").strip().upper()
    if len(g) < 4 or not ("A" <= g[0] <= "R") or not ("A" <= g[1] <= "R"):
        return None
    if not (g[2].isdigit() and g[3].isdigit()):
        return None
    try:
        lon = (ord(g[0]) - 65) * 20 - 180 + int(g[2]) * 2
        lat = (ord(g[1]) - 65) * 10 - 90 + int(g[3]) * 1
        if len(g) >= 6 and "A" <= g[4] <= "X" and "A" <= g[5] <= "X":
            lon += (ord(g[4]) - 65) * (2.0 / 24) + (1.0 / 24)
            lat += (ord(g[5]) - 65) * (1.0 / 24) + (0.5 / 24)
        else:
            lon += 1.0
            lat += 0.5
        if -180 <= lon <= 180 and -90 <= lat <= 90:
            return (lat, lon)
    except Exception:
        pass
    return None


def _find_world_map():
    """Cerca world_map.jpg vicino al programma (come fa il cruscotto satelliti)."""
    basi = [os.path.dirname(os.path.abspath(__file__)),
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            os.getcwd()]
    try:
        basi.append(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
    except Exception:
        pass
    nomi = ("world_map.jpg", "worldmap.jpg", "WorldMap.jpg")
    subs = ("", "assets", "img", "images", "maps", "data")
    for base in basi:
        for sub in subs:
            for nome in nomi:
                p = os.path.join(base, sub, nome)
                if os.path.isfile(p):
                    return p
    return None


def home_from_qsos(qsos):
    """Locatore QTH dedotto dal my_gridsquare più frequente nel log. (lat,lon) o None."""
    cnt = {}
    for q in qsos:
        g = _s(q, "my_gridsquare").upper()[:6]
        if g:
            cnt[g] = cnt.get(g, 0) + 1
    if not cnt:
        return None
    return grid_to_latlon(max(cnt, key=lambda k: cnt[k]))


def build_map_figure(qsos, band=None, home_latlon=None, facecolor="#0D1626"):
    """Figura matplotlib con le griglie lavorate (verde=confermate, blu=lavorate).
    Sfondo Blue Marble se disponibile, altrimenti oceano + graticola.
    band: se valorizzata (es. '20m') filtra solo quella banda.
    home_latlon: (lat,lon) del proprio QTH -> marker a stella.
    Ritorna (fig, n_grid_unici). Richiede matplotlib."""
    from matplotlib.figure import Figure
    fig = Figure(figsize=(8.8, 4.6), dpi=100, facecolor=facecolor)
    ax = fig.add_subplot(111)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-90, 90)
    ax.set_facecolor("#0b2036")

    bg = _find_world_map()
    if bg:
        try:
            import matplotlib.image as mpimg
            ax.imshow(mpimg.imread(bg), extent=[-180, 180, -90, 90],
                      aspect="auto", zorder=0)
        except Exception:
            bg = None
    if not bg:
        for lon in range(-180, 181, 30):
            ax.axvline(lon, color="#13324f", lw=0.5, zorder=0)
        for lat in range(-90, 91, 30):
            ax.axhline(lat, color="#13324f", lw=0.5, zorder=0)

    bsel = (band or "").lower().strip()
    worked, conf = {}, {}
    for q in qsos:
        if bsel and _s(q, "band").lower() != bsel:
            continue
        ll = grid_to_latlon(_s(q, "gridsquare"))
        if not ll:
            continue
        key = _s(q, "gridsquare").upper()[:6]
        worked[key] = ll
        if _is_lotw(q) or _is_eqsl(q) or _is_paper(q):
            conf[key] = ll

    if worked:
        wx = [v[1] for k, v in worked.items() if k not in conf]
        wy = [v[0] for k, v in worked.items() if k not in conf]
        cx = [v[1] for v in conf.values()]
        cy = [v[0] for v in conf.values()]
        if wx:
            ax.scatter(wx, wy, s=14, c="#2c7be5", edgecolors="white",
                       linewidths=0.3, zorder=3, label=f"Lavorate ({len(wx)})")
        if cx:
            ax.scatter(cx, cy, s=16, c="#48BB78", edgecolors="white",
                       linewidths=0.3, zorder=4, label=f"Confermate ({len(cx)})")

    if home_latlon:
        ax.scatter([home_latlon[1]], [home_latlon[0]], s=120, marker="*",
                   c="#FFD24A", edgecolors="#1a1a1a", linewidths=0.6,
                   zorder=6, label="QTH")

    if worked or home_latlon:
        ax.legend(loc="lower left", fontsize=7, framealpha=0.7,
                  facecolor="#0f1b2d", edgecolor="#223b55", labelcolor="white")

    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#223b55")
    fig.tight_layout(pad=0.4)
    return fig, len(worked)


# =========================================================================== #
#  EXPORT PDF riepilogo (testabile headless)
# =========================================================================== #
def staz_from_qsos(qsos):
    cnt = {}
    for q in qsos:
        s = (_s(q, "station_callsign") or _s(q, "operator")).upper()
        if s:
            cnt[s] = cnt.get(s, 0) + 1
    return max(cnt, key=lambda k: cnt[k]) if cnt else ""


def build_summary_pdf(path, ov, rate, awards, stazione=""):
    """Scrive un PDF A4 di riepilogo statistiche. Usa reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as cv
    from reportlab.lib import colors as _col

    PW, PH = A4
    c = cv.Canvas(path, pagesize=A4)
    x = 18 * mm
    y = PH - 20 * mm

    c.setFillColor(_col.HexColor("#0a3d91"))
    c.setFont("Helvetica-Bold", 18)
    c.drawString(x, y, "ADIF FZR — Riepilogo statistiche")
    y -= 7 * mm
    c.setFont("Helvetica", 10)
    c.setFillColor(_col.HexColor("#444444"))
    sott = []
    if stazione:
        sott.append(stazione)
    if ov.get("data_min"):
        sott.append(f"{_fmt_data(ov['data_min'])} — {_fmt_data(ov['data_max'])}")
    c.drawString(x, y, "   ·   ".join(sott) if sott else "")
    y -= 10 * mm

    def tile(bx, by, w, h, titolo, val, col="#2c7be5"):
        c.setFillColor(_col.HexColor("#f2f6fc"))
        c.roundRect(bx, by - h, w, h, 3 * mm, fill=1, stroke=0)
        c.setFillColor(_col.HexColor(col))
        c.setFont("Helvetica-Bold", 17)
        c.drawString(bx + 5 * mm, by - 8 * mm, str(val))
        c.setFillColor(_col.HexColor("#555555"))
        c.setFont("Helvetica", 8)
        c.drawString(bx + 5 * mm, by - 13.5 * mm, titolo)

    tw, th, gap = 52 * mm, 17 * mm, 4 * mm
    kpis = [("QSO totali", f"{ov['totale']:,}".replace(",", "."), "#2c7be5"),
            ("Entità DXCC", ov["dxcc"], "#1f9d57"),
            ("Bande", ov["bande"], "#c05621"),
            ("Modi", ov["modi"], "#805ad5"),
            ("LoTW", f"{ov['lotw']} ({ov['lotw_pct']:.0f}%)", "#38a169"),
            ("eQSL", f"{ov['eqsl']} ({ov['eqsl_pct']:.0f}%)", "#319795")]
    for i, (t, v, col) in enumerate(kpis):
        bx = x + (i % 3) * (tw + gap)
        by = y - (i // 3) * (th + gap)
        tile(bx, by, tw, th, t, v, col)
    y -= 2 * (th + gap) + 4 * mm

    c.setFillColor(_col.HexColor("#333333"))
    c.setFont("Helvetica", 10)
    bd = rate["best_day"]
    c.drawString(x, y, f"Giorni attivi: {ov['giorni_attivi']}    "
                       f"Media: {rate['media_giorno']:.1f} QSO/giorno    "
                       f"Miglior giorno: {_fmt_data(bd[0])} ({bd[1]} QSO)")
    y -= 10 * mm

    def sezione(titolo, coppie, by, maxbar=60 * mm):
        c.setFillColor(_col.HexColor("#0a3d91"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x, by, titolo)
        by -= 6 * mm
        tot = max((v for _, v in coppie), default=1) or 1
        c.setFont("Helvetica", 9)
        for k, v in coppie[:8]:
            c.setFillColor(_col.HexColor("#333333"))
            c.drawString(x, by, str(k)[:14])
            c.setFillColor(_col.HexColor("#2c7be5"))
            c.roundRect(x + 32 * mm, by - 1, maxbar * (v / tot), 3.2 * mm, 1, fill=1, stroke=0)
            c.setFillColor(_col.HexColor("#555555"))
            c.drawString(x + 32 * mm + maxbar + 3 * mm, by, str(v))
            by -= 6 * mm
        return by - 3 * mm

    bande = [(b, ov["per_banda"][b]) for b in BAND_ORDER if b in ov["per_banda"]]
    bande += [(b, v) for b, v in ov["per_banda"].items() if b not in dict(bande)]
    modi = sorted(ov["per_modo"].items(), key=lambda t: -t[1])
    ycol = y
    ycol = sezione("QSO per banda", bande, ycol)
    ycol = sezione("QSO per modo", modi, ycol)

    # Award
    c.setFillColor(_col.HexColor("#0a3d91"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, ycol, "Award — confermati / target  (lavorati)")
    ycol -= 6 * mm
    c.setFont("Helvetica", 9)
    for a in awards:
        c.setFillColor(_col.HexColor("#333333"))
        tgt = a["target"] or max(a["worked"], 1)
        c.drawString(x, ycol, f"{a['award']:5s}  {a['conf']} / {tgt}   "
                              f"(lavorati {a['worked']} · LoTW {a['lotw']} · eQSL {a['eqsl']})")
        ycol -= 5.5 * mm

    c.setFillColor(_col.HexColor("#999999"))
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(x, 14 * mm, "Generato da ADIF FZR 2.6 — iw1fzr.it")
    c.showPage()
    c.save()


# =========================================================================== #
#  REPORT AWARD PDF (banda×modo, cosa manca dove) — testabile headless
# =========================================================================== #
def _cell_stato(cell):
    """Stato di una cella (dict w,l,e,p) del modello awards:
    'L'/'P' = confermato valido, 'e' = solo eQSL, '·' = lavorato, '' = manca."""
    if not cell:
        return ""
    if cell.get("l"):
        return "L"
    if cell.get("p"):
        return "P"
    if cell.get("e"):
        return "e"
    if cell.get("w"):
        return "·"
    return ""


def build_award_report_pdf(path, qsos, awards_list=("DXCC", "WAS", "WAZ", "WAC"),
                           getter=None, max_matrix_rows=400):
    """Report PDF della situazione award: per ciascun award riepilogo,
    elenco mancanti (mixed) e matrice banda×modo (Phone/CW/Digital/Sat) con lo
    stato per cella (così si vede 'Arizona manca 20m CW'). Usa awards.py."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors as C
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, PageBreak)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from gui.awards import compute_award, GROUP_LABEL, AWARD_INFO as _AI
    from gui.was_status import _default_getter as _dg
    g = getter or _dg

    styles = getSampleStyleSheet()
    # Larghezza utile del foglio A4 orizzontale (margini 12 mm per lato).
    usable_width = landscape(A4)[0] - 24 * mm
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=15,
                        textColor=C.HexColor("#0a3d91"), spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=10.5,
                        textColor=C.HexColor("#1b4b8a"), spaceBefore=6, spaceAfter=2)
    norm = ParagraphStyle("n", parent=styles["Normal"], fontSize=8.5, leading=11)
    small = ParagraphStyle("s", parent=styles["Normal"], fontSize=7.5, leading=9,
                           textColor=C.HexColor("#444444"))

    COL = {"L": C.HexColor("#1f7a3f"), "P": C.HexColor("#2f8a52"),
           "e": C.HexColor("#b5732a"), "·": C.HexColor("#d79a2b"),
           "": C.HexColor("#ffffff")}
    TXT = {"L": C.white, "P": C.white, "e": C.white, "·": C.black, "": C.black}

    story = []
    GROUPS_REP = [("mixed", "Mixed"), ("phone", "Phone/SSB"), ("cw", "CW"), ("digital", "Digitale")]

    for ai, kind in enumerate(awards_list):
        try:
            m = compute_award(qsos, kind, g)
        except Exception:
            continue
        rows = m["rows"]          # [(rid,label)]
        bands = m["bands"]        # bande presenti
        data = m["data"]
        sat = m.get("sat", {})
        sat_names = m.get("sat_names", [])
        tgt = m.get("target") or _AI.get(kind, ("", "", 0))[2]
        nome = _AI.get(kind, (kind,))[0]

        # stato mixed per riferimento
        def _ref_conf(rid):
            for b in bands:
                c = data["mixed"].get(rid, {}).get(b)
                if c and (c.get("l") or c.get("p")):
                    return True
            for sn in sat_names:
                c = sat.get(rid, {}).get(sn)
                if c and (c.get("l") or c.get("p")):
                    return True
            return False

        def _ref_worked(rid):
            for b in bands:
                c = data["mixed"].get(rid, {}).get(b)
                if c and c.get("w"):
                    return True
            for sn in sat_names:
                c = sat.get(rid, {}).get(sn)
                if c and c.get("w"):
                    return True
            return False

        conf = [r for r in rows if _ref_conf(r[0])]
        work = [r for r in rows if _ref_worked(r[0])]
        manc = [r for r in rows if not _ref_worked(r[0])]
        daconf = [r for r in rows if _ref_worked(r[0]) and not _ref_conf(r[0])]

        enb = (kind in ("WAS", "WAZ", "WAC", "DXCC"))  # universo completo noto
        if kind == "DXCC":
            # mancanti/confermate dalle ENTITÀ ATTUALI (340), non solo le lavorate
            dt = calc_dxcc_table(qsos)
            cur = [r for r in dt["rows"] if r["kind"] == "cur"]
            conf = [(r["code"], r["nome"]) for r in cur if r["stato"] == "conf"]
            daconf = [(r["code"], r["nome"]) for r in cur if r["stato"] == "todo"]
            manc = [(r["code"], r["nome"]) for r in cur if r["stato"] == "miss"]
            tgt = dt["cur_tot"]

        if ai > 0:
            story.append(PageBreak())
        story.append(Paragraph("%s — %s" % (kind, nome), h1))
        if enb:
            story.append(Paragraph(
                "Confermate <b>%d</b> / %s · da confermare %d · mancanti %d"
                % (len(conf), tgt, len(daconf), len(manc)), norm))
            if manc:
                story.append(Paragraph(
                    "<b>Mancanti:</b> " + ", ".join(lbl for _, lbl in manc), small))
            if daconf:
                story.append(Paragraph(
                    "<b>Da confermare:</b> " + ", ".join(lbl for _, lbl in daconf), small))
        else:
            story.append(Paragraph(
                "Lavorate <b>%d</b> · confermate %d · da confermare %d  "
                "(universo non elencabile: i 'mancanti' non sono listabili)"
                % (len(work), len(conf), len(daconf)), norm))
            if daconf:
                story.append(Paragraph(
                    "<b>Da confermare:</b> " + ", ".join(lbl for _, lbl in daconf)[:4000], small))

        # Righe della matrice: per enumerabili tutte, per DXCC solo lavorate
        rows_mat = rows if enb else work
        rows_mat = rows_mat[:max_matrix_rows]
        if not bands or not rows_mat:
            story.append(Paragraph("Nessun dato banda×modo.", small))
            continue

        story.append(Paragraph("Dettaglio banda × modo "
                               "(L/P = confermato valido, e = eQSL, · = lavorato, "
                               "vuoto = manca):", h2))
        for grp, glab in GROUPS_REP:
            gd = data.get(grp, {})
            # salta il gruppo se completamente vuoto
            if not any(_cell_stato(gd.get(rid, {}).get(b)) for rid, _ in rows_mat for b in bands):
                continue
            header = [glab] + bands
            tdata = [header]
            first_col = 34 * mm
            other_col = max(4 * mm, (usable_width - first_col) / max(1, len(bands)))
            matrix_font = 6 if other_col >= 8 * mm else 4.5
            styl = [("FONTSIZE", (0, 0), (-1, -1), matrix_font),
                    ("GRID", (0, 0), (-1, -1), 0.3, C.HexColor("#c8d2e0")),
                    ("BACKGROUND", (0, 0), (-1, 0), C.HexColor("#1b4b8a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), C.white),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]
            for ri, (rid, lbl) in enumerate(rows_mat, start=1):
                riga = [lbl[:22]]
                for ci, b in enumerate(bands, start=1):
                    s = _cell_stato(gd.get(rid, {}).get(b))
                    riga.append(s)
                    if s:
                        styl.append(("BACKGROUND", (ci, ri), (ci, ri), COL[s]))
                        styl.append(("TEXTCOLOR", (ci, ri), (ci, ri), TXT[s]))
                tdata.append(riga)
            colw = [first_col] + [other_col for _ in bands]
            t = Table(tdata, colWidths=colw, repeatRows=1)
            t.setStyle(TableStyle(styl))
            story.append(Paragraph(glab, small))
            story.append(t)

            # Totale del gruppo: entità confermate/target e lavorate.
            # Si usa l'intero universo dell'award, non solo le righe mostrate
            # nella matrice (DXCC, ad esempio, mostra solo le entità lavorate).
            gruppo_conf = 0
            gruppo_work = 0
            gruppo_target = len(rows)
            for rid, _lbl in rows:
                celle = [gd.get(rid, {}).get(b) for b in bands]
                if any(c and (c.get("l") or c.get("p")) for c in celle):
                    gruppo_conf += 1
                if any(c and c.get("w") for c in celle):
                    gruppo_work += 1
            story.append(Paragraph(
                "<b>Totale %s:</b> confermate %d/%d · lavorate %d/%d" %
                (glab, gruppo_conf, gruppo_target, gruppo_work, gruppo_target), small))
            story.append(Spacer(1, 4))

        # Satellite (solo righe con attività satellitare)
        sat_rows = [(rid, lbl) for rid, lbl in rows_mat
                    if any(_cell_stato(sat.get(rid, {}).get(sn)) for sn in sat_names)]
        if sat_names and sat_rows:
            header = ["Satellite"] + [sn[:8] for sn in sat_names]
            tdata = [header]
            sat_first_col = 28 * mm
            # Ripartisce SEMPRE lo spazio utile tra tutte le colonne satellite:
            # evitare un minimo fisso che faceva uscire la tabella dal foglio.
            sat_col = max(1, (usable_width - sat_first_col) / max(1, len(sat_names)))
            sat_font = 6 if sat_col >= 8 * mm else (5 if sat_col >= 5.5 * mm else (4 if sat_col >= 4 * mm else 3.5))
            styl = [("FONTSIZE", (0, 0), (-1, -1), sat_font),
                    ("GRID", (0, 0), (-1, -1), 0.3, C.HexColor("#c8d2e0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 1),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 1),
                    ("BACKGROUND", (0, 0), (-1, 0), C.HexColor("#5a3a8a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), C.white),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER")]
            for ri, (rid, lbl) in enumerate(sat_rows, start=1):
                riga = [lbl[:22]]
                for ci, sn in enumerate(sat_names, start=1):
                    s = _cell_stato(sat.get(rid, {}).get(sn))
                    riga.append(s)
                    if s:
                        styl.append(("BACKGROUND", (ci, ri), (ci, ri), COL[s]))
                        styl.append(("TEXTCOLOR", (ci, ri), (ci, ri), TXT[s]))
                tdata.append(riga)
            t = Table(tdata, colWidths=[sat_first_col] + [sat_col] * len(sat_names),
                      repeatRows=1)
            t.setStyle(TableStyle(styl))
            story.append(Paragraph("Satellite", small))
            story.append(t)
            sat_conf_total = 0
            sat_work_total = 0
            sat_target = len(rows)
            for rid, _lbl in rows:
                celle = [sat.get(rid, {}).get(sn) for sn in sat_names]
                if any(c and (c.get("l") or c.get("p")) for c in celle):
                    sat_conf_total += 1
                if any(c and c.get("w") for c in celle):
                    sat_work_total += 1
            story.append(Paragraph(
                "<b>Totale Satellite:</b> confermate %d/%d · lavorate %d/%d" %
                (sat_conf_total, sat_target, sat_work_total, sat_target), small))

    doc = SimpleDocTemplate(path, pagesize=landscape(A4),
                            leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title="Report award ADIF FZR")
    if not story:
        story = [Paragraph("Nessun dato award disponibile.", norm)]
    doc.build(story)


# =========================================================================== #
#  GUI
# =========================================================================== #
_PALETTE = ["#2B6CB0", "#48BB78", "#C05621", "#805AD5", "#D69E2E",
            "#319795", "#E53E3E", "#3182CE", "#38A169", "#DD6B20"]


class DashboardDialog(ctk.CTkToplevel):
    def __init__(self, parent, qsos, colori_pdf):
        super().__init__(parent)
        self.title("Statistiche")
        self.geometry("1060x800")
        self.minsize(900, 620)
        self.resizable(True, True)
        self.grab_set()
        self.qsos = qsos or []
        self.colori_pdf = colori_pdf or {"primario": "#2B6CB0", "secondario": "#48BB78"}

        self.ov = calc_overview(self.qsos)
        self.rate = calc_rate(self.qsos)
        self.awards = calc_award_progress(self.qsos)

        ctk.CTkLabel(self, text="📊 Statistiche",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 4))

        # Il pulsante Chiudi va impacchettato in fondo PRIMA del contenuto
        # espandibile, altrimenti con finestra bassa finisce fuori schermo.
        ctk.CTkButton(self, text="Chiudi", command=self.destroy,
                      fg_color="#718096", width=120).pack(side="bottom", pady=8)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=6)
        for t in ("Riepilogo", "Attività", "Bande & Modi", "Mappa", "Award"):
            self.tabs.add(t)

        self._build_riepilogo(self.tabs.tab("Riepilogo"))
        self._build_attivita(self.tabs.tab("Attività"))
        self._build_bande_modi(self.tabs.tab("Bande & Modi"))
        self._build_mappa(self.tabs.tab("Mappa"))
        self._build_award(self.tabs.tab("Award"))

    # ---- helper: KPI tile ------------------------------------------------- #
    def _tile(self, parent, titolo, valore, sub="", colore="#2B6CB0", command=None):
        bordo = "#2c7be5" if command else "#223b55"
        card = ctk.CTkFrame(parent, corner_radius=10, fg_color="#132742",
                            border_width=1, border_color=bordo)
        l_val = ctk.CTkLabel(card, text=valore, font=ctk.CTkFont(size=26, weight="bold"),
                             text_color=colore)
        l_val.pack(anchor="w", padx=14, pady=(12, 0))
        tit = titolo + ("   ▸" if command else "")
        l_tit = ctk.CTkLabel(card, text=tit, font=ctk.CTkFont(size=12),
                             text_color="#cdd9ea")
        l_tit.pack(anchor="w", padx=14, pady=(0, 2))
        if sub:
            l_sub = ctk.CTkLabel(card, text=sub, font=ctk.CTkFont(size=10),
                                 text_color="#8396b0")
            l_sub.pack(anchor="w", padx=14, pady=(0, 10))
        else:
            l_sub = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=2))
            l_sub.pack(pady=(0, 8))
        if command:
            for w in (card, l_val, l_tit, l_sub):
                try:
                    w.configure(cursor="hand2")
                except Exception:
                    pass
                w.bind("<Button-1>", lambda _e, c=command: c())
        return card

    # ---- helper: bar chart verticale su canvas ---------------------------- #
    def _bar_canvas(self, parent, dati_ord, colore, title, H=300, label_angle=0,
                    on_click=None):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=8, pady=6)
        W = 880
        PAD_L, PAD_R, PAD_T, PAD_B = 50, 16, 24, 54
        cv = tk.Canvas(frame, width=W, height=H, bg="#0D1626", highlightthickness=0)
        cv.pack(fill="both", expand=True)
        titolo = title + ("   (clicca una barra)" if on_click else "")
        cv.create_text(W // 2, 10, text=titolo, font=("Arial", 10, "bold"), fill="#8fc0ff")
        if not dati_ord:
            cv.create_text(W // 2, H // 2, text="Nessun dato", font=("Arial", 12), fill="#718096")
            return
        valori = [v for _, v in dati_ord]
        max_v = max(valori) if valori else 1
        n = len(dati_ord)
        area_w = W - PAD_L - PAD_R
        area_h = H - PAD_T - PAD_B
        bar_w = max(6, min(64, area_w // n - 4))
        gap = max(2, (area_w - bar_w * n) // (n + 1))
        steps = 5
        for i in range(steps + 1):
            y = PAD_T + area_h - int(area_h * i / steps)
            cv.create_line(PAD_L, y, W - PAD_R, y, fill="#1f3350", dash=(3, 4))
            cv.create_text(PAD_L - 6, y, text=str(int(max_v * i / steps)),
                           anchor="e", font=("Arial", 8), fill="#6b7f9c")
        hit = []   # (x0, x1, label) per il click
        for i, (k, v) in enumerate(dati_ord):
            x0 = PAD_L + gap + i * (bar_w + gap)
            x1 = x0 + bar_w
            bh = int(area_h * v / max_v) if max_v else 0
            y0 = PAD_T + area_h - bh
            y1 = PAD_T + area_h
            col = colore if isinstance(colore, str) else _PALETTE[i % len(_PALETTE)]
            cv.create_rectangle(x0, y0, x1, y1, fill=col, outline="")
            cv.create_text((x0 + x1) // 2, y0 - 7, text=str(v),
                           font=("Arial", 8, "bold"), fill="#dbe6f6")
            cv.create_text((x0 + x1) // 2, y1 + 8, text=str(k), font=("Arial", 8),
                           fill="#9fb6d4", angle=label_angle,
                           anchor="n" if label_angle == 0 else "ne")
            hit.append((x0 - gap / 2.0, x1 + gap / 2.0, str(k)))
        cv.create_line(PAD_L, PAD_T, PAD_L, PAD_T + area_h, fill="#4A5568")
        cv.create_line(PAD_L, PAD_T + area_h, W - PAD_R, PAD_T + area_h, fill="#4A5568")
        if on_click:
            def _click(ev, _hit=hit, _cb=on_click, _ytop=PAD_T, _ybot=PAD_T + area_h):
                if ev.y < _ytop - 10 or ev.y > _ybot + 40:
                    return
                for x0, x1, lab in _hit:
                    if x0 <= ev.x <= x1:
                        _cb(lab)
                        return
            cv.configure(cursor="hand2")
            cv.bind("<Button-1>", _click)

    # ---- TAB Riepilogo ---------------------------------------------------- #
    def _esporta_pdf(self):
        from tkinter import filedialog, messagebox
        staz = staz_from_qsos(self.qsos)
        nome = f"Riepilogo_{staz or 'ADIF_FZR'}.pdf"
        path = filedialog.asksaveasfilename(
            parent=self, title="Esporta riepilogo PDF", defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")], initialfile=nome)
        if not path:
            return
        try:
            build_summary_pdf(path, self.ov, self.rate, self.awards, staz)
        except Exception as ex:
            messagebox.showerror("Export PDF", f"Errore:\n{ex}", parent=self)
            return
        if messagebox.askyesno("Export PDF", "PDF creato.\nAprirlo ora?", parent=self):
            try:
                apri_path((path))
            except Exception:
                pass

    def _build_riepilogo(self, tab):
        ov = self.ov
        topbar = ctk.CTkFrame(tab, fg_color="transparent")
        topbar.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkButton(topbar, text="⤓ Esporta PDF", width=130, height=30,
                      fg_color="#1f9d57", hover_color="#17a74a",
                      command=self._esporta_pdf).pack(side="right")
        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.pack(fill="x", padx=10, pady=(6, 6))
        tiles = [
            ("QSO totali", f"{ov['totale']:,}".replace(",", "."), "", "#2c7be5", None),
            ("Entità DXCC", str(ov["dxcc"]),
             (f"attuali · +{ov['dxcc_deleted']} deleted" if ov.get("dxcc_deleted")
              else "attuali"), "#48BB78", self._mostra_lista_dxcc),
            ("Bande", str(ov["bande"]), "", "#C05621", None),
            ("Modi", str(ov["modi"]), "", "#805AD5", None),
            ("Conferme LoTW", str(ov["lotw"]), f"{ov['lotw_pct']:.0f}% dei QSO", "#38A169", None),
            ("Conferme eQSL", str(ov["eqsl"]), f"{ov['eqsl_pct']:.0f}% dei QSO", "#319795", None),
        ]
        if ov.get("qso_sat"):
            tiles.append(("DXCC via satellite", str(ov["dxcc_sat"]),
                          f"conf {ov['dxcc_sat_conf']} · {ov['qso_sat']} QSO sat",
                          "#8fc0ff", lambda: self._mostra_lista_dxcc(solo_sat=True)))
        for i in range(6):
            grid.columnconfigure(i, weight=1, uniform="k")
        for i, (t, v, s, c, cmd) in enumerate(tiles):
            self._tile(grid, t, v, s, c, command=cmd).grid(
                row=i // 3, column=(i % 3) * 2,
                columnspan=2, padx=6, pady=6, sticky="nsew")

        # Riga riassuntiva periodo + rate
        info = ctk.CTkFrame(tab, corner_radius=10, fg_color="#0f1b2d",
                            border_width=1, border_color="#223b55")
        info.pack(fill="x", padx=16, pady=(8, 6))
        r = self.rate
        bd_k, bd_v = r["best_day"]
        righe = [
            f"Periodo:  {_fmt_data(ov['data_min'])}  →  {_fmt_data(ov['data_max'])}",
            f"Giorni attivi:  {ov['giorni_attivi']}     Media:  {r['media_giorno']:.1f} QSO/giorno",
            f"Miglior giorno:  {_fmt_data(bd_k)}  ({bd_v} QSO)     "
            f"Miglior mese:  {_fmt_mese(r['best_month'][0])}  ({r['best_month'][1]} QSO)",
        ]
        for t in righe:
            ctk.CTkLabel(info, text=t, font=ctk.CTkFont(size=12),
                         text_color="#dce6f3", anchor="w").pack(anchor="w", padx=14, pady=3)

        # Ripartizione continenti (barra orizzontale compatta)
        if ov["per_cont"]:
            self._continenti(tab, ov["per_cont"], ov["totale"])

    def _continenti(self, tab, per_cont, tot):
        box = ctk.CTkFrame(tab, fg_color="transparent")
        box.pack(fill="x", padx=16, pady=(4, 8))
        ctk.CTkLabel(box, text="Ripartizione per continente",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#8fc0ff").pack(anchor="w", pady=(0, 4))
        nomi = {"EU": "Europa", "NA": "Nord America", "SA": "Sud America",
                "AS": "Asia", "AF": "Africa", "OC": "Oceania"}
        for i, (c, v) in enumerate(sorted(per_cont.items(), key=lambda x: -x[1])):
            riga = ctk.CTkFrame(box, fg_color="transparent")
            riga.pack(fill="x", pady=1)
            ctk.CTkLabel(riga, text=nomi.get(c, c), width=110, anchor="w",
                         font=ctk.CTkFont(size=11), text_color="#cdd9ea").pack(side="left")
            pb = ctk.CTkProgressBar(riga, height=12,
                                    progress_color=_PALETTE[i % len(_PALETTE)])
            pb.pack(side="left", fill="x", expand=True, padx=8)
            pb.set((v / tot) if tot else 0)
            ctk.CTkLabel(riga, text=f"{v}  ({100*v/tot:.0f}%)" if tot else str(v),
                         width=90, anchor="e", font=ctk.CTkFont(size=11),
                         text_color="#9fb6d4").pack(side="left")

    # ---- Dialog lista entità DXCC (clic sulla tile) ----------------------- #
    def _mostra_lista_dxcc(self, solo_sat=False, band=None, mode=None,
                           stato_default="Tutti"):
        import tkinter.ttk as ttk
        from tkinter import messagebox
        base = calc_dxcc_table(self.qsos)
        if not base["has_table"]:
            messagebox.showinfo("Entità DXCC",
                                "Tabella entità attuali non disponibile.", parent=self)
            return
        win = ctk.CTkToplevel(self)
        if band:
            win.title("DXCC su banda %s — lavorate e mancanti" % band)
        elif mode:
            win.title("DXCC su modo %s — lavorate e mancanti" % mode)
        else:
            win.title("Entità DXCC — attuali e deleted, lavorate e mancanti")
        win.geometry("860x680")
        win.minsize(700, 500)
        win.grab_set(); win.lift(); win.focus_force()

        store = {"data": base}
        lbl_head = ctk.CTkLabel(win, font=ctk.CTkFont(size=14, weight="bold"), text="")
        lbl_head.pack(pady=(10, 2))

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=(2, 0))
        var_cerca = ctk.StringVar()
        var_src = ctk.StringVar(value="Satellite" if solo_sat else "Tutti")
        var_gruppo = ctk.StringVar(value="Tutti")
        var_stato = ctk.StringVar(value=stato_default)
        var_cont = ctk.StringVar(value="Tutti")
        ctk.CTkLabel(bar, text="Cerca:").pack(side="left")
        ctk.CTkEntry(bar, textvariable=var_cerca, width=130).pack(side="left", padx=(4, 8))
        ctk.CTkLabel(bar, text="QSO:").pack(side="left")
        ctk.CTkOptionMenu(bar, variable=var_src, width=100,
                          values=["Tutti", "Satellite", "Terrestre"],
                          command=lambda _=None: _refresh()).pack(side="left", padx=(2, 8))
        ctk.CTkLabel(bar, text="Gruppo:").pack(side="left")
        ctk.CTkOptionMenu(bar, variable=var_gruppo, width=95,
                          values=["Tutti", "Attuali", "Deleted"],
                          command=lambda _=None: _popola()).pack(side="left", padx=(2, 8))
        ctk.CTkLabel(bar, text="Stato:").pack(side="left")
        ctk.CTkOptionMenu(bar, variable=var_stato, width=135,
                          values=["Tutti", "Confermati", "Da confermare",
                                  "Non lavorati", "Da completare"],
                          command=lambda _=None: _popola()).pack(side="left", padx=(2, 8))
        ctk.CTkOptionMenu(bar, variable=var_cont, width=75,
                          values=["Tutti", "EU", "NA", "SA", "AS", "AF", "OC"],
                          command=lambda _=None: _popola()).pack(side="left")

        # Fondo fisso (legenda + Chiudi) impacchettato PRIMA della tabella
        bottom = ctk.CTkFrame(win, fg_color="transparent")
        bottom.pack(side="bottom", fill="x")

        frame = ctk.CTkFrame(win)
        frame.pack(fill="both", expand=True, padx=12, pady=8)
        style = ttk.Style()
        try:
            style.theme_use("default")
        except Exception:
            pass
        style.configure("DX.Treeview", background="#0D1626", foreground="#9fb6d4",
                        fieldbackground="#0D1626", rowheight=22, font=("Segoe UI", 10))
        style.configure("DX.Treeview.Heading", background="#1A365D",
                        foreground="white", font=("Segoe UI", 9, "bold"))
        cols = ("Tipo", "Entità", "Cont", "DXCC", "QSO", "LoTW", "QSL", "eQSL")
        tree = ttk.Treeview(frame, columns=cols, show="headings", style="DX.Treeview")
        for c, w, anc in (("Tipo", 62, "center"), ("Entità", 240, "w"),
                          ("Cont", 46, "center"), ("DXCC", 50, "center"),
                          ("QSO", 50, "center"), ("LoTW", 50, "center"),
                          ("QSL", 50, "center"), ("eQSL", 50, "center")):
            tree.heading(c, text=c)
            tree.column(c, width=w, anchor=anc)
        # Tre stati, tre colori: confermato=verde, da confermare=ambra, mancante=grigio.
        # I deleted in tinta più tenue.
        tree.tag_configure("conf", foreground="#4ADE80", font=("Segoe UI", 10, "bold"))
        tree.tag_configure("todo", foreground="#e0a53a", font=("Segoe UI", 10, "bold"))
        tree.tag_configure("miss", foreground="#55657c")
        tree.tag_configure("conf_del", foreground="#86c7a0", font=("Segoe UI", 10, "bold"))
        tree.tag_configure("todo_del", foreground="#c0a062", font=("Segoe UI", 10, "bold"))
        tree.tag_configure("miss_del", foreground="#44515f")
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _set_header(d):
            lbl_head.configure(text=(
                f"ATTUALI /{d['cur_tot']}:  confermate {d['cur_conf']} · "
                f"da confermare {d['cur_todo']} · mancanti {d['cur_manc']}"
                f"      |      DELETED /{d['del_tot']}:  confermate {d['del_conf']} · "
                f"da confermare {d['del_todo']} · mancanti {d['del_manc']}"))

        def _dataset():
            qs = self.qsos
            if band:
                qs = [q for q in qs if _s(q, "band").lower() == band.lower()]
            if mode:
                qs = [q for q in qs if _s(q, "mode").upper() == mode.upper()]
            src = var_src.get()
            if src == "Satellite":
                qs = [q for q in qs if _is_sat(q)]
            elif src == "Terrestre":
                qs = [q for q in qs if not _is_sat(q)]
            return calc_dxcc_table(qs)

        def _popola(*_):
            tree.delete(*tree.get_children())
            q = var_cerca.get().strip().upper()
            grp = var_gruppo.get()
            stato = var_stato.get()
            cont = var_cont.get()
            for r in store["data"]["rows"]:
                if grp == "Attuali" and r["kind"] != "cur":
                    continue
                if grp == "Deleted" and r["kind"] != "del":
                    continue
                st = r["stato"]   # 'conf' | 'todo' | 'miss'
                if stato == "Confermati" and st != "conf":
                    continue
                if stato == "Da confermare" and st != "todo":
                    continue
                if stato == "Non lavorati" and st != "miss":
                    continue
                if stato == "Da completare" and st == "conf":
                    continue   # mostra da confermare + mancanti
                if cont != "Tutti" and r["cont"] != cont:
                    continue
                if q and q not in r["nome"].upper():
                    continue
                dele = (r["kind"] == "del")
                tag = st + ("_del" if dele else "")
                tree.insert("", "end", tags=(tag,), values=(
                    "Deleted" if dele else "Attuale",
                    r["nome"], r["cont"], r["code"], r["qso"] or "",
                    "✓" if r["lotw"] else "—",
                    "✓" if r["paper"] else "—",
                    "✓" if r["eqsl"] else "—"))

        def _refresh(*_):
            store["data"] = _dataset()
            _set_header(store["data"])
            _popola()

        try:
            var_cerca.trace_add("write", lambda *a: _popola())
        except Exception:
            pass
        _refresh()

        ctk.CTkLabel(bottom, text="Verde = confermato (LoTW o cartacea) · ambra = lavorato, da confermare · "
                              "grigio = non lavorato · righe più tenui = deleted  "
                              "(per il DXCC l'eQSL non vale)",
                     font=ctk.CTkFont(size=10), text_color="#8396b0").pack(pady=(0, 2))
        ctk.CTkButton(bottom, text="Chiudi", command=win.destroy,
                      fg_color="#718096", width=100).pack(pady=(2, 10))

    # ---- TAB Attività ----------------------------------------------------- #
    def _mesi_conta(self):
        """Conteggi per mese (1..12) e per anno-mese (YYYY-MM)."""
        per_mese, per_am = {}, {}
        for q in self.qsos:
            d = _s(q, "qso_date")
            if len(d) == 8 and d.isdigit():
                mn = int(d[4:6]) if d[4:6].isdigit() else 0
                if 1 <= mn <= 12:
                    per_mese[mn] = per_mese.get(mn, 0) + 1
                per_am[f"{d[:4]}-{d[4:6]}"] = per_am.get(f"{d[:4]}-{d[4:6]}", 0) + 1
        return per_mese, per_am

    def _build_attivita(self, tab):
        # NB: niente CTkScrollableFrame (dentro una tab del CTkTabview può
        # restare ad altezza 0 e la scheda appare vuota). I 3 grafici
        # condividono l'altezza della scheda.
        dati_a = sorted(self.ov["per_anno"].items())
        self._bar_canvas(tab, dati_a, self.colori_pdf.get("primario", "#2c7be5"),
                         "QSO per anno", H=200,
                         label_angle=35 if len(dati_a) > 12 else 0)
        per_mese, per_am = self._mesi_conta()
        _MESI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
                 "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
        # QSO per mese dell'anno (1..12)
        dati_m = [(_MESI[m - 1], per_mese.get(m, 0)) for m in range(1, 13)]
        self._bar_canvas(tab, dati_m, self.colori_pdf.get("secondario", "#48BB78"),
                         "QSO per mese (tutti gli anni)", H=200)
        # Andamento mensile (YYYY-MM)
        dati_am = sorted(per_am.items())
        if len(dati_am) > 60:
            dati_am = dati_am[-60:]   # ultimi 5 anni di mesi, per leggibilità
        self._bar_canvas(tab, dati_am, "#C05621",
                         "Andamento mensile", H=200, label_angle=35)

    # ---- TAB Bande & Modi ------------------------------------------------- #
    def _build_bande_modi(self, tab):
        # Bande ordinate per BAND_ORDER
        pb = self.ov["per_banda"]
        ordine = [b for b in BAND_ORDER if b in pb]
        ordine += [b for b in pb if b not in ordine]
        dati_b = [(b, pb[b]) for b in ordine]
        self._bar_canvas(tab, dati_b, "#2c7be5", "QSO per banda", H=250,
                         label_angle=35 if len(dati_b) > 12 else 0,
                         on_click=lambda lab: self._mostra_lista_dxcc(
                             band=lab, stato_default="Non lavorati"))
        # Modi (top 12)
        pm = sorted(self.ov["per_modo"].items(), key=lambda x: -x[1])[:12]
        self._bar_canvas(tab, pm, "#48BB78", "QSO per modo (top 12)", H=250,
                         label_angle=35 if len(pm) > 8 else 0,
                         on_click=lambda lab: self._mostra_lista_dxcc(
                             mode=lab, stato_default="Non lavorati"))

    # ---- Apre la finestra Award COMPLETA (matrici banda×modo) sull'award --- #
    def _apri_award_completo(self, kind):
        from tkinter import messagebox
        try:
            from gui.awards import AwardsWindow
        except Exception as ex:
            messagebox.showerror("Award", "Modulo Award non disponibile:\n%s" % ex,
                                 parent=self)
            return
        # La Dashboard è modale (grab): la finestra Award usa transient (niente
        # grab), quindi rilascio il grab o resterebbe non cliccabile.
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            w = AwardsWindow(self.master or self, qsos=self.qsos)
            try:
                w._select_award(kind)
            except Exception:
                pass
            try:
                w.focus()
            except Exception:
                pass
        except Exception as ex:
            messagebox.showerror("Award", "Errore apertura Award:\n%s" % ex, parent=self)

    # ---- Dialog lista award generico (WAS/WAZ/WAC/IOTA) ------------------- #
    def _mostra_lista_award(self, kind):
        import tkinter.ttk as ttk
        from tkinter import messagebox
        base = calc_award_table(self.qsos, kind)
        if base is None:
            messagebox.showinfo("Award", "Dati award non disponibili.", parent=self)
            return
        win = ctk.CTkToplevel(self)
        win.title("%s — %s" % (kind, base["nome_award"]))
        win.geometry("660x640")
        win.minsize(560, 460)
        win.grab_set(); win.lift(); win.focus_force()

        store = {"data": base}
        lbl = ctk.CTkLabel(win, font=ctk.CTkFont(size=14, weight="bold"), text="")
        lbl.pack(pady=(10, 2))

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=(2, 0))
        var_cerca = ctk.StringVar()
        var_src = ctk.StringVar(value="Tutti")
        var_stato = ctk.StringVar(value="Tutti")
        ctk.CTkLabel(bar, text="Cerca:").pack(side="left")
        ctk.CTkEntry(bar, textvariable=var_cerca, width=140).pack(side="left", padx=(4, 8))
        ctk.CTkLabel(bar, text="QSO:").pack(side="left")
        ctk.CTkOptionMenu(bar, variable=var_src, width=100,
                          values=["Tutti", "Satellite", "Terrestre"],
                          command=lambda _=None: _refresh()).pack(side="left", padx=(2, 8))
        ctk.CTkLabel(bar, text="Stato:").pack(side="left")
        ctk.CTkOptionMenu(bar, variable=var_stato, width=135,
                          values=["Tutti", "Confermati", "Da confermare",
                                  "Non lavorati", "Da completare"],
                          command=lambda _=None: _popola()).pack(side="left", padx=(2, 8))

        # Fondo fisso (legenda + Chiudi) impacchettato PRIMA della tabella
        bottom = ctk.CTkFrame(win, fg_color="transparent")
        bottom.pack(side="bottom", fill="x")

        frame = ctk.CTkFrame(win)
        frame.pack(fill="both", expand=True, padx=12, pady=8)
        style = ttk.Style()
        try:
            style.theme_use("default")
        except Exception:
            pass
        style.configure("AW.Treeview", background="#0D1626", foreground="#9fb6d4",
                        fieldbackground="#0D1626", rowheight=22, font=("Segoe UI", 10))
        style.configure("AW.Treeview.Heading", background="#1A365D",
                        foreground="white", font=("Segoe UI", 9, "bold"))
        cols = ("Rif", "Descrizione", "QSO", "LoTW", "QSL", "eQSL")
        tree = ttk.Treeview(frame, columns=cols, show="headings", style="AW.Treeview")
        for c, w, anc in (("Rif", 70, "center"), ("Descrizione", 250, "w"),
                          ("QSO", 55, "center"), ("LoTW", 55, "center"),
                          ("QSL", 55, "center"), ("eQSL", 55, "center")):
            tree.heading(c, text=c)
            tree.column(c, width=w, anchor=anc)
        tree.tag_configure("conf", foreground="#4ADE80", font=("Segoe UI", 10, "bold"))
        tree.tag_configure("todo", foreground="#e0a53a", font=("Segoe UI", 10, "bold"))
        tree.tag_configure("miss", foreground="#55657c")
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _set_header(d):
            if d["has_universe"]:
                lbl.configure(text="%s: confermati %d/%d · da confermare %d · mancanti %d"
                              % (d["kind"], d["conf"], d["tot"], d["todo"], d["manc"]))
            else:
                lbl.configure(text="%s: lavorati %d · confermati %d · da confermare %d"
                                   "   (universo non elencabile)"
                              % (d["kind"], d["lav"], d["conf"], d["todo"]))

        def _dataset():
            src = var_src.get()
            if src == "Satellite":
                qs = [q for q in self.qsos if _is_sat(q)]
            elif src == "Terrestre":
                qs = [q for q in self.qsos if not _is_sat(q)]
            else:
                qs = self.qsos
            return calc_award_table(qs, kind)

        def _popola(*_):
            tree.delete(*tree.get_children())
            q = var_cerca.get().strip().upper()
            stt = var_stato.get()
            for r in store["data"]["rows"]:
                st = r["stato"]
                if stt == "Confermati" and st != "conf":
                    continue
                if stt == "Da confermare" and st != "todo":
                    continue
                if stt == "Non lavorati" and st != "miss":
                    continue
                if stt == "Da completare" and st == "conf":
                    continue
                if q and q not in (r["nome"].upper() + " " + r["id"].upper()):
                    continue
                tree.insert("", "end", tags=(st,), values=(
                    r["id"], r["nome"], r["qso"] or "",
                    "✓" if r["lotw"] else "—",
                    "✓" if r["paper"] else "—",
                    "✓" if r["eqsl"] else "—"))

        def _refresh(*_):
            store["data"] = _dataset()
            _set_header(store["data"])
            _popola()

        try:
            var_cerca.trace_add("write", lambda *a: _popola())
        except Exception:
            pass
        _refresh()

        ctk.CTkLabel(bottom, text="Verde = confermato (LoTW o cartacea) · ambra = da confermare · "
                              "grigio = mancante",
                     font=ctk.CTkFont(size=10), text_color="#8396b0").pack(pady=(0, 2))
        ctk.CTkButton(bottom, text="Chiudi", command=win.destroy,
                      fg_color="#718096", width=100).pack(pady=(2, 10))

    # ---- TAB Mappa -------------------------------------------------------- #
    def _build_mappa(self, tab):
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa
        except Exception as ex:
            ctk.CTkLabel(tab, text="Mappa non disponibile (matplotlib assente)\n("
                                   + str(ex) + ")",
                         font=ctk.CTkFont(size=12), text_color="#9fb6d4").pack(pady=40)
            return
        self._map_home = home_from_qsos(self.qsos)

        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=(8, 2))
        ctk.CTkLabel(bar, text="Griglie lavorate — verde = confermate "
                              "(LoTW/eQSL/cartaceo), blu = lavorate, ★ = QTH",
                     font=ctk.CTkFont(size=11), text_color="#8fc0ff").pack(side="left")
        bande = [b for b in BAND_ORDER if b in self.ov["per_banda"]]
        bande += [b for b in self.ov["per_banda"] if b not in bande]
        self._map_band = ctk.StringVar(value="Tutte")
        ctk.CTkLabel(bar, text="Banda:", font=ctk.CTkFont(size=11),
                     text_color="#9fb6d4").pack(side="right", padx=(8, 4))
        ctk.CTkOptionMenu(bar, variable=self._map_band, width=120,
                          values=["Tutte"] + bande,
                          command=lambda _=None: self._render_map()).pack(side="right")

        self._map_holder = ctk.CTkFrame(tab, fg_color="transparent")
        self._map_holder.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self._render_map()

    def _render_map(self):
        for w in self._map_holder.winfo_children():
            w.destroy()
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        band = self._map_band.get()
        band = None if band == "Tutte" else band
        try:
            fig, n = build_map_figure(self.qsos, band=band, home_latlon=self._map_home)
        except Exception as ex:
            ctk.CTkLabel(self._map_holder, text="Errore mappa:\n" + str(ex),
                         font=ctk.CTkFont(size=11), text_color="#9fb6d4").pack(pady=30)
            return
        canvas = FigureCanvasTkAgg(fig, master=self._map_holder)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        if n == 0:
            ctk.CTkLabel(self._map_holder,
                         text="Nessun QSO con locatore (gridsquare) per questa selezione.",
                         font=ctk.CTkFont(size=11), text_color="#8396b0").pack(pady=4)

    # ---- TAB Award -------------------------------------------------------- #
    def _build_award(self, tab):
        head = ctk.CTkFrame(tab, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(12, 2))
        ctk.CTkButton(head, text="⤓ Report award PDF", width=160, height=30,
                      fg_color="#1f9d57", hover_color="#17a74a",
                      command=self._report_award_pdf).pack(side="right")
        ctk.CTkLabel(head, text="Avanzamento award — lavorati e confermati",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#8fc0ff").pack(anchor="w")
        ctk.CTkLabel(head, text="Barra piena = confermati (LoTW/eQSL/cartaceo) · "
                               "numero grigio = lavorati · clicca una riga per il dettaglio",
                     font=ctk.CTkFont(size=10), text_color="#8396b0").pack(anchor="w")

        # NB: CTkFrame (non Scrollable): dentro una tab del CTkTabview lo
        # scrollable può restare ad altezza 0 e la scheda appare vuota.
        wrap = ctk.CTkFrame(tab, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=16, pady=4)
        for i, a in enumerate(self.awards):
            try:
                self._award_row(wrap, a, _PALETTE[i % len(_PALETTE)])
            except Exception as ex:
                ctk.CTkLabel(wrap, text="Award %s: %s" % (a.get("award", "?"), ex),
                             font=ctk.CTkFont(size=10), text_color="#e0a53a",
                             anchor="w").pack(fill="x", padx=6, pady=1)

    # ---- Report award PDF (riepilogo + mancanti + banda×modo) ------------- #
    def _report_award_pdf(self):
        from tkinter import filedialog, messagebox

        # Prima scegli quali sezioni includere nel PDF.
        disponibili = [
            ("DXCC", "DXCC — entità DXCC"),
            ("WAS", "WAS — Worked All States"),
            ("WAZ", "WAZ — Worked All Zones"),
            ("WAC", "WAC — Worked All Continents"),
            ("IOTA", "IOTA — Islands On The Air"),
        ]
        scelta = {codice: tk.BooleanVar(value=True) for codice, _ in disponibili}
        finestra = ctk.CTkToplevel(self)
        finestra.title("Scegli gli award da stampare")
        finestra.geometry("390x360")
        finestra.resizable(False, False)
        finestra.transient(self)
        finestra.grab_set()
        ctk.CTkLabel(finestra, text="Award da includere nel PDF",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=20, pady=(18, 8))
        ctk.CTkLabel(finestra, text="Seleziona uno o più award. Il dettaglio satellite viene adattato alla larghezza del foglio.",
                     font=ctk.CTkFont(size=11), wraplength=345, justify="left").pack(anchor="w", padx=20, pady=(0, 10))
        for codice, etichetta in disponibili:
            ctk.CTkCheckBox(finestra, text=etichetta, variable=scelta[codice]).pack(anchor="w", padx=24, pady=5)
        risultato = {"awards": None}

        def conferma():
            selezionati = [codice for codice, _ in disponibili if scelta[codice].get()]
            if not selezionati:
                messagebox.showwarning("Report award", "Seleziona almeno un award.", parent=finestra)
                return
            risultato["awards"] = selezionati
            finestra.destroy()

        def annulla():
            finestra.destroy()

        fondo = ctk.CTkFrame(finestra, fg_color="transparent")
        fondo.pack(side="bottom", fill="x", padx=20, pady=16)
        ctk.CTkButton(fondo, text="Annulla", fg_color="#4b5563", command=annulla).pack(side="right", padx=(8, 0))
        ctk.CTkButton(fondo, text="Continua", command=conferma).pack(side="right")
        self.wait_window(finestra)
        awards_selezionati = risultato["awards"]
        if not awards_selezionati:
            return

        staz = staz_from_qsos(self.qsos)
        nome = "Report_award_%s.pdf" % (staz or "ADIF_FZR")
        path = filedialog.asksaveasfilename(
            parent=self, title="Report award PDF", defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")], initialfile=nome)
        if not path:
            return
        try:
            build_award_report_pdf(path, self.qsos, awards_list=tuple(awards_selezionati))
        except Exception as ex:
            messagebox.showerror("Report award", "Errore:\n%s" % ex, parent=self)
            return
        if messagebox.askyesno("Report award", "PDF creato.\nAprirlo ora?", parent=self):
            try:
                apri_path((path))
            except Exception as ex:
                messagebox.showwarning("Report award",
                                       "PDF creato, ma non è stato possibile aprirlo automaticamente.\n%s" % ex,
                                       parent=self)

    def _award_row(self, parent, a, colore):
        kind = a["award"]
        # Click su una riga award -> apre la finestra Award COMPLETA sull'award
        # (matrici banda×modo, mappe, diplomi). Unico ingresso dalla Dashboard.
        cmd = (lambda k=kind: self._apri_award_completo(k))

        bordo = "#2c7be5" if cmd else "#223b55"
        card = ctk.CTkFrame(parent, corner_radius=10, fg_color="#0f1b2d",
                            border_width=1, border_color=bordo)
        card.pack(fill="x", pady=6)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 2))
        l1 = ctk.CTkLabel(top, text=kind + (" ▸" if cmd else ""), width=66, anchor="w",
                          font=ctk.CTkFont(size=15, weight="bold"), text_color=colore)
        l1.pack(side="left")
        l2 = ctk.CTkLabel(top, text=a["nome"], anchor="w",
                          font=ctk.CTkFont(size=11), text_color="#9fb6d4")
        l2.pack(side="left")
        tgt = a["target"] or max(a["worked"], 1)
        l3 = ctk.CTkLabel(top,
                          text=f"confermati {a['conf']} / {tgt}   ·   lavorati {a['worked']}",
                          anchor="e", font=ctk.CTkFont(size=11), text_color="#cdd9ea")
        l3.pack(side="right")
        pb = ctk.CTkProgressBar(card, height=16, progress_color=colore)
        pb.pack(fill="x", padx=14, pady=(2, 4))
        pb.set(min(1.0, a["conf"] / tgt) if tgt else 0)
        det = ctk.CTkLabel(card, text=f"LoTW {a['lotw']}   ·   eQSL {a['eqsl']}",
                           anchor="w", font=ctk.CTkFont(size=10), text_color="#8396b0")
        det.pack(anchor="w", padx=14, pady=(0, 10))
        if cmd:
            for w in (card, top, l1, l2, l3, det):
                try:
                    w.configure(cursor="hand2")
                except Exception:
                    pass
                w.bind("<Button-1>", lambda _e, c=cmd: c())
