"""
Parser cty.dat (AD1C / bigcty) + bandierina dal nominativo.

Uso:
    import utils.cty as cty
    cty.carica([percorsi...])            # carica cty.dat (una volta)
    cty.country("IK1GPG")                # -> ("Italy","EU","15","28") o None
    cty.bandiera("IK1GPG")               # -> "🇮🇹"  (o "" se sconosciuta)

Se cty.dat non è presente, resta attiva una mini-tabella di prefissi di
riserva (i più comuni), così la bandiera compare comunque nei casi frequenti.
"""

import os
import re

_prefissi = {}     # PREFISSO -> (name, cont, cq, itu)
_esatti = {}       # =CALL    -> (name, cont, cq, itu)
_caricato = False

# --- Nome DXCC (come in cty.dat) -> ISO2 per l'emoji bandiera ---
_ISO2 = {
    "Sov Mil Order of Malta": "", "Spratly Islands": "", "Monaco": "MC",
    "Agalega & St. Brandon": "", "Mauritius": "MU", "Rodriguez Island": "",
    "Equatorial Guinea": "GQ", "Annobon Island": "", "Fiji": "FJ",
    "Conway Reef": "", "Rotuma Island": "", "Kingdom of Eswatini": "SZ",
    "Tunisia": "TN", "Vietnam": "VN", "Guinea": "GN", "Bouvet": "",
    "Peter 1 Island": "", "Azerbaijan": "AZ", "Georgia": "GE",
    "Montenegro": "ME", "Sri Lanka": "LK", "ITU HQ": "", "United Nations HQ": "",
    "Timor-Leste": "TL", "Israel": "IL", "Libya": "LY", "Cyprus": "CY",
    "Tanzania": "TZ", "Nigeria": "NG", "Madagascar": "MG",
    "Mauritania": "MR", "Niger": "NE", "Togo": "TG", "Samoa": "WS",
    "Uganda": "UG", "Kenya": "KE", "Senegal": "SN", "Jamaica": "JM",
    "Yemen": "YE", "Lesotho": "LS", "Malawi": "MW", "Algeria": "DZ",
    "Barbados": "BB", "Maldives": "MV", "Guyana": "GY", "Croatia": "HR",
    "Ghana": "GH", "Malta": "MT", "Zambia": "ZM", "Kuwait": "KW",
    "Sierra Leone": "SL", "West Malaysia": "MY", "East Malaysia": "MY",
    "Nepal": "NP", "Dem. Rep. of the Congo": "CD", "Burundi": "BI",
    "Singapore": "SG", "Rwanda": "RW", "Trinidad & Tobago": "TT",
    "Botswana": "BW", "Tonga": "TO", "Oman": "OM", "Bhutan": "BT",
    "United Arab Emirates": "AE", "Qatar": "QA", "Bahrain": "BH",
    "Pakistan": "PK", "Scarborough Reef": "", "Turkey": "TR",
    "Iceland": "IS", "Antarctica": "AQ", "Guatemala": "GT", "Costa Rica": "CR",
    "Cocos Island": "", "Cameroon": "CM", "Corsica": "FR", "Central African Republic": "CF",
    "Republic of the Congo": "CG", "Gabon": "GA", "Chad": "TD",
    "Cote d'Ivoire": "CI", "Benin": "BJ", "Mali": "ML",
    "European Russia": "RU", "Kaliningrad": "RU", "Asiatic Russia": "RU",
    "Uzbekistan": "UZ", "Kazakhstan": "KZ", "Turkmenistan": "TM",
    "Tajikistan": "TJ", "Kyrgyzstan": "KG", "Ukraine": "UA", "Belarus": "BY",
    "Moldova": "MD", "Angola": "AO", "Cape Verde": "CV", "Comoros": "KM",
    "Guinea-Bissau": "GW", "Sao Tome & Principe": "ST", "Fed. Rep. of Germany": "DE",
    "Germany": "DE", "Philippines": "PH", "Eritrea": "ER", "Ethiopia": "ET",
    "Somalia": "SO", "Djibouti": "DJ", "South Sudan": "SS", "Sudan": "SD",
    "Egypt": "EG", "Greece": "GR", "Mount Athos": "GR", "Tuvalu": "TV",
    "Austria": "AT", "France": "FR", "Guadeloupe": "GP", "Martinique": "MQ",
    "French Guiana": "GF", "Reunion Island": "RE", "St. Pierre & Miquelon": "PM",
    "New Caledonia": "NC", "French Polynesia": "PF", "Wallis & Futuna Islands": "WF",
    "Belgium": "BE", "Denmark": "DK", "Faroe Islands": "FO", "Greenland": "GL",
    "England": "GB", "Isle of Man": "IM", "Northern Ireland": "GB",
    "Jersey": "JE", "Scotland": "GB", "Guernsey": "GG", "Wales": "GB",
    "Spain": "ES", "Balearic Islands": "ES", "Canary Islands": "ES",
    "Ceuta & Melilla": "ES", "Ireland": "IE", "Armenia": "AM", "Liechtenstein": "LI",
    "Hungary": "HU", "Switzerland": "CH", "Vatican City": "VA", "Bosnia-Herzegovina": "BA",
    "Slovenia": "SI", "North Macedonia": "MK", "Czech Republic": "CZ",
    "Slovak Republic": "SK", "Poland": "PL", "Portugal": "PT", "Azores": "PT",
    "Madeira Islands": "PT", "Luxembourg": "LU", "Sweden": "SE", "Netherlands": "NL",
    "Curacao": "CW", "Bonaire": "BQ", "Aruba": "AW", "Sint Maarten": "SX",
    "Saba & St. Eustatius": "BQ", "Brazil": "BR", "Fernando de Noronha": "BR",
    "Bolivia": "BO", "Chile": "CL", "Easter Island": "CL", "Colombia": "CO",
    "Ecuador": "EC", "Galapagos Islands": "EC", "Paraguay": "PY", "Peru": "PE",
    "Suriname": "SR", "Uruguay": "UY", "Venezuela": "VE", "Argentina": "AR",
    "Falkland Islands": "FK", "Anguilla": "AI", "Antigua & Barbuda": "AG",
    "Bahamas": "BS", "Belize": "BZ", "British Virgin Islands": "VG",
    "Canada": "CA", "Cayman Islands": "KY", "Cuba": "CU", "Dominica": "DM",
    "Dominican Republic": "DO", "El Salvador": "SV", "US Virgin Islands": "VI",
    "Grenada": "GD", "Haiti": "HT", "Honduras": "HN", "Mexico": "MX",
    "Nicaragua": "NI", "Panama": "PA", "Puerto Rico": "PR", "St. Kitts & Nevis": "KN",
    "St. Lucia": "LC", "St. Vincent": "VC", "Turks & Caicos Islands": "TC",
    "United States": "US", "Alaska": "US", "Hawaii": "US", "Guam": "GU",
    "American Samoa": "AS", "Northern Mariana Islands": "MP", "Bermuda": "BM",
    "China": "CN", "Taiwan": "TW", "Hong Kong": "HK", "Macao": "MO",
    "North Korea": "KP", "Republic of Korea": "KR", "South Korea": "KR",
    "India": "IN", "Japan": "JP", "Thailand": "TH", "Cambodia": "KH",
    "Laos": "LA", "Myanmar": "MM", "Indonesia": "ID", "Brunei Darussalam": "BN",
    "Mongolia": "MN", "Iran": "IR", "Iraq": "IQ", "Jordan": "JO",
    "Lebanon": "LB", "Saudi Arabia": "SA", "Syria": "SY", "Afghanistan": "AF",
    "Bangladesh": "BD", "Palestine": "PS", "Australia": "AU", "New Zealand": "NZ",
    "Papua New Guinea": "PG", "Solomon Islands": "SB", "Vanuatu": "VU",
    "Kiribati": "KI", "Nauru": "NR", "Palau": "PW", "Marshall Islands": "MH",
    "Micronesia": "FM", "Norway": "NO", "Svalbard": "SJ", "Jan Mayen": "SJ",
    "Finland": "FI", "Aland Islands": "AX", "Estonia": "EE", "Latvia": "LV",
    "Lithuania": "LT", "Bulgaria": "BG", "Romania": "RO", "Serbia": "RS",
    "Albania": "AL", "Gibraltar": "GI", "San Marino": "SM", "Namibia": "NA",
    "South Africa": "ZA", "Mozambique": "MZ", "Zimbabwe": "ZW", "Morocco": "MA",
    "Western Sahara": "EH", "Burkina Faso": "BF", "Gambia": "GM", "Liberia": "LR",
    "Seychelles": "SC", "Fed. Rep. of Germany": "DE",
}


