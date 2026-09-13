"""Allineamento del log locale ai dati LoTW ("Allinea log a LoTW").

LoTW, per i QSO CONFERMATI, deriva dal certificato della stazione che
conferma i campi di location (DXCC, zone, locator, stato/contea, IOTA).
Questi sono spesso proprio i campi mancanti o sbagliati nel log, e sono
quelli che contano per gli award (WAZ, VUCC, WAS/USACA...).

Questo modulo e' PURO (niente GUI): scarica -> confronta -> costruisce un
DIFF -> applica solo su conferma. I campi da importare e la politica di
scrittura sono personalizzabili.

Flusso tipico:
    testo = LotwDownloader(...).download(qsl_detail=True)[1]
    scaricati = parse_lotw_adif(testo)
    diff, stats = calcola_allineamento(app.qsos_caricati, scaricati,
                                       campi_scelti, politiche)
    # mostra l'anteprima all'utente...
    n = applica_allineamento(diff)   # muta i dict del log

Nota: i normalizzatori modo/banda replicano quelli di
gui.dialogs.online_dialogs (_merge_download_in_log) per garantire lo
STESSO matching. In un refactoring futuro conviene spostarli in un unico
modulo condiviso.
"""

import adif_io


# --------------------------------------------------------------------------- #
#  Catalogo campi importabili da LoTW (con qso_qsldetail=yes) e politica di
#  scrittura di default. L'utente puo' cambiare selezione e politica.
#    'overwrite' -> scrive sempre (LoTW autorevole)
#    'fill'      -> scrive solo se il campo locale e' vuoto
#    'skip'      -> non tocca il campo
# --------------------------------------------------------------------------- #
CAMPI_LOTW = [
    # (campo_adif, etichetta, politica_default)
    ('dxcc',       'Entita\u0300 DXCC (n.)',   'overwrite'),
    ('country',    'Nome paese',               'overwrite'),
    ('pfx',        'Prefisso WPX',             'overwrite'),
    ('cont',       'Continente',               'overwrite'),
    ('cqz',        'Zona CQ',                  'overwrite'),
    ('ituz',       'Zona ITU',                 'overwrite'),
    ('state',      'Stato/Provincia',          'overwrite'),
    ('cnty',       'Contea (USACA)',           'overwrite'),
    ('gridsquare', 'Locator',                  'fill'),   # non declassare 6->4
    ('iota',       'Riferimento IOTA',         'fill'),   # da LoTW e' parziale
]

_POLITICHE = ('overwrite', 'fill', 'skip')


def politiche_default():
    """Ritorna il dizionario {campo: politica} di default."""
    return {c: pol for c, _lbl, pol in CAMPI_LOTW}


def campi_default():
    """Campi selezionati di default (tutti tranne quelli in 'skip')."""
    return [c for c, _lbl, pol in CAMPI_LOTW if pol != 'skip']


# --------------------------------------------------------------------------- #
#  Normalizzatori per il matching (identici a online_dialogs._merge_...)
# --------------------------------------------------------------------------- #
def _norm_modo(modo, submode=""):
    m = str(modo).upper().strip()
    s = str(submode).upper().strip()
    if m == "MFSK" and s in ("FT4", "FT8", "FT2", "JS8", "VARA"):
        return s
    if m in ("USB", "LSB", "AM", "FM"):
        return "SSB" if m in ("USB", "LSB") else m
    return m


_FREQ_RANGES = [
    (0.1357, 0.1378, "2190M"), (0.472, 0.479, "630M"),
    (1.8, 2.0, "160M"), (3.5, 4.0, "80M"), (5.0, 5.5, "60M"),
    (7.0, 7.3, "40M"), (10.1, 10.15, "30M"), (14.0, 14.35, "20M"),
    (18.068, 18.168, "17M"), (21.0, 21.45, "15M"),
    (24.89, 24.99, "12M"), (28.0, 29.7, "10M"), (50.0, 54.0, "6M"),
    (70.0, 71.0, "4M"), (144.0, 148.0, "2M"), (222.0, 225.0, "1.25M"),
    (420.0, 450.0, "70CM"), (902.0, 928.0, "33CM"),
    (1240.0, 1300.0, "23CM"), (2300.0, 2450.0, "13CM"),
    (3300.0, 3500.0, "9CM"), (5650.0, 5925.0, "6CM"),
    (10000.0, 10500.0, "3CM"),
]


def _banda_da_freq(freq):
    try:
        f = float(str(freq or "").replace(",", ".").strip())
    except Exception:
        return ""
    for low, high, band in _FREQ_RANGES:
        if low <= f <= high:
            return band
    return ""


def _banda(qso):
    band = str(qso.get('band', '') or qso.get('BAND', '')).upper().strip()
    return band or _banda_da_freq(qso.get('freq', '') or qso.get('FREQ', ''))


def _date_vicine(d1, d2, tolleranza_giorni=1):
    try:
        from datetime import datetime as _dt
        t1 = _dt.strptime(str(d1).strip(), "%Y%m%d")
        t2 = _dt.strptime(str(d2).strip(), "%Y%m%d")
        return abs((t1 - t2).days) <= tolleranza_giorni
    except Exception:
        return str(d1).strip() == str(d2).strip()


