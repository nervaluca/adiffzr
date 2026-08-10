import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import os
import json
import urllib.request
import urllib.parse
import subprocess
import tempfile
import adif_io
from config import T

class CloudlogUploader:
    """Client minimale per l'endpoint ufficiale POST /index.php/api/qso di
    Cloudlog. Nessuna dipendenza esterna: usa solo urllib (stdlib), così
    funziona su qualunque installazione di ADIF FZR senza richiedere
    'requests'. Ogni chiamata invia UN QSO alla volta in formato ADIF
    embeddato in JSON, così come documentato dall'API ufficiale Cloudlog."""

    def __init__(self, base_url, api_key, station_profile_id):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key.strip()
        self.station_profile_id = str(station_profile_id).strip()

    def _endpoint(self):
        return f"{self.base_url}/index.php/api/qso"

    # Campi che possono contenere testo libero con caratteri speciali
    _CAMPI_TESTO = {
        'name', 'comment', 'notes', 'country', 'qth', 'address',
        'my_city', 'my_country', 'my_name', 'cont', 'station_callsign',
    }

    @staticmethod
    def _sanifica_val(k, val):
        """Sanifica un valore ADIF per Cloudlog.
        - Rimuove < > da tutti i campi (spaccano il parser ADIF PHP)
        - Nei campi testo: rimuove apostrofi, virgolette e caratteri non-ASCII
          che causano crash SQL o errori PHP → HTTP 500"""
        s = (str(val)
             .strip()
             .replace('<', '')
             .replace('>', '')
             .replace('\r', ' ')
             .replace('\n', ' ')
             .replace('\t', ' '))
        if k.lower() in CloudlogUploader._CAMPI_TESTO:
            # Rimuove apostrofi e virgolette (rompono SQL in Cloudlog)
            s = s.replace("'", '').replace('"', '').replace('`', '')
            # Rimuove caratteri non-ASCII (nomi giapponesi/cinesi/arabi ecc.)
            s = s.encode('ascii', errors='ignore').decode('ascii')
        # & → and (può rompere JSON/XML in alcuni Cloudlog)
        s = s.replace('&', 'and')
        return s

    @staticmethod
    def _qso_to_adif_string(qso):
        """Converte un singolo QSO (dict) in una stringa ADIF <tag:len>val...<eor>."""
        CAMPI_ESCLUSI = {
            'adif_ver', 'programid', 'programversion', 'created_timestamp',
            'app_cloudlog_qso_id',
        }
        parts = []
        for k, v in qso.items():
            k_low = k.lower()
            if k_low in CAMPI_ESCLUSI:
                continue
            val = CloudlogUploader._sanifica_val(k_low, v)
            if not val:
                continue
            # FREQ: deve essere un numero decimale valido
            if k_low == 'freq':
                try:
                    val = f"{float(val):.6f}".rstrip('0').rstrip('.')
                except ValueError:
                    continue
            parts.append(f"<{k.upper()}:{len(val)}>{val}")
        parts.append("<eor>")
        return "".join(parts)

    def test_connection(self):
        """Invia un QSO 'vuoto' fittizio non valido solo per verificare che
        la API key venga accettata (status diverso da 401/'missing api key').
        Ritorna (True, msg) o (False, msg)."""
        try:
            payload = {
                "key": self.api_key,
                "station_profile_id": self.station_profile_id,
                "type": "adif",
                "string": "<call:4>TEST<qso_date:8>19700101<time_on:4>0000<band:3>20m<mode:3>SSB<eor>",
            }
            data = _cl_json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self._endpoint(), data=data,
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = _cl_json.loads(resp.read().decode("utf-8"))
            if body.get("status") == "failed" and "api key" in str(body.get("reason", "")).lower():
                return False, body.get("reason", "API key non valida")
            return True, "OK"
        except urllib.error.HTTPError as e:
            try:
                body = _cl_json.loads(e.read().decode("utf-8"))
                return False, body.get("reason", str(e))
            except Exception:
                return False, str(e)
        except Exception as e:
            return False, str(e)

    def upload_qso(self, qso):
        """Carica un singolo QSO. Ritorna dict {'ok':bool,'dup':bool,'msg':str}."""
        adif_str = self._qso_to_adif_string(qso)
        payload = {
            "key": self.api_key,
            "station_profile_id": self.station_profile_id,
            "type": "adif",
            "string": adif_str,
        }
        try:
            data = _cl_json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self._endpoint(), data=data,
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = _cl_json.loads(resp.read().decode("utf-8"))
            if body.get("status") == "created":
                imported = body.get("imported_count", 1)
                if imported == 0:
                    # Cloudlog ha riconosciuto un duplicato e non l'ha importato
                    return {"ok": True, "dup": True, "msg": "duplicato"}
                return {"ok": True, "dup": False, "msg": "ok"}
            return {"ok": False, "dup": False,
                    "msg": str(body.get("messages") or body.get("reason") or "errore sconosciuto")}
        except urllib.error.HTTPError as e:
            try:
                raw = e.read().decode("utf-8", errors="replace")
                if e.code == 500:
                    # 500 quasi sempre = carattere speciale nel QSO che spezza il parser ADIF di Cloudlog
                    return {"ok": False, "dup": False,
                            "msg": f"HTTP 500 — Parser ADIF Cloudlog in errore (carattere speciale nel QSO?)"}
                body = _cl_json.loads(raw)
                return {"ok": False, "dup": False, "msg": body.get("reason", str(e))}
            except Exception:
                return {"ok": False, "dup": False, "msg": f"HTTP {e.code}: {e.reason}"}
        except Exception as e:
            return {"ok": False, "dup": False, "msg": str(e)}