_ISO2.update({
    "Italy": "IT", "African Italy": "IT", "Sardinia": "IT", "Sicily": "IT",
    "Kosovo": "XK", "Andorra": "AD", "St. Barthelemy": "BL",
    "Saint Martin": "MF", "Montserrat": "MS", "Slovak Republic": "SK",
    "Czech Republic": "CZ",
})


_ISO2.update({  # SUPP_ISO2 isole/entità
    'Agalega & St. Brandon': 'MU',
    'Amsterdam & St. Paul Is.': 'TF',
    'Andaman & Nicobar Is.': 'IN',
    'Annobon Island': 'GQ',
    'Ascension Island': 'SH',
    'Asiatic Turkey': 'TR',
    'Austral Islands': 'PF',
    'Aves Island': 'VE',
    'Baker & Howland Islands': 'US',
    'Banaba Island': 'KI',
    'Bear Island': 'NO',
    'Bouvet': 'BV',
    'Cabo Verde': 'CV',
    'Central Kiribati': 'KI',
    'Chagos Islands': 'IO',
    'Chatham Islands': 'NZ',
    'Chesterfield Islands': 'NC',
    'Christmas Island': 'CX',
    'Clipperton Island': 'FR',
    'Cocos (Keeling) Islands': 'CC',
    'Cocos Island': 'CR',
    'Conway Reef': 'FJ',
    'Crete': 'GR',
    'Crozet Island': 'TF',
    'DPR of Korea': 'KP',
    'Desecheo Island': 'US',
    'Dodecanese': 'GR',
    'Ducie Island': 'PN',
    'Eastern Kiribati': 'KI',
    'European Turkey': 'TR',
    'Franz Josef Land': 'RU',
    'Glorioso Islands': 'TF',
    'Guantanamo Bay': 'US',
    'Heard Island': 'HM',
    'Johnston Island': 'US',
    'Juan Fernandez Islands': 'CL',
    'Kerguelen Islands': 'TF',
    'Kermadec Islands': 'NZ',
    'Kure Island': 'US',
    'Lakshadweep Islands': 'IN',
    'Lord Howe Island': 'AU',
    'Macquarie Island': 'AU',
    'Malpelo Island': 'CO',
    'Mariana Islands': 'MP',
    'Market Reef': 'AX',
    'Marquesas Islands': 'PF',
    'Mayotte': 'YT',
    'Mellish Reef': 'AU',
    'Midway Island': 'US',
    'Minami Torishima': 'JP',
    'N.Z. Subantarctic Is.': 'NZ',
    'Navassa Island': 'US',
    'Niue': 'NU',
    'Norfolk Island': 'NF',
    'North Cook Islands': 'CK',
    'Ogasawara': 'JP',
    'Palmyra & Jarvis Islands': 'US',
    'Peter 1 Island': 'NO',
    'Pitcairn Island': 'PN',
    'Pr. Edward & Marion Is.': 'ZA',
    'Pratas Island': 'TW',
    'Republic of Kosovo': 'XK',
    'Republic of South Sudan': 'SS',
    'Revillagigedo': 'MX',
    'Rodriguez Island': 'MU',
    'Rotuma Island': 'FJ',
    'Sable Island': 'CA',
    'San Andres & Providencia': 'CO',
    'San Felix & San Ambrosio': 'CL',
    'Shetland Islands': 'GB',
    'South Cook Islands': 'CK',
    'South Georgia Island': 'GS',
    'South Orkney Islands': 'GB',
    'South Sandwich Islands': 'GS',
    'St. Helena': 'SH',
    'St. Martin': 'MF',
    'St. Paul Island': 'CA',
    'St. Peter & St. Paul': 'BR',
    'Swains Island': 'AS',
    'Temotu Province': 'SB',
    'The Gambia': 'GM',
    'Timor - Leste': 'TL',
    'Tokelau Islands': 'TK',
    'Trindade & Martim Vaz': 'BR',
    'Tristan da Cunha & Gough': 'SH',
    'Tromelin Island': 'TF',
    'UK Base Areas on Cyprus': 'GB',
    'Wake Island': 'US',
    'Western Kiribati': 'KI',
    'Willis Island': 'AU',
})


