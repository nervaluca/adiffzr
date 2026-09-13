# -*- coding: utf-8 -*-
"""
awards.py — Cruscotto Award per ADIF FZR.

Una sola finestra con selettore award in alto (WAS · DXCC · WAC · WAZ · VUCC);
ogni award mostra una matrice righe × bande colorata per livello di conferma
(LoTW / cartacea / eQSL / solo lavorato), con i tab modo
(Mixed / Phone / CW / Digitale / Satellite), lo switch "regola ufficiale",
tooltip e legenda. Resta in primo piano.

Riusa la logica di gui/was_status.py (nessuna dipendenza extra oltre a
customtkinter). Colloca il file in gui/ e aprilo passando i QSO in memoria:

    from gui.awards import AwardsWindow
    AwardsWindow(self, qsos=self.qsos_caricati)

I QSO sono dict con chiavi ADIF minuscole (state, dxcc, cont, cqz, gridsquare,
band, mode, prop_mode, sat_name, country, lotw_qsl_rcvd, eqsl_qsl_rcvd,
qsl_rcvd). Con struttura diversa passa un getter:  getter=lambda r,k: r.get(k)
"""

import re
from config import T

try:
    import tkinter as tk
    import customtkinter as ctk
except Exception:  # consente il test della logica senza GUI
    tk = None
    ctk = None

from gui.was_status import (
    BAND_ORDER, _default_getter, _newcell, _mode_group,
    cell_status, arrl_ok, any_cell,
    STATE_NAMES, US_STATES, US_DXCC,
)

try:  # mappe award stampabili (opzionale: se il modulo manca, il bottone avvisa)
    from gui.award_map import (render_svg as _map_svg,
                               statuses_from_model as _map_stats,
                               GRIDS as _MAP_GRIDS)
except Exception:
    _map_svg = None
    _MAP_GRIDS = {}

try:
    from gui.award_diploma import genera_sample_diploma as _gen_diploma
except Exception:
    _gen_diploma = None

# --------------------------------------------------------------------------- #
#  Dati di riferimento aggiuntivi
# --------------------------------------------------------------------------- #
CONT_NAMES = {'NA': 'Nord America', 'SA': 'Sud America', 'EU': 'Europa',
              'AF': 'Africa', 'AS': 'Asia', 'OC': 'Oceania'}
WAC_CONTS = ['NA', 'SA', 'EU', 'AF', 'AS', 'OC']       # WAC: 6 continenti
CQ_ZONES = [str(i) for i in range(1, 41)]              # WAZ: zone 1..40
VUCC_BANDS = ['6m', '2m', '70cm']                      # VHF/UHF presenti in BAND_ORDER

AWARDS = ['WAS', 'WAS250', 'DXCC', 'WAC', 'WAZ', 'VUCC', 'WPX', 'IOTA', 'USACA', 'WAJA']
AWARD_INFO = {
    'WAS':  ("Worked All States", "stati USA confermati", 50),
    'WAS250': ("ARRL America250 WAS", "50 stati USA · QSO 2026 · conferme LoTW", 50),
    'DXCC': ("DX Century Club", "entità DXCC confermate", 100),
    'WAC':  ("Worked All Continents", "continenti confermati", 6),
    'WAZ':  ("Worked All Zones (CQ)", "zone CQ confermate", 40),
    'VUCC': ("VHF/UHF Century Club", "griglie confermate (VHF+)", 100),
    'WPX':  ("CQ WPX", "prefissi confermati", 400),
    'IOTA': ("Islands On The Air", "riferimenti isola confermati", 100),
    'USACA': ("USA Counties Award", "contee USA confermate", 500),
    'WAJA': ("Worked All Japan Prefectures", "prefetture JA confermate", 47),
}
GROUPS = ['mixed', 'phone', 'cw', 'digital', 'sat']
GROUP_LABEL = {'mixed': 'Mixed', 'phone': 'Phone', 'cw': 'CW',
               'digital': 'Digitale', 'sat': 'Satellite'}


# --------------------------------------------------------------------------- #
#  Logica di calcolo (indipendente dalla GUI, testabile a parte)
# --------------------------------------------------------------------------- #
def _flags(g, r):
    lotw = str(g(r, 'lotw_qsl_rcvd') or '').upper() in ('V', 'Y')
    eqsl = str(g(r, 'eqsl_qsl_rcvd') or '').upper() == 'Y'
    paper = str(g(r, 'qsl_rcvd') or '').upper() == 'Y'
    return lotw, eqsl, paper


# ---- estrattori chiave per ciascun award: ritornano (id, etichetta) ---- #
def _kf_was(r, g):
    st = str(g(r, 'state') or '').upper().strip()
    if st not in US_STATES:
        return None, None
    if str(g(r, 'dxcc') or '').strip() not in US_DXCC:
        return None, None
    return st, STATE_NAMES[st]


def _kf_was250(r, g):
    """ARRL America250 WAS ('WAS-250'): come WAS ma valgono solo i QSO fatti
    nel 2026 (0000z 1/1 – 2359z 31/12), su qualsiasi banda. La conferma valida
    è via LoTW (colonna verde)."""
    if not str(g(r, 'qso_date') or '').strip().startswith('2026'):
        return None, None
    return _kf_was(r, g)


def _kf_wac(r, g):
    c = str(g(r, 'cont') or '').upper().strip()
    if c not in CONT_NAMES:
        return None, None
    return c, CONT_NAMES[c]


def _kf_waz(r, g):
    z = str(g(r, 'cqz') or '').strip()
    if not z:
        return None, None
    try:
        n = int(float(z))
    except Exception:
        return None, None
    if not (1 <= n <= 40):
        return None, None
    return str(n), f"Zona {n}"


def _kf_dxcc(r, g):
    d = str(g(r, 'dxcc') or '').strip()
    if not d or d in ('0',):
        return None, None
    lbl = str(g(r, 'country') or '').strip() or f"DXCC {d}"
    return d, lbl


def _kf_vucc(r, g):
    grid = str(g(r, 'gridsquare') or '').upper().strip()[:4]
    if len(grid) < 4:
        return None, None
    return grid, grid


_WPX_IGNORE = {'P', 'M', 'MM', 'AM', 'QRP', 'QRPP', 'LH', 'BCN', 'A'}


def _plain_prefix(call):
    """Prefisso WPX di un nominativo senza '/': lettere/numeri fino all'ultima
    cifra inclusa, scartando il suffisso finale (sole lettere). Senza cifra
    appende '0' (prefisso senza numero)."""
    call = (call or '').upper().strip()
    m = re.match(r'^([A-Z0-9]*\d)[A-Z]*$', call)
    if m:
        return m.group(1)
    if call and not call[-1].isdigit():
        return call + '0'
    return call