class ClublogUploader:
    """Client per le API ufficiali di Clublog:
    - realtime.php: upload di UN QSO alla volta (form urlencoded), pensata
      per pochi QSO/sessione, NON per bulk upload (Clublog blocca/penalizza
      l'abuso di questo endpoint con tanti QSO in rapida sequenza).
    - putlogs.php: upload multipart dell'intero file ADIF, pensata invece
      apposta per caricare in blocco un log intero o grosse porzioni."""

    REALTIME_URL = "https://clublog.org/realtime.php"
    PUTLOGS_URL = "https://clublog.org/putlogs.php"

    def __init__(self, email, password, callsign, api_key):
        self.email = email.strip()
        self.password = password.strip()
        self.callsign = callsign.strip().upper()
        self.api_key = api_key.strip()

    def upload_qso_realtime(self, qso):
        """Carica un singolo QSO via realtime.php. Ritorna dict {'ok','dup','msg'}."""
        adif_str = CloudlogUploader._qso_to_adif_string(qso)  # stesso formato <tag:len>val...<eor>
        payload = {
            "email": self.email,
            "password": self.password,
            "callsign": self.callsign,
            "adif": adif_str,
            "api": self.api_key,
        }
        try:
            data = urllib.parse.urlencode(payload).encode("utf-8")
            req = urllib.request.Request(
                self.REALTIME_URL, data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST")
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8", errors="replace").strip()
            body_up = body.upper()
            if "QSO DUPLICATE" in body_up:
                return {"ok": True, "dup": True, "msg": body}
            if "QSO OK" in body_up or "QSO MODIFIED" in body_up:
                return {"ok": True, "dup": False, "msg": body}
            return {"ok": False, "dup": False, "msg": body or "Risposta non riconosciuta"}
        except urllib.error.HTTPError as e:
            try:
                msg = e.read().decode("utf-8", errors="replace")
            except Exception:
                msg = str(e)
            return {"ok": False, "dup": False, "msg": f"HTTP {e.code}: {msg}"}
        except Exception as e:
            return {"ok": False, "dup": False, "msg": str(e)}

    def upload_bulk_adif(self, adif_text, filename="adif_fzr_export.adi"):
        """Carica l'intero file ADIF (testo) via putlogs.php (multipart/form-data).
        Implementato a mano con urllib per non introdurre dipendenze esterne
        (niente 'requests'). Ritorna (ok: bool, msg: str)."""
        boundary = "----ADIFFZRBoundary7d8f1a2c"
        fields = {
            "email": self.email,
            "password": self.password,
            "callsign": self.callsign,
            "api": self.api_key,
        }
        parts = []
        for name, value in fields.items():
            parts.append(f"--{boundary}\r\n"
                         f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                         f"{value}\r\n")
        parts.append(f"--{boundary}\r\n"
                     f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                     f"Content-Type: application/octet-stream\r\n\r\n")
        body_head = "".join(parts).encode("utf-8")
        body_tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
        body = body_head + adif_text.encode("utf-8") + body_tail

        try:
            req = urllib.request.Request(
                self.PUTLOGS_URL, data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                msg = resp.read().decode("utf-8", errors="replace").strip()
            return True, (msg or "Upload completato (nessun messaggio dal server).")
        except urllib.error.HTTPError as e:
            try:
                msg = e.read().decode("utf-8", errors="replace")
            except Exception:
                msg = str(e)
            return False, f"HTTP {e.code}: {msg}"
        except Exception as e:
            return False, str(e)




class LotwUploader:
    """Invoca l'eseguibile tqsl (TrustedQSL) per firmare e caricare i QSO su
    LoTW. Non esiste un'API REST ufficiale per questo: il flusso supportato
    da ARRL è scrivere un ADIF temporaneo e lanciare tqsl in modalità
    riga di comando con i flag -d -u -a compliant -x -l <location>."""

    def __init__(self, tqsl_path, station_location, password=""):
        self.tqsl_path = tqsl_path.strip().strip('"')
        self.station_location = station_location.strip()
        self.password = password

    def is_valido(self):
        return os.path.isfile(self.tqsl_path)

    def upload(self, qsos):
        """Scrive i QSO in un ADIF temporaneo e lancia tqsl. Ritorna
        (exit_code:int, messaggio:str, stderr_completo:str)."""
        CAMPI_H = {"adif_ver", "programid", "programversion", "created_timestamp"}
        righe = ["<ADIF_VER:5>3.1.4", "<PROGRAMID:17>ADIF_FZR_2.3_BETA", "<EOH>", ""]
        for qso in qsos:
            campi = []
            for k, v in qso.items():
                if k.lower() in CAMPI_H or not str(v).strip():
                    continue
                campi.append(f"<{k.upper()}:{len(str(v))}>{v}")
            campi.append("<EOR>")
            righe.append(" ".join(campi))
        adif_text = chr(10).join(righe)

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".adi", prefix="adif_fzr_lotw_",
            delete=False, encoding="utf-8")
        try:
            tmp.write(adif_text)
            tmp.close()

            cmd = [self.tqsl_path, "-d", "-u", "-a", "compliant", "-x",
                   "-l", self.station_location]
            if self.password:
                cmd += ["-p", self.password]
            cmd.append(tmp.name)

            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            exit_code = proc.returncode
            msg = _TQSL_EXIT_CODES_IT.get(exit_code, f"Codice di uscita sconosciuto: {exit_code}")
            return exit_code, msg, proc.stderr
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass




class EqslUploader:
    """Client per l'interfaccia ufficiale 'Real-Time Logging Software'
    di eQSL.cc: un unico endpoint (ImportADIF.cfm) accetta sia un singolo
    QSO sia un intero file ADIF via FORM POST multipart, senza bisogno di
    API key — solo username/password eQSL passati come campi form."""

    URL = "https://www.eQSL.cc/qslcard/ImportADIF.cfm"

    def __init__(self, username, password, qth_nickname=""):
        self.username = username.strip()
        self.password = password.strip()
        self.qth_nickname = qth_nickname.strip()

    def upload_adif(self, adif_text):
        """Carica un file ADIF (testo, con o senza header) su eQSL.
        Ritorna (ok: bool, msg: str, added: int|None, total: int|None).
        Nota: 'Caution: ProgramID or Logger not found' è un avviso NON
        bloccante di eQSL — significa solo che il tag PROGRAMID dell'header
        non è registrato nel loro database di logger conosciuti; i QSO
        vengono comunque importati normalmente."""
        boundary = "----ADIFFZRBoundaryEQSL9b3c"
        fields = {
            "EQSL_USER": self.username,
            "EQSL_PSWD": self.password,
        }
        if self.qth_nickname:
            fields["QTHNickname"] = self.qth_nickname
        parts = []
        for name, value in fields.items():
            parts.append(f"--{boundary}\r\n"
                         f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                         f"{value}\r\n")
        parts.append(f"--{boundary}\r\n"
                     f'Content-Disposition: form-data; name="Filename"; filename="adif_fzr_export.adi"\r\n'
                     f"Content-Type: application/octet-stream\r\n\r\n")
        body_head = "".join(parts).encode("utf-8")
        body_tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
        body = body_head + adif_text.encode("utf-8") + body_tail

        try:
            req = urllib.request.Request(
                self.URL, data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            testo_pulito = re.sub(r'<[^>]+>', ' ', html)
            testo_pulito = re.sub(r'\s+', ' ', testo_pulito).strip()

            # Riga chiave: "Result: X out of Y records added"
            m = re.search(r'Result:\s*(\d+)\s*out of\s*(\d+)\s*records?\s*added', testo_pulito, re.I)
            added = int(m.group(1)) if m else None
            total = int(m.group(2)) if m else None

            # Errori fatali veri (non confondere con "Caution: ..." che è
            # solo informativo) — cerchiamo righe che iniziano con "Error"
            # o contengono "Bad Callsign"/"Bad Band"/"Bad Mode" ecc.
            errori_fatali = re.findall(r'(Error[^.]*\.)', testo_pulito, re.I)
            bad_match = re.findall(r'(Bad [A-Za-z/_]+:?[^.]*\.)', testo_pulito, re.I)

            if added is not None:
                ok = added > 0 or total == 0
            else:
                ok = not errori_fatali and not bad_match

            msg_parti = []
            if added is not None:
                msg_parti.append(f"Result: {added} out of {total} records added")
            for w in re.findall(r'(Caution:[^.]*\.)', testo_pulito, re.I):
                msg_parti.append(w.strip() + "  (non bloccante)")
            for e in errori_fatali + bad_match:
                msg_parti.append(e.strip())
            if not msg_parti:
                msg_parti.append(testo_pulito[:400])

            return ok, chr(10).join(msg_parti), added, total
        except urllib.error.HTTPError as e:
            try:
                msg = e.read().decode("utf-8", errors="replace")
            except Exception:
                msg = str(e)
            return False, f"HTTP {e.code}: {msg}", None, None
        except Exception as e:
            return False, str(e), None, None




class QO100Uploader:
    """Client per l'API di QO-100 DX Club (qo100dx.club).
    Endpoint: POST https://qo100dx.club/api/qso
    Auth: header X-API-Key
    Accetta solo QSO via satellite QO-100 (SAT_NAME=QO-100, PROP_MODE=SAT)."""

    URL = "https://qo100dx.club/api/qso"

    def __init__(self, api_key, station_callsign, my_gridsquare=""):
        self.api_key         = api_key.strip()
        self.station_callsign = station_callsign.strip().upper()
        self.my_gridsquare   = my_gridsquare.strip().upper()

    @staticmethod
    def _filtra_qo100(qsos):
        """Restituisce solo i QSO via QO-100 (SAT_NAME contiene 'QO-100' e/o PROP_MODE=SAT)."""
        out = []
        for q in qsos:
            sat  = str(q.get("sat_name","")).upper()
            prop = str(q.get("prop_mode","")).upper()
            if "QO-100" in sat or "QO100" in sat or prop == "SAT":
                out.append(q)
        return out

    def upload_qso(self, qso):
        """Carica un singolo QSO in formato JSON. Ritorna (ok, msg)."""
        # Campi obbligatori
        data = {
            "QSO_DATE":        str(qso.get("qso_date","")).strip(),
            "TIME_ON":         str(qso.get("time_on","")).strip(),
            "STATION_CALLSIGN": self.station_callsign,
            "CALL":            str(qso.get("call","")).upper().strip(),
            "MODE":            str(qso.get("mode","")).upper().strip(),
            "BAND":            str(qso.get("band","")).lower().strip(),
            "SAT_NAME":        str(qso.get("sat_name","QO-100")).upper().strip() or "QO-100",
            "PROP_MODE":       "SAT",
        }
        # Campi opzionali utili
        if qso.get("submode"):
            data["SUBMODE"] = str(qso["submode"]).upper().strip()
        grid = str(qso.get("gridsquare","")).upper().strip()
        if grid:
            data["VUCC_GRIDS"] = grid
            data["GRIDSQUARE"] = grid
        if self.my_gridsquare:
            data["MY_GRIDSQUARE"]   = self.my_gridsquare
            data["MY_VUCC_GRIDS"]   = self.my_gridsquare
        if qso.get("rst_sent"):
            data["RST_SENT"] = str(qso["rst_sent"]).strip()
        if qso.get("rst_rcvd"):
            data["RST_RCVD"] = str(qso["rst_rcvd"]).strip()
        if qso.get("comment"):
            data["COMMENT"] = str(qso["comment"]).strip()

        try:
            body = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                self.URL, data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": self.api_key,
                    "User-Agent": "ADIF-FZR/2.3",
                },
                method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                code = resp.getcode()
                msg  = resp.read().decode("utf-8", errors="replace").strip()
            return True, msg or f"HTTP {code} OK"
        except urllib.error.HTTPError as e:
            try:
                msg = e.read().decode("utf-8", errors="replace").strip()
            except Exception:
                msg = str(e)
            return False, f"HTTP {e.code}: {msg}"
        except Exception as e:
            return False, str(e)




class LotwDownloader:
    """Scarica l'ADIF delle QSL confermate da LoTW tramite l'endpoint
    ufficiale https://lotw.arrl.org/lotwuser/lotwreport.adi
    I parametri principali documentati da ARRL:
      login, password, qso_query=yes,
      qso_qslsince=YYYY-MM-DD   (opzionale, filtra per data conferma)
      qso_owncall=CALLSIGN      (opzionale)
    Risposta: file ADIF diretto (text/plain)."""

    URL = "https://lotw.arrl.org/lotwuser/lotwreport.adi"

    def __init__(self, username, password):
        self.username = username.strip()
        self.password = password.strip()

    def download(self, qsl_since="", owncall=""):
        """Scarica l'ADIF. Ritorna (ok:bool, adif_text:str, msg:str)."""
        params = {
            "login":     self.username,
            "password":  self.password,
            "qso_query": "yes",
        }
        if qsl_since.strip():
            params["qso_qslsince"] = qsl_since.strip()
        if owncall.strip():
            params["qso_owncall"] = owncall.strip().upper()

        url = self.URL + "?" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ADIF-FZR/2.3"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8", errors="replace")

            # LoTW restituisce "<eoh>" nella prima riga se il login è ok.
            # Se restituisce "<!-- Error: ..." il login è fallito.
            if "incorrect username or password" in raw.lower() or \
               ("<!-- error" in raw.lower() and "<eoh>" not in raw.lower()):
                return False, "", "Credenziali LoTW non valide o account bloccato."
            if "<eoh>" not in raw.lower() and "<eor>" not in raw.lower():
                return False, "", f"Risposta inattesa da LoTW:\n{raw[:300]}"
            return True, raw, "OK"
        except urllib.error.HTTPError as e:
            return False, "", f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            return False, "", str(e)