def _flag_da_iso2(iso2):
    iso2 = (iso2 or "").upper()
    if len(iso2) != 2 or not iso2.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2)


def _parse(txt):
    global _prefissi, _esatti
    _prefissi = {}
    _esatti = {}
    for blocco in txt.split(";"):
        b = blocco.strip()
        if not b:
            continue
        name = cont = cq = itu = None
        primo = b.split(",")[0]
        if ":" in primo and b.count(":") >= 7:
            parti = b.split(":")
            name = parti[0].strip()
            cq = parti[1].strip(); itu = parti[2].strip(); cont = parti[3].strip()
            lista = ":".join(parti[8:]) if len(parti) > 8 else ""
        else:
            lista = b
        if name is None:
            continue
        info = (name, cont, cq, itu)
        for tok in lista.replace("\n", " ").replace("\r", " ").split(","):
            tok = tok.strip()
            if not tok:
                continue
            tok = re.sub(r"[\(\[\{<~].*?[\)\]\}>~]", "", tok)  # override cq/itu/etc
            if tok.startswith("="):
                _esatti[tok[1:].upper()] = info
            elif tok.startswith("*"):
                _prefissi[tok[1:].upper()] = info
            elif tok:
                _prefissi[tok.upper()] = info


# --- mini-tabella di riserva (se manca cty.dat) ---
_MINI = {
    "I": ("Italy", "EU"), "IZ": ("Italy", "EU"), "IK": ("Italy", "EU"),
    "IW": ("Italy", "EU"), "IU": ("Italy", "EU"), "DL": ("Germany", "EU"),
    "DK": ("Germany", "EU"), "DJ": ("Germany", "EU"), "DF": ("Germany", "EU"),
    "F": ("France", "EU"), "G": ("England", "EU"), "M": ("England", "EU"),
    "2E": ("England", "EU"), "EA": ("Spain", "EU"), "PA": ("Netherlands", "EU"),
    "ON": ("Belgium", "EU"), "OK": ("Czech Republic", "EU"), "OM": ("Slovak Republic", "EU"),
    "SP": ("Poland", "EU"), "OE": ("Austria", "EU"), "HB": ("Switzerland", "EU"),
    "OH": ("Finland", "EU"), "SM": ("Sweden", "EU"), "LA": ("Norway", "EU"),
    "OZ": ("Denmark", "EU"), "EI": ("Ireland", "EU"), "CT": ("Portugal", "EU"),
    "SV": ("Greece", "EU"), "LZ": ("Bulgaria", "EU"), "YO": ("Romania", "EU"),
    "9A": ("Croatia", "EU"), "S5": ("Slovenia", "EU"), "HA": ("Hungary", "EU"),
    "YU": ("Serbia", "EU"), "UA": ("European Russia", "EU"), "R": ("European Russia", "EU"),
    "UR": ("Ukraine", "EU"), "EU": ("Belarus", "EU"), "LY": ("Lithuania", "EU"),
    "YL": ("Latvia", "EU"), "ES": ("Estonia", "EU"), "W": ("United States", "NA"),
    "K": ("United States", "NA"), "N": ("United States", "NA"), "AA": ("United States", "NA"),
    "VE": ("Canada", "NA"), "VA": ("Canada", "NA"), "XE": ("Mexico", "NA"),
    "PY": ("Brazil", "SA"), "LU": ("Argentina", "SA"), "CE": ("Chile", "SA"),
    "JA": ("Japan", "AS"), "JH": ("Japan", "AS"), "JR": ("Japan", "AS"),
    "BV": ("Taiwan", "AS"), "BY": ("China", "AS"), "BG": ("China", "AS"),
    "HL": ("Republic of Korea", "AS"), "VK": ("Australia", "OC"),
    "ZL": ("New Zealand", "OC"), "4X": ("Israel", "AS"), "ZS": ("South Africa", "AF"),
}