def _wpx_prefix(call):
    """Estrae il prefisso secondo le regole CQ WPX. Gestisce: portable con
    prefisso (PA/G3ZAY -> PA0), sostituzione del numero d'area (W8XYZ/4 -> W4),
    prefissi senza numero (+0), suffissi da ignorare (/P /M /MM /QRP ...)."""
    call = (call or '').upper().strip()
    if not call:
        return ''
    if '/' not in call:
        return _plain_prefix(call)
    parts = [p for p in call.split('/') if p]
    kept = [p for p in parts if p not in _WPX_IGNORE] or parts
    if len(kept) == 1:
        return _plain_prefix(kept[0])
    main = max(kept, key=len)
    other = min(kept, key=len)
    if other.isdigit():                         # /4 -> sostituisce il numero
        return re.sub(r'\d+$', other, _plain_prefix(main))
    if len(other) == 1:                         # singola lettera = designatore
        return _plain_prefix(main)
    base = other                                # 'other' e' un prefisso portable
    if not base[-1].isdigit():
        base += '0'
    return base


def _kf_wpx(r, g):
    px = _wpx_prefix(str(g(r, 'call') or ''))
    if not px:
        return None, None
    return px, px


def _kf_iota(r, g):
    io = str(g(r, 'iota') or '').upper().strip()
    if not io:
        return None, None
    m = re.match(r'^([A-Z]{2})[-\s]?(\d{1,3})$', io)
    if not m:
        return None, None
    ref = f"{m.group(1)}-{int(m.group(2)):03d}"   # normalizza EU25 / EU 025 -> EU-025
    return ref, ref


def _kf_cnty(r, g):
    """USA-CA: contea USA. Campo ADIF CNTY, formato 'ST,County'
    (già qualificato per stato: 'Franklin' esiste in decine di stati)."""
    cy = str(g(r, 'cnty') or '').upper().strip()
    if not cy:
        return None, None
    cy = cy.replace('/', ',').replace(';', ',')
    parts = [p.strip() for p in cy.split(',') if p.strip()]
    if len(parts) < 2:
        return None, None
    st, county = parts[0], ' '.join(parts[1:])
    if st not in US_STATES:
        return None, None
    ref = f"{st},{county.title()}"
    return ref, ref


# Prefetture giapponesi — codici JIS X 0401 / ISO 3166-2 (01..47, nord→sud),
# la numerazione legata ai codici postali e usata da LoTW quando il campo STATE
# è valorizzato per DXCC 339. NB: diversa dai codici JARL (Tokyo JARL=10).
JP_PREF = {
    '01': 'Hokkaido', '02': 'Aomori', '03': 'Iwate', '04': 'Miyagi',
    '05': 'Akita', '06': 'Yamagata', '07': 'Fukushima', '08': 'Ibaraki',
    '09': 'Tochigi', '10': 'Gunma', '11': 'Saitama', '12': 'Chiba',
    '13': 'Tokyo', '14': 'Kanagawa', '15': 'Niigata', '16': 'Toyama',
    '17': 'Ishikawa', '18': 'Fukui', '19': 'Yamanashi', '20': 'Nagano',
    '21': 'Gifu', '22': 'Shizuoka', '23': 'Aichi', '24': 'Mie',
    '25': 'Shiga', '26': 'Kyoto', '27': 'Osaka', '28': 'Hyogo',
    '29': 'Nara', '30': 'Wakayama', '31': 'Tottori', '32': 'Shimane',
    '33': 'Okayama', '34': 'Hiroshima', '35': 'Yamaguchi', '36': 'Tokushima',
    '37': 'Kagawa', '38': 'Ehime', '39': 'Kochi', '40': 'Fukuoka',
    '41': 'Saga', '42': 'Nagasaki', '43': 'Kumamoto', '44': 'Oita',
    '45': 'Miyazaki', '46': 'Kagoshima', '47': 'Okinawa',
}


def _kf_waja(r, g):
    """WAJA: prefettura giapponese. Scatta solo su DXCC 339, legge STATE.
    Interpreta il codice JIS/ISO 01..47; un codice fuori tabella viene mostrato
    grezzo (così un eventuale schema JARL è visibile a colpo d'occhio)."""
    if str(g(r, 'dxcc') or '').strip() != '339':
        return None, None
    st = str(g(r, 'state') or '').upper().strip().replace('JP-', '')
    if not st:
        return None, None
    if st.isdigit():
        code = f"{int(st):02d}"
        return code, JP_PREF.get(code, f"Pref {code}")
    name = (st.title().replace('-Ken', '').replace('-Fu', '')
            .replace('-To', '').replace('-Do', '').strip())
    return name, name


_KEYFN = {'WAS': _kf_was, 'WAS250': _kf_was250, 'WAC': _kf_wac, 'WAZ': _kf_waz,
          'DXCC': _kf_dxcc, 'VUCC': _kf_vucc,
          'WPX': _kf_wpx, 'IOTA': _kf_iota, 'USACA': _kf_cnty,
          'WAJA': _kf_waja}


def _compute_generic(qsos, keyfn, getter=_default_getter, fixed_rows=None,
                     row_order=None, row_labels=None, band_whitelist=None,
                     include_sat=True, target=100):
    """Motore comune: costruisce la matrice righe × bande + vista satellite.
    Ritorna una struttura pronta per la GUI (come compute_was, ma generica).

    Una riga viene creata solo se il QSO *conta davvero* (banda ammessa o
    satellite quando previsto): così VUCC non elenca griglie di QSO HF."""
    g = getter
    labels = {}
    terr = {'phone': {}, 'cw': {}, 'digital': {}}
    sat = {}
    sat_count = {}
    terr_bands = set()
    n_terr = n_sat = 0
    stations = {}   # rid -> [ {call,date,time,band,mode,grp,conf} ]

    def _cell(store, rid, col):
        return store.setdefault(rid, {}).setdefault(col, _newcell())

    def _conf(lotw, paper, eqsl):
        return 'lotw' if lotw else 'paper' if paper else 'eqsl' if eqsl else 'work'

    def _add_station(rid, r, grp, band, conf):
        stations.setdefault(rid, []).append({
            'call': str(g(r, 'call') or '').upper().strip(),
            'date': str(g(r, 'qso_date') or '').strip(),
            'time': str(g(r, 'time_on') or '').strip(),
            'band': band, 'mode': str(g(r, 'mode') or '').upper().strip(),
            'grp': grp, 'conf': conf})

    for r in qsos:
        rid, lbl = keyfn(r, g)
        if rid is None:
            continue
        if fixed_rows is not None and rid not in fixed_rows:
            continue
        lotw, eqsl, paper = _flags(g, r)

        if include_sat and str(g(r, 'prop_mode') or '').upper() == 'SAT':
            labels.setdefault(rid, lbl)
            sn = str(g(r, 'sat_name') or '').upper().strip() or '(sconosciuto)'
            c = _cell(sat, rid, sn)
            c['w'] += 1; c['l'] |= lotw; c['e'] |= eqsl; c['p'] |= paper
            sat_count[sn] = sat_count.get(sn, 0) + 1
            n_sat += 1
            _add_station(rid, r, 'sat', str(g(r, 'band') or '').lower().strip(),
                         _conf(lotw, paper, eqsl))
            continue

        band = str(g(r, 'band') or '').lower().strip()
        if band not in BAND_ORDER:
            continue
        if band_whitelist is not None and band not in band_whitelist:
            continue
        labels.setdefault(rid, lbl)
        terr_bands.add(band)
        grp = _mode_group(g(r, 'mode'))
        c = _cell(terr[grp], rid, band)
        c['w'] += 1; c['l'] |= lotw; c['e'] |= eqsl; c['p'] |= paper
        n_terr += 1
        _add_station(rid, r, grp, band, _conf(lotw, paper, eqsl))

    bands = [b for b in BAND_ORDER if b in terr_bands
             and (band_whitelist is None or b in band_whitelist)]

    if fixed_rows is not None:
        row_ids = list(row_order) if row_order else sorted(fixed_rows)
        rl = row_labels or {}
        rows = [(rid, rl.get(rid, labels.get(rid, rid))) for rid in row_ids]
    else:
        row_ids = sorted(labels, key=lambda i: (labels[i] or i))
        rows = [(rid, labels.get(rid, rid)) for rid in row_ids]

    def gc(grp, rid, b):
        return terr[grp].get(rid, {}).get(b) or _newcell()

    data = {'mixed': {rid: {b: any_cell([gc(grp, rid, b)
                                         for grp in ('phone', 'cw', 'digital')])
                            for b in bands} for rid, _ in rows}}
    for grp in ('phone', 'cw', 'digital'):
        data[grp] = {rid: {b: gc(grp, rid, b) for b in bands} for rid, _ in rows}

    sat_names = sorted(sat_count, key=lambda x: -sat_count[x])
    satfull = {rid: {sn: (sat.get(rid, {}).get(sn) or _newcell())
                     for sn in sat_names} for rid, _ in rows}

    return {'rows': rows, 'bands': bands, 'sat_names': sat_names,
            'data': data, 'sat': satfull, 'target': target,
            'total_terr': n_terr, 'total_sat': n_sat, 'total_log': len(qsos),
            'stations': stations}


