import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import time

class SDRConsoleControl:
    """Controllo radio via SDR Console attraverso il suo server CAT
    (protocollo Kenwood TS-2000) su porta seriale virtuale.

    Espone la STESSA interfaccia di OmniRigControl, così l'app può usare
    l'uno o l'altro in modo intercambiabile. Legge la frequenza/modo dove
    l'utente punta in SDR Console (es. downlink QO-100 sul Perseus).

    Catena tipica:  SDR Console → COM_A ↔ COM_B → questa classe (legge COM_B).

    NOTE:
    - Serve pyserial. Se manca, disponibile() ritorna False senza errori.
    - Il controllo (set_freq/set_modo/split) è di sola lettura per ora:
      SDR Console via CAT accetta anche scrittura, ma per il logging serve
      solo leggere; i metodi di scrittura sono no-op prudenti.
    """

    # Mappa codici modo TS-2000 → stringhe ADIF
    _MD_TO_MODO = {"1": "LSB", "2": "USB", "3": "CW", "4": "FM",
                   "5": "AM", "6": "RTTY", "7": "CW", "9": "RTTY"}

    def __init__(self, porta="COM11", baud=57600):
        self.porta = porta
        self.baud = baud
        self._ser = None
        self._pyserial_ok = None   # None = non ancora verificato

    # ── Disponibilità ────────────────────────────────────────
    def disponibile(self):
        """True se pyserial è installato (la porta si verifica al connetti)."""
        if self._pyserial_ok is None:
            try:
                import serial  # noqa: F401
                self._pyserial_ok = True
            except Exception:
                self._pyserial_ok = False
        return self._pyserial_ok

    def imposta_porta(self, porta, baud=None):
        """Cambia la porta seriale (chiude l'eventuale connessione aperta)."""
        self._chiudi()
        self.porta = porta
        if baud:
            self.baud = baud

    def connetti(self, avvia_se_serve=True):
        """Apre la porta seriale verso SDR Console. Ritorna True se riuscito."""
        if not self.disponibile():
            return False
        if self._ser is not None:
            return True
        try:
            import serial
            self._ser = serial.Serial(self.porta, self.baud, timeout=0.2)
            return True
        except Exception:
            self._ser = None
            return False

    def _assicura(self):
        """Garantisce che la porta sia aperta."""
        if self._ser is not None:
            return True
        return self.connetti()

    # ── Comunicazione TS-2000 ────────────────────────────────
    def _invia(self, comando):
        """Manda un comando TS-2000 (con ';') e legge la risposta fino al ';'.
        Ritorna la stringa di risposta, o '' se errore."""
        if not self._assicura():
            return ""
        try:
            self._ser.reset_input_buffer()
            self._ser.write(comando.encode("ascii"))
            import time
            risposta = b""
            t0 = time.time()
            while time.time() - t0 < 1.0:
                c = self._ser.read(1)
                if not c:
                    continue
                risposta += c
                if c == b";":
                    break
            return risposta.decode("ascii", "replace")
        except Exception:
            # Porta caduta: chiudi così al prossimo giro si riapre
            self._chiudi()
            return ""

    # ── Lettura frequenza / modo ─────────────────────────────
    def get_freq(self):
        """Frequenza del ricevitore attivo (Hz) o None."""
        r = self._invia("FA;")
        if r.startswith("FA") and r.endswith(";"):
            cifre = r[2:-1]
            if cifre.isdigit():
                return int(cifre)
        return None

    def get_freq_ab(self):
        """Ritorna (freq_a, freq_b). SDR Console via TS-2000 espone i
        ricevitori come FA (RX1) e FB (RX2). Per il logging usiamo FA come
        VFO-A; FB solo se presente un secondo ricevitore."""
        fa = self.get_freq()
        fb = None
        r = self._invia("FB;")
        if r.startswith("FB") and r.endswith(";"):
            cifre = r[2:-1]
            if cifre.isdigit():
                fb = int(cifre)
        return (fa, fb)

    def get_modo(self):
        """Modo del ricevitore attivo come stringa ADIF, o None."""
        r = self._invia("MD;")
        if r.startswith("MD") and r.endswith(";"):
            codice = r[2:-1]
            return self._MD_TO_MODO.get(codice)
        return None

    def get_modo_ab(self):
        """(modo_a, modo_b). SDR Console espone un modo per ricevitore
        attivo; ritorniamo lo stesso per entrambi per semplicità."""
        m = self.get_modo()
        return (m, m)

    def is_split(self):
        """SDR Console (ricezione) non ha il concetto di split come un rig.
        Ritorna sempre False."""
        return False

    def nome_radio(self):
        """Nome della sorgente per il display."""
        return "SDR Console"

    # ── Scrittura (no-op prudenti: per ora sola lettura) ─────
    def set_freq(self, hz):
        """Imposta la frequenza in SDR Console (comando FA). Opzionale."""
        try:
            self._invia(f"FA{int(hz):011d};")
            return True
        except Exception:
            return False

    def set_modo(self, modo, dig_come_usbd=True):
        """Non implementato per SDR Console (sola lettura per il logging)."""
        return False

    def toggle_split(self):
        return None

    def vfo_swap(self):
        return False

    # ── Chiusura ─────────────────────────────────────────────
    def chiudi_omnirig(self, forza=False):
        """Simmetria con OmniRig: chiude la porta seriale."""
        self._chiudi()

    def _chiudi(self):
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None