def _mini_country(call):
    call = call.upper()
    for L in range(min(3, len(call)), 0, -1):
        if call[:L] in _MINI:
            n, c = _MINI[call[:L]]
            return (n, c, "", "")
    return None


def carica(percorsi):
    """Carica cty.dat dal primo percorso valido. Ritorna True se caricato."""
    global _caricato
    for p in percorsi:
        try:
            if p and os.path.exists(p):
                _parse(open(p, encoding="utf-8", errors="replace").read())
                _caricato = bool(_prefissi)
                if _caricato:
                    return True
        except Exception:
            continue
    _caricato = False
    return False


def country(call):
    call = (call or "").upper().strip()
    if not call:
        return None
    # normalizza portatili: prendi la parte con la cifra più significativa
    if call in _esatti:
        return _esatti[call]

    def _risolvi(base):
        if not _caricato:
            return _mini_country(base)
        if base in _esatti:
            return _esatti[base]
        for L in range(len(base), 0, -1):
            if base[:L] in _prefissi:
                return _prefissi[base[:L]]
        return None

    if "/" in call:
        _SUFFIX = {"P", "M", "MM", "AM", "QRP", "A"}
        parti = [x for x in call.split("/")
                 if x and x not in _SUFFIX and not (len(x) == 1 and x.isdigit())]
        if not parti:
            parti = [call.replace("/", "")]
        # ordina per lunghezza: il prefisso di località (più corto) vince sul call di casa
        cand = sorted(set(parti), key=len)
        for base in cand:
            r = _risolvi(base)
            if r:
                return r
        return None
    return _risolvi(call)