def compute_award(qsos, kind, getter=_default_getter):
    """Calcola il modello per l'award richiesto (WAS/DXCC/WAC/WAZ/VUCC)."""
    kf = _KEYFN[kind]
    tgt = AWARD_INFO[kind][2]
    if kind in ('WAS', 'WAS250'):
        return _compute_generic(qsos, kf, getter, fixed_rows=US_STATES,
                                row_order=sorted(US_STATES),
                                row_labels=STATE_NAMES, target=tgt)
    if kind == 'WAC':
        return _compute_generic(qsos, kf, getter, fixed_rows=set(WAC_CONTS),
                                row_order=WAC_CONTS,
                                row_labels=CONT_NAMES, target=tgt)
    if kind == 'WAZ':
        return _compute_generic(qsos, kf, getter, fixed_rows=set(CQ_ZONES),
                                row_order=CQ_ZONES,
                                row_labels={z: f"Zona {z}" for z in CQ_ZONES},
                                target=tgt)
    if kind == 'VUCC':
        return _compute_generic(qsos, kf, getter, band_whitelist=set(VUCC_BANDS),
                                include_sat=False, target=tgt)
    # DXCC: solo entità lavorate, tutte le bande
    return _compute_generic(qsos, kf, getter, target=tgt)


# --------------------------------------------------------------------------- #
#  Export HTML / PDF (funzioni pure, indipendenti dalla GUI)
# --------------------------------------------------------------------------- #
_STAT_LETTER = {'lotw': 'L', 'paper': 'P', 'eqsl': 'e', 'work': '·', 'none': ''}
_STAT_HTML = {'lotw': '#1f7a3f', 'paper': '#2f8a52', 'eqsl': '#b5732a',
              'work': '#38455c', 'none': '#0f1826'}
_STAT_DESC = {'lotw': 'LoTW (valido)', 'paper': 'Cartacea (valido)',
              'eqsl': 'eQSL (non valido award)', 'work': 'Lavorato',
              'none': 'Non lavorato'}


# --- Estratto log: stazioni lavorate per entità (riferimento o tutte) ---
_CONF_RANK = {'lotw': 3, 'paper': 2, 'eqsl': 1, 'work': 0}
_CONF_LABEL = {'lotw': 'LoTW', 'paper': 'Cartacea', 'eqsl': 'eQSL', 'work': 'Lavorato'}


def _fmt_date(d):
    d = str(d or '').strip()
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d


def _extract_groups(group):
    if group == 'sat':
        return {'sat'}
    if group in ('phone', 'cw', 'digital'):
        return {group}
    return {'phone', 'cw', 'digital'}          # mixed = terrestre


def entity_extract(model, group, full=False, band=None):
    """Per ogni entità (in ordine riga) con almeno una stazione lavorata nella
    vista corrente, ritorna (rid, label, [stazioni], n_qso_totali).
    band: se valorizzata, considera solo le stazioni di quella banda (slice).
    full=False -> solo la QSO di riferimento (meglio confermata, poi più
    vecchia); full=True -> tutte le stazioni ordinate."""
    grset = _extract_groups(group)
    b = str(band).lower() if (band and group != 'sat') else None
    st = model.get('stations', {})
    out = []
    for rid, label in model['rows']:
        lst = [s for s in st.get(rid, [])
               if s['grp'] in grset and (b is None or str(s.get('band', '')).lower() == b)]
        if not lst:
            continue
        lst.sort(key=lambda s: (-_CONF_RANK.get(s['conf'], 0), s['date'], s['time']))
        out.append((rid, label, lst if full else lst[:1], len(lst)))
    return out


def _table_data(model, group, strict, band=None):
    """Ritorna (cols, righe) dove ogni riga = (id, label, [(stato,cella)...],
    (stato_all, cella_all)). Pura, riusabile per HTML e PDF.
    band: se valorizzata (es. '17m'), limita a quella singola banda (slice)."""
    if group == 'sat':
        cols = model['sat_names']
        if band and band in cols:
            cols = [band]
    elif band and band in model['bands']:
        cols = [band]
    else:
        cols = model['bands']

    def getcell(rid, c):
        if group == 'sat':
            return model['sat'][rid].get(c) or _newcell()
        return model['data'][group][rid][c]

    rows = []
    for rid, label in model['rows']:
        cells = [(cell_status(getcell(rid, c), strict), getcell(rid, c)) for c in cols]
        allc = any_cell([getcell(rid, c) for c in cols]) if cols else _newcell()
        rows.append((rid, label, cells, (cell_status(allc, strict), allc)))
    return cols, rows


def _award_valid(model, group, strict, band=None):
    _, rows = _table_data(model, group, strict, band)
    return sum(1 for _, _, _, (st, _c) in rows if st in ('lotw', 'paper'))