class EqslDownloader:
    """Scarica l'ADIF delle QSL ricevute (inbox) da eQSL.cc.
    Il flusso è a DUE STEP (documentazione ufficiale eQSL):
    1) GET DownloadInBox.cfm?UserName=...&Password=...  → risponde con
       una pagina HTML che contiene un link <A HREF="...>.ADI file</A>
       puntante al file ADIF generato (es. /downloadedfiles/XY1234.adi)
    2) GET di quel link → ADIF effettivo.
    Il parametro UserName/Password va nel GET; la password
    va URL-encoded perché può contenere caratteri speciali."""

    BASE_URL = "https://www.eQSL.cc"
    INBOX_URL = BASE_URL + "/qslcard/DownloadInBox.cfm"

    def __init__(self, username, password, qth_nickname=""):
        self.username = username.strip()
        self.password = password.strip()
        self.qth_nickname = qth_nickname.strip()

    def download(self, rcvd_since=""):
        """Scarica l'ADIF inbox. Ritorna (ok:bool, adif_text:str, msg:str)."""
        params = {
            "UserName": self.username,
            "Password": self.password,
        }
        if self.qth_nickname:
            params["QTHNickname"] = self.qth_nickname
        if rcvd_since.strip():
            # eQSL accetta YYYYMMDD o YYYYMMDDHHMM
            params["RcvdSince"] = rcvd_since.strip()

        url = self.INBOX_URL + "?" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ADIF-FZR/2.3"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            html_low = html.lower()

            # Errori di autenticazione
            if "login" in html_low and "adif log file has been built" not in html_low:
                testo = re.sub(r'<[^>]+>', ' ', html)
                testo = re.sub(r'\s+', ' ', testo).strip()
                # Cerca un messaggio di errore esplicito
                m = re.search(r'(error[^<.]{0,120})', testo, re.I)
                msg_err = m.group(1).strip() if m else "Credenziali non valide o sessione scaduta."
                return False, "", msg_err

            # Step 2: cerca il link al file .adi nella risposta HTML
            # Il pattern documentato: <A HREF="...">ADI file</A>
            m = re.search(r'<a\s+href="([^"]*\.adi)"', html, re.I)
            if not m:
                # Prova anche .txt
                m = re.search(r'<a\s+href="([^"]*\.txt)"', html, re.I)
            if not m:
                # Cerca "NO QSO FOUND" come risposta legittima
                if "no qso found" in html_low:
                    return True, "", "NO_QSO"
                testo = re.sub(r'<[^>]+>', ' ', html)
                testo = re.sub(r'\s+', ' ', testo).strip()
                return False, "", f"Link al file ADIF non trovato nella risposta eQSL.\n{testo[:300]}"

            # Costruisce URL completo se necessario
            adi_href = m.group(1)
            if adi_href.startswith("http"):
                adi_url = adi_href
            elif adi_href.startswith("/"):
                adi_url = self.BASE_URL + adi_href
            else:
                adi_url = self.BASE_URL + "/qslcard/" + adi_href

            # Scarica il file ADIF vero
            req2 = urllib.request.Request(adi_url, headers={"User-Agent": "ADIF-FZR/2.3"})
            with urllib.request.urlopen(req2, timeout=120) as resp2:
                adif_text = resp2.read().decode("utf-8", errors="replace")

            if "<eor>" not in adif_text.lower():
                return False, "", f"File scaricato non sembra ADIF valido:\n{adif_text[:200]}"

            return True, adif_text, "OK"

        except urllib.error.HTTPError as e:
            return False, "", f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            return False, "", str(e)


