"""
Backend di controllo radio via Hamlib (rigctld), multipiattaforma.

Interfaccia identica a OmniRigControl / SDRConsoleControl, così il resto
dell'app non cambia. Comunica con il demone rigctld sul protocollo TCP
testuale (default 127.0.0.1:4532).

Due modi d'uso:
  - rigctld avviato a mano dall'utente (o su un altro PC/host);
  - avvio automatico di rigctld dall'app (path, modello, porta, baud
    configurabili), come si fa con OmniRig.exe.

Comandi rigctld usati: f/F (freq), m/M (modo), s/S (split), i (split freq),
G XCHG (scambio VFO), \\chk_vfo, \\dump_state.
"""

import socket
import subprocess
import threading
import time


# --- mappa modi: Hamlib (rigctld) <-> app ---
_HL2APP = {
    "USB": "USB", "LSB": "LSB", "CW": "CW", "CWR": "CW", "RTTY": "RTTY",
    "RTTYR": "RTTY", "FM": "FM", "WFM": "FM", "AM": "AM",
    "PKTUSB": "USB-D", "PKTLSB": "LSB-D", "PKTFM": "FM", "FT8": "USB-D",
}
_APP2HL = {
    "USB": "USB", "LSB": "LSB", "CW": "CW", "RTTY": "RTTY", "FM": "FM", "AM": "AM",
    "SSB": "USB", "USB-D": "PKTUSB", "LSB-D": "PKTLSB",
    "FT8": "PKTUSB", "FT4": "PKTUSB", "PSK": "PKTUSB", "DATA": "PKTUSB",
    "DATA-U": "PKTUSB", "DATA-L": "PKTLSB",
}