def build_award_html(award, group, model, strict=False, meta="", full_extract=False,
                     band=None):
    """Genera l'HTML autonomo (tema scuro) della vista award corrente."""
    fullname, sub, target = AWARD_INFO[award]
    cols, rows = _table_data(model, group, strict, band)
    valid = _award_valid(model, group, strict, band)
    gl = "Satellite" if group == 'sat' else group.capitalize()
    if band:
        gl += f" · {band}"
    all_hdr = "SAT" if group == 'sat' else "ALL"

    def esc(s):
        return (str(s).replace('&', '&amp;').replace('<', '&lt;')
                .replace('>', '&gt;'))

    th = "".join(f"<th>{esc(c)}</th>" for c in cols)
    body = []
    for rid, label, cells, (astat, _a) in rows:
        tds = []
        for stat, cell in cells:
            let = _STAT_LETTER[stat]
            title = f"{cell['w']} QSO" if cell['w'] else "non lavorato"
            tds.append(f'<td class="c" style="background:{_STAT_HTML[stat]}" '
                       f'title="{title}">{let}</td>')
        alet = _STAT_LETTER[astat]
        tds.append(f'<td class="c all" style="background:{_STAT_HTML[astat]}">{alet}</td>')
        body.append(f'<tr><td class="id">{esc(rid)}</td>'
                    f'<td class="nm">{esc(label)}</td>{"".join(tds)}</tr>')

    legend = "".join(
        f'<span class="lg"><i style="background:{_STAT_HTML[k]}"></i>{_STAT_DESC[k]}</span>'
        for k in ('lotw', 'paper', 'eqsl', 'work', 'none'))

    ext = entity_extract(model, group, full_extract, band)
    if ext:
        cap = ("tutte le stazioni lavorate per entita'" if full_extract
               else "stazione di riferimento per entita'")
        xr = []
        for rid, label, sts, cnt in ext:
            for i, s in enumerate(sts):
                idc = (f'<td class="id">{esc(rid)}</td><td class="nm">{esc(label)}</td>'
                       if i == 0 else '<td class="id"></td><td class="nm"></td>')
                ctc = f'<td class="ct">{cnt}</td>' if i == 0 else '<td class="ct"></td>'
                cf = s['conf']
                xr.append(
                    f'<tr>{idc}<td class="cs">{esc(s["call"])}</td>'
                    f'<td>{_fmt_date(s["date"])}</td><td>{esc(s["band"])}</td>'
                    f'<td>{esc(s["mode"])}</td>'
                    f'<td style="color:{_STAT_HTML[cf]};font-weight:700">'
                    f'{_CONF_LABEL[cf]}</td>{ctc}</tr>')
        extract_html = (
            f'<h2 class="xh">Estratto log &mdash; {cap} '
            f'<span class="xn">({len(ext)} entita\u0027)</span></h2>'
            f'<table class="xt"><thead><tr><th>Riga</th><th>Nome</th>'
            f'<th>Call</th><th>Data</th><th>Banda</th><th>Modo</th>'
            f'<th>Conferma</th><th>QSO</th></tr></thead>'
            f'<tbody>{"".join(xr)}</tbody></table>')
    else:
        extract_html = ""

    return f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(award)} — {esc(fullname)}</title>