def iso2(call):
    info = country(call)
    if not info:
        return ""
    return _ISO2.get(info[0], "")


def bandiera(call):
    info = country(call)
    if not info:
        return ""
    return _flag_da_iso2(_ISO2.get(info[0], ""))


def aggiorna(dest, urls=None):
    """Scarica l'ultimo cty.dat (bigcty di AD1C) e lo salva in 'dest'.
    Fa un backup del file esistente, poi ricarica i prefissi.
    Ritorna (ok: bool, messaggio: str). Nessuna dipendenza esterna."""
    import os as _os, io as _io, zipfile as _zip, urllib.request as _rq, shutil as _sh, tempfile as _tmp
    if urls is None:
        urls = [
            "https://www.country-files.com/bigcty/cty.dat",
            "https://www.country-files.com/cty/cty.dat",
            "https://www.country-files.com/bigcty/download/bigcty.zip",
        ]
    dati = None
    ultimo_err = ""
    for u in urls:
        try:
            req = _rq.Request(u, headers={"User-Agent": "Mozilla/5.0 (ADIF FZR)"})
            with _rq.urlopen(req, timeout=25) as r:
                raw = r.read()
            if u.lower().endswith(".zip"):
                zf = _zip.ZipFile(_io.BytesIO(raw))
                nome = next((n for n in zf.namelist() if n.lower().endswith("cty.dat")), None)
                if not nome:
                    ultimo_err = "cty.dat non trovato nello zip"; continue
                raw = zf.read(nome)
            txt = raw.decode("utf-8", errors="replace")
            # controllo minimo di validità: deve contenere righe DXCC tipiche
            if "Italy:" in txt or "United States:" in txt:
                dati = txt; break
            ultimo_err = "contenuto non riconosciuto come cty.dat"
        except Exception as e:
            ultimo_err = f"{type(e).__name__}: {e}"
            continue
    if dati is None:
        return False, "Download non riuscito. " + ultimo_err

    try:
        # backup del vecchio file
        if dest and _os.path.exists(dest):
            try: _sh.copy2(dest, dest + ".bak")
            except Exception: pass
        # scrittura atomica
        d = _os.path.dirname(dest) or "."
        fd, tmp = _tmp.mkstemp(suffix=".dat", dir=d)
        with _os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(dati)
        _os.replace(tmp, dest)
    except Exception as e:
        return False, f"Impossibile salvare: {e}"

    # ricarica i prefissi
    try:
        carica([dest])
    except Exception:
        pass
    n = len(_prefissi) + len(_esatti)
    return True, f"cty.dat aggiornato: {n} prefissi/call caricati."