def _chiave(qso):
    modo = _norm_modo(qso.get('mode', '') or qso.get('MODE', ''),
                      qso.get('submode', '') or qso.get('SUBMODE', ''))
    return (
        str(qso.get('call', '') or qso.get('CALL', '')).upper().strip(),
        str(qso.get('qso_date', '') or qso.get('QSO_DATE', '')).strip(),
        _banda(qso),
        modo,
    )


# --------------------------------------------------------------------------- #
#  Parsing dell'ADIF scaricato da LoTW (chiavi minuscole, come nel log app)
# --------------------------------------------------------------------------- #
def parse_lotw_adif(testo):
    """Parsa il testo ADIF di LoTW e ritorna una lista di dict a chiavi
    minuscole (coerenti con qsos_caricati)."""
    if not testo or not testo.strip():
        return []
    try:
        records, _hdr = adif_io.read_from_string(testo)
    except Exception:
        return []
    out = []
    for rec in records:
        out.append({str(k).lower(): str(v) for k, v in rec.items()})
    return out


# --------------------------------------------------------------------------- #
#  Confronto: costruisce il DIFF senza mutare nulla
# --------------------------------------------------------------------------- #
def _valore_locale(qso, campo):
    return str(qso.get(campo, '') or qso.get(campo.upper(), '')).strip()


def _decidi(vecchio, nuovo, politica):
    """Ritorna il nuovo valore da scrivere, oppure None se non si cambia."""
    nuovo = str(nuovo or '').strip()
    if not nuovo or politica == 'skip':
        return None
    if nuovo.upper() == str(vecchio or '').strip().upper():
        return None                       # gia' uguale (ignora maiuscole)
    if politica == 'fill' and str(vecchio or '').strip():
        return None                       # 'fill' non sovrascrive
    return nuovo


def calcola_allineamento(app_qsos, scaricati, campi, politiche):
    """Confronta il log con i record LoTW e ritorna (diff, stats).

    diff: lista di dict {qso, call, data, banda, campo, old, new}
          (qso = riferimento al dict nel log, NON ancora modificato)
    stats: {'match': n_qso_locali_agganciati, 'modifiche': n_celle_da_cambiare,
            'senza_match': n_record_lotw_senza_corrispondenza,
            'per_campo': {campo: conteggio}}
    """
    campi = [c for c in campi if politiche.get(c, 'skip') != 'skip']

    indice = {}
    for q in app_qsos:
        call, data, band, modo = _chiave(q)
        if call and data:
            indice.setdefault(call, []).append((data, band, modo, q))

    diff = []
    per_campo = {}
    qso_agganciati = set()
    senza_match = 0

    for rec in scaricati:
        call_d, data_d, band_d, modo_d = _chiave(rec)
        candidati = indice.get(call_d, [])

        corr = [q for (dl, bl, ml, q) in candidati
                if dl == data_d and bl == band_d and ml == modo_d]
        if not corr:
            corr = [q for (dl, bl, ml, q) in candidati
                    if bl == band_d and ml == modo_d and _date_vicine(dl, data_d)]
        if not corr:
            senza_match += 1
            continue

        for q in corr:
            qso_agganciati.add(id(q))
            for campo in campi:
                nuovo = _decidi(_valore_locale(q, campo),
                                rec.get(campo, ''), politiche.get(campo, 'skip'))
                if nuovo is None:
                    continue
                diff.append({
                    'qso': q,
                    'call': call_d, 'data': data_d, 'banda': band_d,
                    'campo': campo,
                    'old': _valore_locale(q, campo),
                    'new': nuovo,
                })
                per_campo[campo] = per_campo.get(campo, 0) + 1

    stats = {
        'match': len(qso_agganciati),
        'modifiche': len(diff),
        'senza_match': senza_match,
        'per_campo': per_campo,
    }
    return diff, stats


def applica_allineamento(diff):
    """Applica il diff: scrive i valori nei dict del log. Ritorna il numero
    di celle modificate. Chiamare DOPO conferma dell'utente (e dopo aver
    salvato lo stato per l'undo)."""
    n = 0
    for d in diff:
        d['qso'][d['campo']] = d['new']
        n += 1
    return n


def salva_preset(path, campi, politiche, last_qsl=""):
    """Salva selezione campi + politiche + data ultimo sync in JSON."""
    import json
    dati = {'campi': list(campi), 'politiche': dict(politiche),
            'last_qsl': str(last_qsl or '')}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)


def carica_preset(path):
    """Carica il preset; se manca, ritorna i default. Ritorna
    (campi, politiche, last_qsl)."""
    import json
    pol = politiche_default()
    campi = campi_default()
    last = ""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
        campi = d.get('campi', campi)
        pol.update(d.get('politiche', {}))
        last = d.get('last_qsl', "")
    except Exception:
        pass
    return campi, pol, last
