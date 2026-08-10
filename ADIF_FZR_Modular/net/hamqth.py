import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import urllib.request
import xml.etree.ElementTree as ET

class HamQTHClient:
    """Client per l'API XML di HamQTH.com.
    Flusso: login (username+password → session_id) → lookup (session_id+callsign → dati)."""

    BASE = "https://www.hamqth.com/xml.php"
    PRG  = "ADIF_FZR_2.3"

    def __init__(self, username, password):
        self.username = username.strip()
        self.password = password.strip()
        self._session = None

    def _login(self):
        """Ottiene un session_id valido. Lo riutilizza se già presente."""
        if self._session:
            return self._session, None
        url = (f"{self.BASE}?u={urllib.parse.quote(self.username)}"
               f"&p={urllib.parse.quote(self.password)}"
               f"&prg={self.PRG}")
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers={"User-Agent": "ADIF-FZR/2.3"}),
                    timeout=10) as r:
                xml = r.read().decode("utf-8", errors="replace")
            m = re.search(r'<session_id>([^<]+)</session_id>', xml)
            if m:
                self._session = m.group(1).strip()
                return self._session, None
            err = re.search(r'<error>([^<]+)</error>', xml)
            return None, err.group(1) if err else "Login fallito (risposta non riconosciuta)"
        except Exception as e:
            return None, str(e)

    def lookup(self, callsign):
        """Cerca un callsign. Ritorna (dict_info, errore_str|None)."""
        session, err = self._login()
        if not session:
            return None, err
        url = (f"{self.BASE}?id={urllib.parse.quote(session)}"
               f"&callsign={urllib.parse.quote(callsign.upper().strip())}"
               f"&prg={self.PRG}")
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers={"User-Agent": "ADIF-FZR/2.3"}),
                    timeout=10) as r:
                xml = r.read().decode("utf-8", errors="replace")
        except Exception as e:
            return None, str(e)

        if '<error>' in xml:
            err = re.search(r'<error>([^<]+)</error>', xml)
            msg = err.group(1) if err else "Errore sconosciuto"
            if "Callsign not found" in msg or "not found" in msg.lower():
                return None, "NOT_FOUND"
            # Session scaduta — riprova una volta
            if "Session does not exist" in msg or "session" in msg.lower():
                self._session = None
                return self.lookup(callsign)
            return None, msg

        def _tag(t):
            m = re.search(fr'<{t}>([^<]*)</{t}>', xml)
            return m.group(1).strip() if m else ""

        info = {
            "callsign":  _tag("callsign") or callsign.upper(),
            "nick":      _tag("nick"),
            "qth":       _tag("qth"),
            "country":   _tag("country"),
            "continent": _tag("continent"),
            "itu":       _tag("itu"),
            "cq":        _tag("cq"),
            "grid":      _tag("grid"),
            "adif":      _tag("adif"),
            "lotw":      _tag("lotw"),
            "eqsl":      _tag("eqsl"),
            "qsl_via":   _tag("qsl_via"),
            "email":     _tag("email"),
            "birth_year":_tag("birth_year"),
        }
        return info, None