<style>
 @media print{{*{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
 @page{{size:A4 landscape;margin:8mm}}
 body{{background:#0a111e;color:#e9eef8;font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0;padding:26px}}
 h1{{font-family:ui-monospace,Consolas,monospace;margin:0 0 2px;font-size:26px}}
 h1 b{{color:#4aa3ff}}
 .sub{{color:#93a6c4;margin:0 0 14px;font-size:14px}}
 .big{{font-family:ui-monospace,Consolas,monospace;font-size:34px;font-weight:700;color:#5fd08f}}
 table{{border-collapse:collapse;font-family:ui-monospace,Consolas,monospace;font-size:12px;margin-top:12px}}
 th{{color:#93a6c4;font-size:10px;letter-spacing:.06em;padding:6px 4px;border-bottom:1px solid #213048;text-transform:uppercase}}
 td.id{{color:#e9eef8;font-weight:700;padding:4px 8px}}
 td.nm{{color:#93a6c4;padding:4px 10px 4px 4px;white-space:nowrap}}
 td.c{{width:30px;height:22px;text-align:center;color:#dff;font-weight:700;border:1px solid #0a111e}}
 td.c.all{{border-left:2px solid #213048}}
 .legend{{margin-top:16px;color:#93a6c4;font-size:12px;display:flex;gap:16px;flex-wrap:wrap}}
 .lg{{display:inline-flex;align-items:center;gap:6px}}
 .lg i{{width:14px;height:14px;border-radius:3px;display:inline-block}}
 .meta{{color:#5f7392;font-size:11px;margin-top:10px}}
 h2.xh{{font-size:14px;margin:22px 0 6px;color:#cfe0ff;font-weight:700}}
 h2.xh .xn{{color:#5f7392;font-weight:400;font-size:12px}}
 table.xt{{font-size:11px}}
 table.xt td{{padding:3px 8px;border-bottom:1px solid #172236;white-space:nowrap}}
 table.xt td.cs{{color:#e9eef8;font-weight:700}}
 table.xt td.ct{{color:#93a6c4;text-align:right}}
</style></head><body>
 <h1><b>{esc(award)}</b> · {esc(fullname)}</h1>
 <p class="sub">{esc(sub)} — vista {esc(gl)}{' · regola ufficiale' if strict else ''}</p>
 <div class="big">{valid}/{target}</div>
 <table><thead><tr><th>Riga</th><th>Nome</th>{th}<th>{all_hdr}</th></tr></thead>
 <tbody>{''.join(body)}</tbody></table>
 <div class="legend">{legend}</div>
 {extract_html}
 <div class="meta">{esc(meta)}</div>
</body></html>"""


def build_award_pdf(path, award, group, model, strict=False, meta="", full_extract=False,
                    band=None):
    """Genera il PDF (reportlab) della vista award corrente, matrice colorata."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    fullname, sub, target = AWARD_INFO[award]
    cols, rows = _table_data(model, group, strict, band)
    valid = _award_valid(model, group, strict, band)
    all_hdr = "SAT" if group == 'sat' else "ALL"

    rl = {k: colors.HexColor(v) for k, v in _STAT_HTML.items()}
    styles = getSampleStyleSheet()
    h = ParagraphStyle('h', parent=styles['Title'], fontSize=16, spaceAfter=2)
    sN = ParagraphStyle('s', parent=styles['Normal'], fontSize=9,
                        textColor=colors.grey)
    h2 = ParagraphStyle('h2', parent=styles['Heading2'], fontSize=12,
                        spaceBefore=10, spaceAfter=4)

    header = ["Riga", "Nome"] + [str(c) for c in cols] + [all_hdr]
    data = [header]
    cell_bg = []
    for ri, (rid, label, cells, (astat, _a)) in enumerate(rows, start=1):
        line = [str(rid), (str(label)[:22])]
        for ci, (stat, cell) in enumerate(cells, start=2):
            line.append(_STAT_LETTER[stat])
            cell_bg.append(('BACKGROUND', (ci, ri), (ci, ri), rl[stat]))
        line.append(_STAT_LETTER[astat])
        cell_bg.append(('BACKGROUND', (len(header) - 1, ri),
                        (len(header) - 1, ri), rl[astat]))
        data.append(line)

    ncol = len(header)
    # Larghezze adattive: la tabella rientra SEMPRE nella pagina, qualunque sia
    # il numero di colonne (bande o satelliti). Le celle griglia si stringono se
    # sono tante; lo spazio in più (poche colonne) va alla colonna Nome.
    usable = landscape(A4)[0] - 24 * mm
    id_w = 11 * mm
    name_w = 32 * mm
    n_grid = max(1, ncol - 2)
    grid_w = (usable - id_w - name_w) / n_grid
    if grid_w > 9 * mm:
        grid_w = 9 * mm
        name_w = usable - id_w - grid_w * n_grid
    col_widths = [id_w, name_w] + [grid_w] * n_grid

    doc = SimpleDocTemplate(path, pagesize=landscape(A4),
                            leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm)
    elems = [Paragraph(f"{award} · {fullname} — {valid}/{target}", h),
             Paragraph(f"{sub} — vista {'Satellite' if group=='sat' else group.capitalize()}"
                       f"{' · regola ufficiale (solo LoTW e cartacea)' if strict else ''}", sN),
             Spacer(1, 6)]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    st = [
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('FONTSIZE', (2, 1), (-1, -1), 7),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16233c')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('TEXTCOLOR', (0, 1), (1, -1), colors.HexColor('#333333')),
        ('TEXTCOLOR', (2, 1), (-1, -1), colors.white),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#c9d3e0')),
        ('LINEAFTER', (-2, 0), (-2, -1), 1.2, colors.HexColor('#7a8aa0')),
        ('ROWBACKGROUNDS', (0, 1), (1, -1), [colors.white, colors.HexColor('#f2f5fa')]),
    ] + cell_bg
    t.setStyle(TableStyle(st))
    elems.append(t)

    # --- Estratto log: stazioni lavorate per entita' ---
    ext = entity_extract(model, group, full_extract, band)
    if ext:
        cap = ("tutte le stazioni per entita'" if full_extract
               else "stazione di riferimento per entita'")
        elems += [Spacer(1, 10),
                  Paragraph(f"Estratto log \u2014 {cap} ({len(ext)} entita\u0027)", h2)]
        ehdr = ["Riga", "Nome", "Call", "Data", "Banda", "Modo", "Conferma", "QSO"]
        edata = [ehdr]
        etc = []           # TEXTCOLOR per la colonna Conferma
        ri = 1
        for rid, label, sts, cnt in ext:
            for i, s in enumerate(sts):
                edata.append([
                    str(rid) if i == 0 else "",
                    (str(label)[:20] if i == 0 else ""),
                    s['call'], _fmt_date(s['date']), s['band'], s['mode'],
                    _CONF_LABEL[s['conf']], str(cnt) if i == 0 else ""])
                etc.append(('TEXTCOLOR', (6, ri), (6, ri), rl[s['conf']]))
                ri += 1
        ew = [12 * mm, 34 * mm, 26 * mm, 22 * mm, 16 * mm, 16 * mm, 24 * mm, 12 * mm]
        et = Table(edata, colWidths=ew, repeatRows=1)
        et.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16233c')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#1a1a1a')),
            ('FONTNAME', (2, 1), (2, -1), 'Helvetica-Bold'),
            ('ALIGN', (7, 1), (7, -1), 'RIGHT'),
            ('ALIGN', (3, 1), (5, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#c9d3e0')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.white, colors.HexColor('#f2f5fa')]),
        ] + etc))
        elems.append(et)
    if meta:
        elems += [Spacer(1, 8), Paragraph(meta, sN)]
    doc.build(elems)
    return path


# --------------------------------------------------------------------------- #
#  Finestra CustomTkinter
# --------------------------------------------------------------------------- #
if ctk is not None:
    from gui.was_status import (COL, LETTER, COL_W, ANY_W, ROW_H, HDR_H)
    ST_W = 210   # colonna riga più larga (nomi paese per DXCC)

    class AwardsWindow(ctk.CTkToplevel):
        def __init__(self, master=None, qsos=None, getter=_default_getter,
                     call="",
                     title="Award · WAS · DXCC · WAC · WAZ · VUCC · WPX · IOTA"):
            super().__init__(master)
            self.title(title)
            self.geometry("980x780")
            self.minsize(760, 560)
            self.resizable(True, True)

            # Deve restare sopra la SOLA finestra principale, non sopra ogni
            # applicazione. transient(master) fa esattamente questo; su Windows
            # però toglie i pulsanti Riduci/Ingrandisci, che ripristino via
            # ctypes subito dopo. Niente -topmost permanente (era il bug: la
            # finestra galleggiava sopra qualunque programma).
            if master is not None:
                try:
                    self.transient(master)
                except Exception:
                    pass
            self.after(150, self.lift)
            self.after(60, self._restore_caption_buttons)

            self._qsos = qsos or []
            self._getter = getter
            self._op_call = call or self._detect_call()
            self._models = {}          # cache per award
            self.award = 'WAS'
            self.group = 'mixed'
            self.strict = tk.BooleanVar(value=False)
            self.col_filter = None
            self._tip = None

            self._build()
            self._select_award('WAS')

        def _restore_caption_buttons(self):
            """Su Windows transient() rimuove i pulsanti Riduci/Ingrandisci:
            li ripristino modificando lo stile della finestra. Silenzioso e
            senza effetti su altri sistemi operativi."""
            try:
                import ctypes
                GWL_STYLE = -16
                WS_MINIMIZEBOX = 0x00020000
                WS_MAXIMIZEBOX = 0x00010000
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                SWP_FRAMECHANGED = 0x0020
                u = ctypes.windll.user32
                hwnd = u.GetParent(self.winfo_id())
                style = u.GetWindowLongW(hwnd, GWL_STYLE)
                u.SetWindowLongW(hwnd, GWL_STYLE,
                                 style | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
                u.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                               SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
                               | SWP_FRAMECHANGED)
            except Exception:
                pass

        def _detect_call(self):
            """Nominativo operatore più frequente nei QSO (station_callsign /
            operator / my_call), per intestare la mappa. Vuoto se assente."""
            from collections import Counter
            g, cnt = self._getter, Counter()
            for r in self._qsos:
                for k in ('station_callsign', 'operator', 'my_call'):
                    v = str(g(r, k) or '').upper().strip()
                    if v:
                        cnt[v] += 1
                        break
            return cnt.most_common(1)[0][0] if cnt else ""

        # ---- modello (cache) ---- #
        def _model(self):
            if self.award not in self._models:
                self._models[self.award] = compute_award(
                    self._qsos, self.award, self._getter)
            return self._models[self.award]

        # ---- costruzione layout ---- #
        def _build(self):
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(4, weight=1)

            # selettore AWARD
            selrow = ctk.CTkFrame(self, fg_color="transparent")
            selrow.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 2))
            self.awardsel = ctk.CTkSegmentedButton(
                selrow, values=AWARDS, command=self._select_award)
            self.awardsel.set('WAS')
            self.awardsel.pack(side="left")

            # Sample diploma (anteprima) in alto a destra, click per salvarlo.
            if _gen_diploma is not None:
                self.lbl_diploma = ctk.CTkLabel(selrow, text="", cursor="hand2")
                self.lbl_diploma.pack(side="right", padx=(8, 0))
                self.lbl_diploma.bind("<Button-1>", lambda e: self._salva_diploma())
                self._aggiorna_diploma()

            # pannello riepilogo
            top = ctk.CTkFrame(self, fg_color=COL['panel'], corner_radius=12)
            top.grid(row=1, column=0, sticky="ew", padx=12, pady=(6, 6))
            top.grid_columnconfigure(1, weight=1)
            self.big = ctk.CTkLabel(top, text="--/--",
                                    font=ctk.CTkFont(size=40, weight="bold"),
                                    text_color=COL['lcd'])
            self.big.grid(row=0, column=0, rowspan=2, padx=(18, 14), pady=14)
            self.big_lbl = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=13),
                                        text_color=COL['muted'], anchor="w")
            self.big_lbl.grid(row=0, column=1, sticky="sw", pady=(16, 0))
            self.meta = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=12),
                                     text_color=COL['muted'], anchor="w",
                                     justify="left")
            self.meta.grid(row=1, column=1, sticky="nw", pady=(0, 14))

            # controlli: tab modi + switch
            ctrl = ctk.CTkFrame(self, fg_color="transparent")
            ctrl.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))
            self.tabs = ctk.CTkSegmentedButton(
                ctrl, values=[GROUP_LABEL[g] for g in GROUPS],
                command=self._on_tab)
            self.tabs.set(GROUP_LABEL[self.group])
            self.tabs.pack(side="left")
            # Selettore banda per mappa/export (slice, es. 17m). "Tutte" = aggregato.
            try:
                _bande = list(self._model()['bands'])
            except Exception:
                _bande = []
            self.band_lbl = ctk.CTkLabel(ctrl, text=T("lbl_banda"),
                                         font=ctk.CTkFont(size=11))
            self.band_lbl.pack(side="left", padx=(12, 2))
            self.map_band = ctk.StringVar(value=T("opt_tutte"))
            self.band_menu = ctk.CTkOptionMenu(ctrl, variable=self.map_band,
                              values=[T("opt_tutte")] + _bande, width=110, height=28,
                              command=lambda _v: None)
            self.band_menu.pack(side="left")
            self._aggiorna_selettore_banda()
            ctk.CTkSwitch(ctrl, text=T("sw_regola_uff"),
                          variable=self.strict, command=self._render,
                          onvalue=True, offvalue=False).pack(side="left", padx=16)
            ctk.CTkButton(ctrl, text="⭳ PDF", width=70,
                          command=self._export_pdf).pack(side="right", padx=(6, 0))
            ctk.CTkButton(ctrl, text="⭳ HTML", width=76,
                          command=self._export_html).pack(side="right", padx=6)
            ctk.CTkButton(ctrl, text=T("btn_mappa"), width=84,
                          command=self._export_map).pack(side="right", padx=6)

            # striscia colonne (endorsement per banda / satellite)
            self.strip = ctk.CTkScrollableFrame(self, height=58,
                                                fg_color="transparent",
                                                orientation="horizontal")
            self.strip.grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 4))

            # matrice: header fisso + canvas scrollabile
            matwrap = ctk.CTkFrame(self, fg_color=COL['panel2'], corner_radius=12)
            matwrap.grid(row=4, column=0, sticky="nsew", padx=12, pady=(2, 6))
            matwrap.grid_columnconfigure(0, weight=1)
            matwrap.grid_rowconfigure(1, weight=1)
            self.hdr = tk.Canvas(matwrap, height=HDR_H, bg=COL['panel'],
                                 highlightthickness=0)
            self.hdr.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
            self.body = tk.Canvas(matwrap, bg=COL['panel2'], highlightthickness=0)
            self.body.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
            sb = ctk.CTkScrollbar(matwrap, command=self.body.yview)
            sb.grid(row=1, column=1, sticky="ns", pady=(0, 6))
            self.body.configure(yscrollcommand=sb.set)
            self.body.bind("<Motion>", self._hover)
            self.body.bind("<Leave>", lambda e: self._hide_tip())
            self.body.bind("<MouseWheel>",
                           lambda e: self.body.yview_scroll(int(-e.delta / 120), "units"))

            # legenda
            leg = ctk.CTkFrame(self, fg_color="transparent")
            leg.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 12))
            for key, txt in [('lotw', 'LoTW · valido'),
                             ('paper', 'Cartacea · valido'),
                             ('eqsl', 'eQSL · non valido award'),
                             ('work', 'Lavorato'),
                             ('none', 'Non lavorato')]:
                item = ctk.CTkFrame(leg, fg_color="transparent")
                item.pack(side="left", padx=(0, 14))
                sw = tk.Canvas(item, width=14, height=14, highlightthickness=0,
                               bg=COL[key])
                sw.pack(side="left", padx=(0, 5))
                ctk.CTkLabel(item, text=txt, font=ctk.CTkFont(size=11),
                             text_color=COL['muted']).pack(side="left")

        # ---- eventi ---- #
        def _select_award(self, name):
            self.award = name
            self.awardsel.set(name)
            self.group = 'mixed'
            self.tabs.set(GROUP_LABEL['mixed'])
            self.col_filter = None
            self._aggiorna_selettore_banda()
            self._aggiorna_diploma()
            self._render()

        def _aggiorna_diploma(self):
            """Rigenera l'anteprima del diploma campione per l'award corrente."""
            if _gen_diploma is None or not hasattr(self, 'lbl_diploma'):
                return
            try:
                fullname, sub, target = AWARD_INFO[self.award]
                img = _gen_diploma(fullname, sub, target, self._op_call or "",
                                   scale=0.30)
                w, h = img.size
                self._diploma_ctk = ctk.CTkImage(light_image=img, dark_image=img,
                                                 size=(w, h))
                self.lbl_diploma.configure(image=self._diploma_ctk)
            except Exception:
                pass

        def _salva_diploma(self):
            if _gen_diploma is None:
                return
            from tkinter import filedialog, messagebox
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension=".png",
                initialfile=f"diploma_{self.award}.png",
                filetypes=[("Immagine PNG", "*.png"), ("Tutti i file", "*.*")])
            if not path:
                return
            try:
                fullname, sub, target = AWARD_INFO[self.award]
                img = _gen_diploma(fullname, sub, target, self._op_call or "",
                                   scale=1.6)
                img.save(path)
                messagebox.showinfo("Diploma", f"Diploma campione salvato:\n{path}",
                                    parent=self)
            except Exception as ex:
                messagebox.showerror(T("hdr_diploma"), T("err_diploma", ex=ex),
                                     parent=self)

        def _on_tab(self, label):
            for g, lab in GROUP_LABEL.items():
                if lab == label:
                    self.group = g
                    break
            self.col_filter = None
            self._aggiorna_selettore_banda()
            self._render()

        def _aggiorna_selettore_banda(self):
            """In vista Satellite il selettore elenca i satelliti; altrove le bande."""
            if not hasattr(self, 'band_menu'):
                return
            m = self._model()
            if self.group == 'sat':
                vals = list(m.get('sat_names', []))
                self.band_lbl.configure(text=T("lbl_satellite"))
            else:
                vals = list(m.get('bands', []))
                self.band_lbl.configure(text=T("lbl_banda"))
            self.band_menu.configure(values=[T("opt_tutte")] + vals)
            self.map_band.set(T("opt_tutte"))

        def _toggle_filter(self, col):
            self.col_filter = None if self.col_filter == col else col
            self._render()

        # ---- colonne correnti ---- #
        def _cols(self):
            m = self._model()
            return m['sat_names'] if self.group == 'sat' else m['bands']

        def _rows(self):
            return self._model()['rows']

        def _cell(self, rid, col):
            m = self._model()
            if self.group == 'sat':
                return m['sat'][rid].get(col) or _newcell()
            return m['data'][self.group][rid][col]

        def _any(self, rid):
            return any_cell([self._cell(rid, c) for c in self._cols()])

        # ---- rendering ---- #
        def _render(self):
            m = self._model()
            strict = self.strict.get()
            cols = self._cols()
            rows = self._rows()
            target = m['target']
            fullname, sub, _ = AWARD_INFO[self.award]

            valid = sum(1 for rid, _ in rows if arrl_ok(self._any(rid)))
            worked = sum(1 for rid, _ in rows if self._any(rid)['w'] > 0)
            self.big.configure(text=f"{valid}/{target}")
            gl = ("WAS Satellite" if (self.award == 'WAS' and self.group == 'sat')
                  else f"vista {GROUP_LABEL[self.group]}")
            self.big_lbl.configure(text=f"{fullname} — {sub} · {gl}")
            self.meta.configure(
                text=(f"Lavorate: {worked}  ·  Confermate: {valid}/{target}  ·  "
                      f"Log: {m['total_terr']} terrestri + {m['total_sat']} sat "
                      f"({m['total_log']} tot)  ·  righe: {len(rows)}"))

            for w in self.strip.winfo_children():
                w.destroy()
            # chip TOTALE: unione su tutte le colonne (in sat = somma tra i sat)
            tfull = (valid >= target)
            tot = ctk.CTkButton(
                self.strip, width=104, height=44,
                fg_color=("#12321f" if tfull else COL['panel']),
                hover_color=COL['panel2'], border_width=2,
                border_color=(COL['lotw'] if tfull else COL['muted']),
                corner_radius=8, command=lambda: self._toggle_filter(None),
                text=f"TOT · lav {worked}\nconf {valid}/{target}",
                font=ctk.CTkFont(family="JetBrains Mono", size=11, weight="bold"),
                text_color=(COL['lotw'] if tfull else COL['txt']))
            tot.pack(side="left", padx=(0, 10), pady=4)
            for col in cols:
                ok = sum(1 for rid, _ in rows if arrl_ok(self._cell(rid, col)))
                full = (ok >= target)
                border = COL['lotw'] if full else COL['grid']
                fg = "#12321f" if full else COL['panel']
                sel = (self.col_filter == col)
                chip = ctk.CTkButton(
                    self.strip, width=78, height=44,
                    fg_color=fg, hover_color=COL['panel2'],
                    border_width=2,
                    border_color=("#c8452e" if sel else border),
                    corner_radius=8, command=lambda c=col: self._toggle_filter(c),
                    text=f"{col}\n{ok}/{target}",
                    font=ctk.CTkFont(family="JetBrains Mono", size=11, weight="bold"),
                    text_color=COL['lotw'] if full else COL['txt'])
                chip.pack(side="left", padx=3, pady=4)

            self._draw_header(cols)
            self._draw_body(cols, rows, strict)

        def _draw_header(self, cols):
            c = self.hdr
            c.delete("all")
            x = ST_W
            c.create_text(12, HDR_H / 2, text="Riga", anchor="w",
                          fill=COL['muted'], font=("JetBrains Mono", 10, "bold"))
            for col in cols:
                dim = self.col_filter and self.col_filter != col
                c.create_text(x + COL_W / 2, HDR_H / 2, text=str(col),
                              fill=(COL['grid'] if dim else COL['muted']),
                              font=("JetBrains Mono", 9, "bold"))
                x += COL_W
            any_hdr = "SAT" if self.group == 'sat' else "ALL"
            c.create_rectangle(x, 0, x + ANY_W, HDR_H, fill="#20272f", outline="")
            c.create_text(x + ANY_W / 2, HDR_H / 2, text=any_hdr,
                          fill=COL['muted'], font=("JetBrains Mono", 9, "bold"))
            total_w = ST_W + len(cols) * COL_W + ANY_W
            c.configure(scrollregion=(0, 0, total_w, HDR_H))

        def _draw_body(self, cols, rows, strict):
            c = self.body
            c.delete("all")
            self._cellmap = {}
            total_w = ST_W + len(cols) * COL_W + ANY_W
            total_h = max(1, len(rows)) * ROW_H

            for ri, (rid, label) in enumerate(rows):
                y = ri * ROW_H
                rid_s = str(rid)
                lab = str(label)
                if lab == rid_s:
                    # id già completo (award a set aperto): una sola scritta
                    disp = rid_s if len(rid_s) <= 26 else rid_s[:25] + "…"
                    c.create_text(12, y + ROW_H / 2, text=disp, anchor="w",
                                  fill=COL['txt'],
                                  font=("JetBrains Mono", 10, "bold"))
                else:
                    # codice breve (grassetto) + nome esteso (attenuato)
                    c.create_text(12, y + ROW_H / 2, text=rid_s, anchor="w",
                                  fill=COL['txt'],
                                  font=("JetBrains Mono", 10, "bold"))
                    if len(lab) > 24:
                        lab = lab[:23] + "…"
                    c.create_text(58, y + ROW_H / 2, text=lab, anchor="w",
                                  fill=COL['muted'], font=("Segoe UI", 9))
                x = ST_W
                for col in cols:
                    cell = self._cell(rid, col)
                    stat = cell_status(cell, strict)
                    dim = self.col_filter and self.col_filter != col
                    fill = COL['none'] if dim else COL[stat]
                    c.create_rectangle(x, y, x + COL_W, y + ROW_H,
                                       fill=fill, outline=COL['panel2'], width=1)
                    if LETTER[stat] and not dim:
                        c.create_text(x + COL_W / 2, y + ROW_H / 2, text=LETTER[stat],
                                      fill=COL['celltxt'],
                                      font=("JetBrains Mono", 9, "bold"))
                    self._cellmap[(x, y)] = (rid, label, col, cell)
                    x += COL_W
                acell = self._any(rid)
                astat = cell_status(acell, strict)
                c.create_rectangle(x, y, x + ANY_W, y + ROW_H,
                                   fill=COL[astat], outline=COL['panel'], width=1)
                if LETTER[astat]:
                    c.create_text(x + ANY_W / 2, y + ROW_H / 2, text=LETTER[astat],
                                  fill=COL['celltxt'],
                                  font=("JetBrains Mono", 9, "bold"))
                alabel = "qualsiasi sat" if self.group == 'sat' else "tutte le bande"
                self._cellmap[(x, y)] = (rid, label, alabel, acell)

            c.configure(scrollregion=(0, 0, total_w, total_h))
            self._cols_x = [ST_W + i * COL_W for i in range(len(cols))] + \
                           [ST_W + len(cols) * COL_W]

        # ---- tooltip ---- #
        def _hover(self, e):
            x = self.body.canvasx(e.x)
            y = self.body.canvasy(e.y)
            if x < ST_W:
                self._hide_tip(); return
            ri = int(y // ROW_H)
            col_x = None
            for cx in getattr(self, '_cols_x', []):
                w = ANY_W if cx == self._cols_x[-1] else COL_W
                if cx <= x < cx + w:
                    col_x = cx; break
            if col_x is None:
                self._hide_tip(); return
            info = self._cellmap.get((col_x, ri * ROW_H))
            if not info or not info[3]['w']:
                self._hide_tip(); return
            rid, label, col, cell = info
            txt = (f"{rid} · {label} · {col}\n"
                   f"QSO: {cell['w']}    "
                   f"LoTW: {'si' if cell['l'] else '—'}   "
                   f"Cart: {'si' if cell['p'] else '—'}   "
                   f"eQSL: {'si' if cell['e'] else '—'}")
            self._show_tip(e.x_root, e.y_root, txt)

        def _show_tip(self, xr, yr, txt):
            if self._tip is None:
                self._tip = tk.Toplevel(self)
                self._tip.wm_overrideredirect(True)
                self._tip.attributes("-topmost", True)
                self._tiplbl = tk.Label(self._tip, justify="left",
                                        bg=COL['panel'], fg=COL['txt'],
                                        font=("JetBrains Mono", 9),
                                        padx=8, pady=5, bd=1, relief="solid")
                self._tiplbl.pack()
            self._tiplbl.configure(text=txt)
            self._tip.wm_geometry(f"+{xr + 14}+{yr + 14}")
            self._tip.deiconify()

        def _hide_tip(self):
            if self._tip is not None:
                self._tip.withdraw()

        # ---- export ---- #
        def _meta_text(self):
            import datetime
            m = self._model()
            return (f"ADIF FZR · cruscotto Award · generato il "
                    f"{datetime.datetime.now():%Y-%m-%d %H:%M} · "
                    f"log: {m['total_terr']} QSO terrestri + {m['total_sat']} sat "
                    f"({m['total_log']} totali)")

        def _band_sel(self):
            """Banda selezionata per mappa/export, o None se 'Tutte'."""
            b = self.map_band.get() if hasattr(self, 'map_band') else 'Tutte'
            return None if b in ('', T("opt_tutte")) else b

        def _export_html(self):
            from tkinter import filedialog, messagebox
            band = self._band_sel()
            suff = f"_{band}" if band else ""
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension=".html",
                initialfile=f"{self.award}_{self.group}{suff}.html",
                filetypes=[("HTML", "*.html"), ("Tutti i file", "*.*")])
            if not path:
                return
            try:
                html = build_award_html(self.award, self.group, self._model(),
                                        self.strict.get(), self._meta_text(),
                                        band=band)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(html)
                messagebox.showinfo(T("hdr_export"), T("msg_html_ok", f=path), parent=self)
            except Exception as ex:
                messagebox.showerror(T("hdr_export"), T("err_html", ex=ex),
                                     parent=self)

        def _export_pdf(self):
            from tkinter import filedialog, messagebox
            band = self._band_sel()
            suff = f"_{band}" if band else ""
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension=".pdf",
                initialfile=f"{self.award}_{self.group}{suff}.pdf",
                filetypes=[("PDF", "*.pdf"), ("Tutti i file", "*.*")])
            if not path:
                return
            try:
                build_award_pdf(path, self.award, self.group, self._model(),
                                self.strict.get(), self._meta_text(), band=band)
                messagebox.showinfo(T("hdr_export"), T("msg_pdf_ok", f=path), parent=self)
            except Exception as ex:
                messagebox.showerror(T("hdr_export"), T("err_pdf", ex=ex),
                                     parent=self)

        def _export_map(self):
            from tkinter import filedialog, messagebox
            if _map_svg is None:
                messagebox.showerror(T("hdr_mappa"), T("err_map_mod"),
                                     parent=self)
                return
            if self.award not in _MAP_GRIDS:
                disponibili = ", ".join(_MAP_GRIDS)
                messagebox.showinfo(
                    T("hdr_mappa"),
                    T("msg_map_nogrid", d=disponibili, a=self.award),
                    parent=self)
                return
            m = self._model()
            strict = self.strict.get()
            rows = self._rows()
            target = m['target']
            band = self._band_sel()
            valid = sum(1 for rid, _ in rows if arrl_ok(self._any(rid)))
            worked = sum(1 for rid, _ in rows if self._any(rid)['w'] > 0)
            fullname, _sub, _ = AWARD_INFO[self.award]
            statuses = _map_stats(m, strict, any_cell, cell_status, _newcell,
                                  group=self.group, band=band)
            # Con uno slice (banda/modo) ricalcolo worked/valid su quello slice.
            slice_lbl = GROUP_LABEL[self.group] + (f" · {band}" if band else "")
            if band or self.group != 'mixed':
                worked = sum(1 for _rid, (stt, nq) in statuses.items() if nq > 0)
                valid = sum(1 for _rid, (stt, _n) in statuses.items()
                            if stt in ('lotw', 'paper'))
            names = STATE_NAMES if self.award in ('WAS', 'WAS250') else None
            svg = _map_svg(
                self.award, statuses,
                title=(f"{self._op_call} — {fullname}" if self._op_call
                       else fullname),
                subtitle=T("map_sub", w=worked, v=valid, t=target, s=slice_lbl),
                names=names, footer=self._meta_text())
            band_suff = f"_{band}" if band else ""
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension=".svg",
                initialfile=f"mappa_{self.award}_{self.group}{band_suff}.svg",
                filetypes=[("SVG", "*.svg"), ("Tutti i file", "*.*")])
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(svg)
            except Exception as ex:
                messagebox.showerror(T("hdr_mappa"), T("err_map_save", ex=ex),
                                     parent=self)
                return
            if messagebox.askyesno(
                    "Mappa",
                    f"SVG salvato:\n{path}\n\nAprirlo nel browser per stamparlo?",
                    parent=self):
                import webbrowser
                webbrowser.open(f"file://{path}")


# --------------------------------------------------------------------------- #
#  Avvio autonomo per test:  python awards.py path\log.adi
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys
    from gui.was_status import parse_adif
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if ctk is None:
        raise SystemExit("customtkinter non installato.")
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.withdraw()
    qsos = parse_adif(path) if path else []
    AwardsWindow(root, qsos=qsos)
    root.mainloop()