class HamlibControl:
    def __init__(self, host="127.0.0.1", port=4532):
        self.host = host or "127.0.0.1"
        self.port = int(port or 4532)
        self._sock = None
        self._lock = threading.Lock()   # _cmd usato da thread diversi (keyer/STOP)
        # avvio automatico di rigctld (opzionale)
        self.avvio_auto = False
        self.rigctld_path = ""      # es. C:\\Program Files\\Hamlib\\bin\\rigctld.exe
        self.modello = ""           # id Hamlib del rig (es. "3073" per IC-7100)
        self.porta_seriale = ""     # es. COM5  oppure  /dev/ttyUSB0
        self.baud = ""              # es. 19200
        self._proc = None
        self._nome = ""
        # anti-blocco: timeout brevi + "circuit breaker"
        self._connect_timeout = 0.4   # s per aprire il socket
        self._cmd_timeout = 0.6       # s per un comando
        self._cooldown_until = 0.0    # se la radio/rigctld non risponde, non ritenta subito
        self._cooldown_s = 5.0        # prima pausa; raddoppia fino a _cooldown_max
        self._cooldown_max = 30.0
        self._guasti = 0              # fallimenti consecutivi

    # ---------------- configurazione ----------------
    def imposta(self, host=None, port=None, rigctld_path=None, modello=None,
                porta_seriale=None, baud=None, avvio_auto=None):
        if host is not None: self.host = host or "127.0.0.1"
        if port is not None:
            try: self.port = int(port)
            except Exception: pass
        if rigctld_path is not None: self.rigctld_path = rigctld_path
        if modello is not None: self.modello = str(modello)
        if porta_seriale is not None: self.porta_seriale = porta_seriale
        if baud is not None: self.baud = str(baud)
        if avvio_auto is not None: self.avvio_auto = bool(avvio_auto)

    # ---------------- connessione ----------------
    def _connesso(self):
        return self._sock is not None

    def _apri_socket(self):
        # se siamo in "cooldown" (connessione fallita di recente) non ritentare:
        # risponde subito, così il polling della UI non si blocca.
        if time.time() < self._cooldown_until:
            return False
        try:
            s = socket.create_connection((self.host, self.port),
                                         timeout=self._connect_timeout)
            s.settimeout(self._cmd_timeout)
            self._sock = s
            return True
        except Exception:
            self._sock = None
            self._segna_guasto()
            return False

    def _segna_guasto(self):
        """rigctld o radio non rispondono: chiude il socket (cosi' eventuali
        risposte in ritardo non finiscono nel comando successivo) e mette in
        pausa i tentativi. La pausa raddoppia a ogni fallimento consecutivo
        (5, 10, 20, 30 s): con la radio spenta l'interfaccia non si blocca."""
        if self._sock is not None:
            try: self._sock.close()
            except Exception: pass
        self._sock = None
        self._guasti += 1
        pausa = min(self._cooldown_s * (2 ** (self._guasti - 1)), self._cooldown_max)
        self._cooldown_until = time.time() + pausa

    def _avvia_rigctld(self):
        """Avvia rigctld localmente se richiesto e non già in ascolto."""
        if not self.avvio_auto or not self.rigctld_path or not self.modello:
            return
        # già in ascolto?
        if self._apri_socket():
            try: self._sock.close()
            except Exception: pass
            self._sock = None
            return
        try:
            cmd = [self.rigctld_path, "-m", str(self.modello),
                   "-t", str(self.port)]
            if self.porta_seriale:
                cmd += ["-r", self.porta_seriale]
            if self.baud:
                cmd += ["-s", str(self.baud)]
            flags = 0
            try:
                flags = subprocess.CREATE_NO_WINDOW  # Windows: niente finestra
            except Exception:
                flags = 0
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL,
                                          creationflags=flags) if flags else \
                         subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
            # dai a rigctld il tempo di aprire la porta CAT + TCP
            for _ in range(15):
                time.sleep(0.3)
                if self._apri_socket():
                    try: self._sock.close()
                    except Exception: pass
                    self._sock = None
                    break
        except Exception:
            self._proc = None

    def connetti(self, avvia_se_serve=True):
        self._cooldown_until = 0.0          # azione esplicita: riprova subito
        self._guasti = 0
        if avvia_se_serve:
            self._avvia_rigctld()
        return self._apri_socket()

    def disponibile(self):
        if self._connesso():
            return True
        return self._apri_socket()

    # ---------------- protocollo rigctld ----------------
    def _cmd(self, comando, righe_attese=1):
        """Invia un comando a rigctld e legge la risposta (linee).
        Riconnette una volta se il socket è caduto. Thread-safe."""
        with self._lock:
            return self._cmd_locked(comando, righe_attese)

    def _cmd_locked(self, comando, righe_attese=1):
        for tentativo in (1, 2):
            if self._sock is None and not self._apri_socket():
                return None
            try:
                self._sock.sendall((comando + "\n").encode("ascii", "ignore"))
                dati = b""
                # legge finché arriva 'RPRT' (fine risposta rigctld) o abbastanza righe
                t0 = time.time()
                chiuso = False
                while time.time() - t0 < 2.0:
                    try:
                        chunk = self._sock.recv(1024)
                    except socket.timeout:
                        break
                    if not chunk:
                        chiuso = True             # rigctld ha chiuso la connessione
                        break
                    dati += chunk
                    if b"RPRT" in dati or dati.count(b"\n") >= righe_attese:
                        # per i 'get' non c'è RPRT finché non completo: ci basta
                        if b"RPRT" in dati or dati.count(b"\n") >= righe_attese:
                            break
                if not dati and chiuso and tentativo == 1:
                    # connessione vecchia chiusa da rigctld: riprova con una nuova
                    try: self._sock.close()
                    except Exception: pass
                    self._sock = None
                    continue
                if not dati:
                    # rigctld e' in ascolto ma la radio non risponde (spenta,
                    # cavo staccato): senza questo, ogni comando aspettava il
                    # timeout e la barra radio bloccava l'interfaccia ogni secondo.
                    self._segna_guasto()
                    return None
                testo = dati.decode("utf-8", "replace")
                # RPRT -5 = timeout verso la radio, -6 = errore I/O sulla porta CAT
                if "RPRT -5" in testo or "RPRT -6" in testo:
                    self._segna_guasto()
                    return None
                self._guasti = 0
                return [r for r in testo.replace("\r", "").split("\n")]
            except Exception:
                # connessione caduta (es. rigctld riavviato): riprova una volta
                # con un socket nuovo, poi pausa
                if tentativo == 1:
                    try: self._sock.close()
                    except Exception: pass
                    self._sock = None
                    continue
                self._segna_guasto()
                return None
        return None

    @staticmethod
    def _prima_riga_valida(righe):
        if not righe:
            return ""
        for r in righe:
            r = r.strip()
            if r and not r.startswith("RPRT"):
                return r
        return ""

    # ---------------- letture ----------------
    def get_freq(self):
        r = self._cmd("f", righe_attese=1)
        v = self._prima_riga_valida(r)
        try:
            return int(float(v))
        except Exception:
            return None

    def get_freq_ab(self):
        """Ritorna (rx_hz, tx_hz). In split, tx = frequenza di split ('i')."""
        rx = self.get_freq()
        tx = rx
        if self.is_split():
            r = self._cmd("i", righe_attese=1)   # get_split_freq
            v = self._prima_riga_valida(r)
            try:
                tx = int(float(v))
            except Exception:
                tx = rx
        return rx, tx

    def get_modo(self):
        r = self._cmd("m", righe_attese=2)   # ritorna: <modo>\n<passband>
        m = self._prima_riga_valida(r).upper()
        return _HL2APP.get(m, m)

    def get_modo_ab(self):
        return self.get_modo(), ""

    def is_split(self):
        r = self._cmd("s", righe_attese=2)   # ritorna: <split 0/1>\n<tx vfo>
        v = self._prima_riga_valida(r)
        return v.strip() in ("1", "1 ", "ON")

    def get_smeter(self):
        """Livello S-meter via rigctld: 'l STRENGTH' -> dB relativi a S9.
        Ritorna int (es. -12, 0, +20) oppure None se la radio non lo espone."""
        try:
            r = self._cmd("l STRENGTH", righe_attese=1)
            v = self._prima_riga_valida(r)
            if v is None or v == "":
                return None
            # rigctld su errore risponde con 'RPRT <negativo>'
            if "RPRT" in v.upper():
                return None
            return int(round(float(v)))
        except Exception:
            return None

    # ---------------- Keyer CW ----------------
    def invia_cw(self, testo):
        """Invia testo in CW tramite il keyer della radio (rigctld send_morse).
        Ritorna True se accettato. Richiede radio che supporti CW via CAT."""
        try:
            t = (testo or "").strip()
            if not t:
                return False
            r = self._cmd("\\send_morse " + t, righe_attese=1)
            v = (self._prima_riga_valida(r) or "")
            # RPRT 0 = ok; altri RPRT negativi = errore/non supportato
            return ("RPRT 0" in v) or (v.strip() == "") or ("0" == v.strip())
        except Exception:
            return False

    def ferma_cw(self):
        """Interrompe l'invio CW in corso (stop_morse)."""
        try:
            self._cmd("\\stop_morse", righe_attese=1)
            return True
        except Exception:
            return False

    def ptt(self, on):
        """Attiva/disattiva il PTT via rigctld (T 1 / T 0). Ritorna True se ok.
        Serve per la TX dei modi digitali (RTTY/PSK) via scheda audio."""
        try:
            r = self._cmd("T %d" % (1 if on else 0), righe_attese=1)
            v = (self._prima_riga_valida(r) or "")
            return ("RPRT 0" in v) or (v.strip() in ("", "0"))
        except Exception:
            return False

    def get_ptt(self):
        """Legge lo stato PTT (t): True se in trasmissione."""
        try:
            r = self._cmd("t", righe_attese=1)
            v = (self._prima_riga_valida(r) or "").strip()
            return v == "1"
        except Exception:
            return False

    def imposta_wpm(self, wpm):
        """Imposta la velocità del keyer in parole al minuto (KEYSPD)."""
        try:
            self._cmd("\\set_level KEYSPD %d" % int(wpm), righe_attese=1)
            return True
        except Exception:
            return False

    def get_wpm(self):
        """Legge la velocità keyer corrente (WPM), o None."""
        try:
            r = self._cmd("\\get_level KEYSPD", righe_attese=1)
            v = self._prima_riga_valida(r)
            return int(round(float(v)))
        except Exception:
            return None

    def nome_radio(self):
        if self._nome:
            return self._nome
        # \chk_vfo o \dump_state sono verbosi; usiamo il modello configurato
        self._nome = ("Hamlib " + self.modello) if self.modello else "Hamlib"
        return self._nome

    # ---------------- comandi ----------------
    def set_freq(self, hz):
        try:
            self._cmd(f"F {int(hz)}", righe_attese=1)
            return True
        except Exception:
            return False

    def set_modo(self, modo, dig_come_usbd=True):
        m = _APP2HL.get(str(modo).upper().strip(), str(modo).upper().strip())
        if not dig_come_usbd and m == "PKTUSB":
            m = "RTTY"
        try:
            self._cmd(f"M {m} 0", righe_attese=1)   # passband 0 = default
            return True
        except Exception:
            return False

    def toggle_split(self):
        try:
            nuovo = "0" if self.is_split() else "1"
            vfo = "VFOA" if nuovo == "0" else "VFOB"
            self._cmd(f"S {nuovo} {vfo}", righe_attese=1)   # set_split_vfo
            return True
        except Exception:
            return False

    def vfo_swap(self):
        try:
            self._cmd("G XCHG", righe_attese=1)   # vfo_op: scambia A/B
            return True
        except Exception:
            return False

    def qsy(self, hz, modo=None, dig_come_usbd=True, usa_bandplan=True):
        ok = self.set_freq(hz)
        if modo:
            self.set_modo(modo, dig_come_usbd=dig_come_usbd)
        return ok

    # ---------------- chiusura ----------------
    def chiudi_omnirig(self, forza=False):
        self._chiudi()

    def _chiudi(self):
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = None
        try:
            if self._proc:
                self._proc.terminate()
                # attendi la chiusura; se resiste, forza kill
                try:
                    self._proc.wait(timeout=2)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
        except Exception:
            pass
        self._proc = None

    def stato(self):
        return "connesso" if self.disponibile() else "non disponibile"
