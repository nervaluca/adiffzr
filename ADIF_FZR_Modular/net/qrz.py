import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import urllib.request
import urllib.parse
import re


class QRZClient:
    """Client per l'API XML di QRZ.com.
    Flusso: login (username+password → session Key) → lookup (s=Key+callsign).
    Con account registrato senza abbonamento i campi restituiti sono ridotti
    (nome, grid, country, zone) e c'è un limite giornaliero (~100 lookup);
    con abbonamento 'XML Logbook Data' arrivano tutti i campi.
    Ritorna un dizionario con le stesse chiavi del client HamQTH, così
    l'interfaccia può usarli allo stesso modo."""

    BASE = "https://xmldata.qrz.com/xml/current/"
    PRG  = "ADIF_FZR_2.5"

    def __init__(self, username, password):
        self.username = (username or "").strip()
        self.password = (password or "").strip()
        self._session = None
        self.last_count = None   # lookup fatti nelle 24h (dal server)

    def _get(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "ADIF-FZR/2.5"})
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.read().decode("utf-8", errors="replace")

    def _login(self):
        if self._session:
            return self._session, None
        url = (f"{self.BASE}?username={urllib.parse.quote(self.username)}"
               f"&password={urllib.parse.quote(self.password)}"
               f"&agent={self.PRG}")
        try:
            xml = self._get(url)
        except Exception as e:
            return None, str(e)
        m = re.search(r'<Key>([^<]+)</Key>', xml)
        if m:
            self._session = m.group(1).strip()
            c = re.search(r'<Count>([^<]+)</Count>', xml)
            if c:
                self.last_count = c.group(1).strip()
            return self._session, None
        err = re.search(r'<Error>([^<]+)</Error>', xml)
        return None, (err.group(1).strip() if err else "Login QRZ fallito (risposta non riconosciuta)")

    def lookup(self, callsign):
        """Cerca un callsign. Ritorna (dict_info, errore_str|None).
        errore_str == 'NOT_FOUND' se il nominativo non è nel database."""
        session, err = self._login()
        if not session:
            return None, err
        call = callsign.upper().strip()
        url = f"{self.BASE}?s={urllib.parse.quote(session)}&callsign={urllib.parse.quote(call)}"
        try:
            xml = self._get(url)
        except Exception as e:
            return None, str(e)

        if '<Error>' in xml:
            e = re.search(r'<Error>([^<]+)</Error>', xml)
            msg = e.group(1).strip() if e else "Errore sconosciuto"
            low = msg.lower()
            if "not found" in low:
                return None, "NOT_FOUND"
            if "session" in low or "timeout" in low or "invalid" in low:
                # sessione scaduta: riprova una volta
                self._session = None
                if session:   # evita loop infinito
                    session2, err2 = self._login()
                    if session2:
                        return self.lookup(call)
                return None, msg
            return None, msg

        def _tag(t):
            m = re.search(fr'<{t}>([^<]*)</{t}>', xml, re.IGNORECASE)
            return m.group(1).strip() if m else ""

        c = re.search(r'<Count>([^<]+)</Count>', xml)
        if c:
            self.last_count = c.group(1).strip()

        fname = _tag("fname")
        lname = _tag("name")
        nome = (fname + " " + lname).strip()
        citta = _tag("addr2")
        stato = _tag("state")
        qth = citta + (", " + stato if stato and citta else stato)

        info = {
            "callsign":  _tag("call") or call,
            "nick":      fname,
            "name":      nome,
            "qth":       qth,
            "addr":      _tag("addr1"),
            "state":     stato,
            "county":    _tag("county"),
            "country":   _tag("country") or _tag("land"),
            "continent": "",
            "itu":       _tag("ituzone"),
            "cq":        _tag("cqzone"),
            "grid":      _tag("grid"),
            "adif":      _tag("dxcc"),
            "dxcc":      _tag("dxcc"),
            "qsl_via":   _tag("qslmgr"),
            "email":     _tag("email"),
            "lat":       _tag("lat"),
            "lon":       _tag("lon"),
        }
        return info, None
