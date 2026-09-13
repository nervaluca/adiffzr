"""
FZR ALERT — Monitor WSJT-X con vista a Box / Card.

Ascolta i pacchetti UDP di WSJT-X (Decode + Status + QSO Logged):
  - Organizza i DX transitati in comode tessere su 5 colonne.
  - Evidenzia le chiamate INDIRIZZATE A TE (es. "IW1FZR CALL", "CALL IW1FZR").
  - Colora i box in base allo stato:
      * ROSSO  = DUPE (già a log su banda/modo)
      * AMBRA  = NEW SLOT (lavorato altrove)
      * VERDE  = NEW (mai lavorato)
      * ROSSO ALERT = PER TE (chiamata diretta a te)
  - CLICK SINGOLO SU UN BOX  -> Risponde a WSJT-X (pacchetto UDP Reply mtype 4) per avviare la chiamata.
  - DOPPIO CLICK SU UN BOX   -> Apre la finestra "Aggiungi QSO" nell'applicazione madre.
  - LOGGING AUTOMATICO       -> Quando si clicca "Log QSO" in WSJT-X (mtype 5), il QSO viene subito registrato e SALVATO SU DISCO.
"""

import socket
import struct
import time
import threading
import queue
import re
from datetime import datetime

import os
import sys
import tkinter as tk
import customtkinter as ctk
try:
    import utils.cty as cty
except Exception:
    cty = None

MAGIC = 0xADBCCBDA

_BAND_TAB = [
    (1.8, 2.0, "160m"), (3.5, 4.0, "80m"), (5.25, 5.45, "60m"),
    (7.0, 7.3, "40m"), (10.1, 10.15, "30m"), (14.0, 14.35, "20m"),
    (18.06, 18.17, "17m"), (21.0, 21.45, "15m"), (24.89, 24.99, "12m"),
    (28.0, 29.7, "10m"), (50.0, 54.0, "6m"), (70.0, 71.0, "4m"),
    (144.0, 148.0, "2m"), (430.0, 440.0, "70cm"), (1240.0, 1300.0, "23cm"),
]


def _banda_da_mhz(mhz):
    for lo, hi, nome in _BAND_TAB:
        if lo <= mhz <= hi:
            return nome
    return ""


def _call_base(c):
    c = (c or "").upper().strip()
    if "/" in c:
        parti = [p for p in c.split("/") if any(ch.isdigit() for ch in p)]
        if parti:
            return max(parti, key=len)
    return c


_RE_CALL = re.compile(r"^[A-Z0-9]{2,8}(/[A-Z0-9]{1,8}){0,2}$")
_RE_GRID = re.compile(r"^[A-R]{2}[0-9]{2}$")
_RE_REPORT = re.compile(r"^[+-]?\d+$")
_NONCALL = {"CQ", "DX", "TEST", "QRZ", "RR73", "RRR", "73", "TU", "R", "RR", "NA",
            "EU", "AS", "SA", "AF", "OC", "WW"}


def _pulisci_call(t):
    t = (t or "").upper().strip().strip("<>")
    if not t or t in _NONCALL:
        return ""
    if _RE_GRID.match(t) or _RE_REPORT.match(t):
        return ""
    if not _RE_CALL.match(t):
        return ""
    # un vero nominativo ha almeno una lettera E una cifra
    if not (any(c.isalpha() for c in t) and any(c.isdigit() for c in t)):
        return ""
    return t


def _dx_call_da_messaggio(msg):
    toks = (msg or "").upper().split()
    if not toks:
        return ""
    # I call tra <> (DXpedition / compound hashati da WSJT-X) hanno priorità
    for t in toks:
        if t.startswith("<") and t.endswith(">"):
            c = _pulisci_call(t)
            if c:
                return c
    if toks[0] == "CQ":
        i = 1
        if i < len(toks) and (toks[i] in ("DX", "TEST", "NA", "EU", "AS", "SA",
                                          "AF", "OC", "WW") or len(toks[i]) == 2):
            i += 1
        return _pulisci_call(toks[i]) if i < len(toks) else ""
    if len(toks) >= 2:
        c = _pulisci_call(toks[1])
        if c:
            return c
    return _pulisci_call(toks[0])


class FZRAlertWindow(ctk.CTkToplevel):
    def __init__(self, parent, app_ref):
        super().__init__(parent)
        self.app = app_ref
        self.title("FZR ALERT — Monitor WSJT-X (Box View)")
        self.geometry("920x600")
        self.minsize(750, 450)
        self.configure(fg_color="#0E141B")

        try:
            self.transient(parent)
        except Exception:
            pass

        self._sock = None
        self._run = False
        self._q = queue.Queue()

        self._cur_band = ""
        self._cur_mode = ""
        self._wsjtx_id = "WSJT-X"
        self._modo = "log"
        self._contest_id = ""
        self._solo_nuovi = False

        self._cards = {}       # call -> dict widget
        self._spot_data = {}   # call -> ultimo payload spot/decode
        self._ordine = []      # ordine di comparsa (per pulizia)
        self._MAX_BOX = 60     # tetto massimo di box a video
        self._SCAD = 90        # secondi: safety se WSJT-X non manda nuovi cicli
        self._ciclo_ms = None  # timestamp del ciclo di decodifica corrente
        self._need_regrid = False
        self._click_timer = None

        self._costruisci_ui()
        # cty.dat per la bandierina (cercato in cartella programma / cwd / dati)
        if cty is not None:
            cand = []
            try:
                if getattr(sys, "frozen", False):
                    cand.append(os.path.join(os.path.dirname(sys.executable), "cty.dat"))
                    _mei = getattr(sys, "_MEIPASS", "")
                    if _mei:
                        cand.append(os.path.join(_mei, "cty.dat"))
            except Exception:
                pass
            try:
                cand.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "cty.dat"))
            except Exception:
                pass
            cand.append(os.path.join(os.getcwd(), "cty.dat"))
            try:
                import config as _cfg
                cand.append(os.path.join(os.path.dirname(os.path.abspath(_cfg.__file__)), "cty.dat"))
            except Exception:
                pass
            try:
                cty.carica(cand)
            except Exception:
                pass
        # cartella bandierine PNG
        self._flags_dir = None
        self._flag_cache = {}
        _basi_flags = [os.path.dirname(os.path.abspath(sys.argv[0])), os.getcwd()]
        try:
            _mei = getattr(sys, "_MEIPASS", "")
            if _mei:
                _basi_flags.insert(0, _mei)
        except Exception:
            pass
        for base in _basi_flags:
            d = os.path.join(base, "flags")
            if os.path.isdir(d):
                self._flags_dir = d; break
        if self._flags_dir is None:
            try:
                import config as _cfg2
                d = os.path.join(os.path.dirname(os.path.abspath(_cfg2.__file__)), "flags")
                if os.path.isdir(d):
                    self._flags_dir = d
            except Exception:
                pass
        self._avvia()
        self.after(300, self._pompa)
        self.protocol("WM_DELETE_WINDOW", self._chiudi)

    def _get_my_call(self):
        try:
            if hasattr(self.app, "entry_owner") and self.app.entry_owner:
                c = self.app.entry_owner.get().strip().upper()
                if c:
                    return c
        except Exception:
            pass
        return "IW1FZR"

    # ---------------- UI ----------------
    def _costruisci_ui(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 4))

        ctk.CTkLabel(top, text="Porta UDP:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.e_porta = ctk.CTkEntry(top, width=60, height=28)
        self.e_porta.insert(0, "2237")
        self.e_porta.pack(side="left", padx=(4, 8))

        self.btn_conn = ctk.CTkButton(top, text="Riconnetti", width=85, height=28,
                                      command=self._riconnetti)
        self.btn_conn.pack(side="left", padx=(0, 8))
        self.btn_cty = ctk.CTkButton(top, text="Aggiorna cty.dat", width=120, height=28,
                                     fg_color="#4A5568", hover_color="#2D3748",
                                     command=self._aggiorna_cty)
        self.btn_cty.pack(side="left", padx=(0, 10))

        self.lbl_stato = ctk.CTkLabel(top, text="● in ascolto…",
                                      font=ctk.CTkFont(size=11, weight="bold"),
                                      text_color="#48BB78")
        self.lbl_stato.pack(side="left")

        self.lbl_bm = ctk.CTkLabel(top, text="—", font=ctk.CTkFont(size=12, weight="bold"),
                                   text_color="#63B3ED")
        self.lbl_bm.pack(side="right")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=10, pady=(0, 6))

        self.seg = ctk.CTkSegmentedButton(bar, values=["Log", "Contest"],
                                          command=self._cambia_modo, width=160, height=28,
                                          font=ctk.CTkFont(size=11, weight="bold"))
        self.seg.set("Log")
        self.seg.pack(side="left")

        ctk.CTkLabel(bar, text="Contest:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(10, 4))
        self.e_contest = ctk.CTkEntry(bar, width=120, height=28)
        self.e_contest.pack(side="left")
        self.e_contest.bind("<KeyRelease>", lambda e: self._set_contest())

        self.var_nuovi = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(bar, text="Solo nuovi", variable=self.var_nuovi,
                        command=self._toggle_nuovi, checkbox_width=16, checkbox_height=16,
                        font=ctk.CTkFont(size=11)).pack(side="left", padx=(12, 0))

        ctk.CTkButton(bar, text="Pulisci", width=65, height=28, fg_color="#4A5568",
                      hover_color="#2D3748", command=self._pulisci).pack(side="right")

        # Scrollable container (5 colonne)
        self.box_scroll = ctk.CTkScrollableFrame(self, fg_color="#0B1219", label_text="")
        self.box_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.box_scroll.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

    # ---------------- Rete UDP ----------------
    def _avvia(self):
        try:
            porta = int(self.e_porta.get().strip() or "2237")
        except Exception:
            porta = 2237
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except Exception:
                    pass
            self._sock.bind(("", porta))
            self._sock.settimeout(1.0)
            self._run = True
            threading.Thread(target=self._loop, daemon=True).start()
            self.lbl_stato.configure(text="● in ascolto…", text_color="#48BB78")
        except Exception as e:
            self.lbl_stato.configure(text=f"● errore: {e}", text_color="#FC8181")
            self._sock = None

    def _loop(self):
        while self._run and self._sock:
            try:
                data, addr = self._sock.recvfrom(8192)
                self._decodifica(data, addr)
            except socket.timeout:
                continue
            except Exception:
                break

    def _stop(self):
        self._run = False
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = None

    def _riconnetti(self):
        self._stop()
        self.after(200, self._avvia)

    def _decodifica(self, data, addr):
        try:
            pos = 0

            def u32():
                nonlocal pos
                v = struct.unpack_from(">I", data, pos)[0]; pos += 4; return v

            def i32():
                nonlocal pos
                v = struct.unpack_from(">i", data, pos)[0]; pos += 4; return v

            def u64():
                nonlocal pos
                v = struct.unpack_from(">Q", data, pos)[0]; pos += 8; return v

            def u8():
                nonlocal pos
                v = struct.unpack_from(">B", data, pos)[0]; pos += 1; return v

            def f64():
                nonlocal pos
                v = struct.unpack_from(">d", data, pos)[0]; pos += 8; return v

            def qstr():
                nonlocal pos
                ln = u32()
                if ln == 0xFFFFFFFF:
                    return ""
                v = data[pos:pos + ln].decode("utf-8", errors="replace"); pos += ln
                return v

            def qdt():
                nonlocal pos
                jd = u64(); ms = u32(); u8()
                l = jd + 68569; n = (4 * l) // 146097
                l = l - (146097 * n + 3) // 4; i = (4000 * (l + 1)) // 1461001
                l = l - (1461 * i) // 4 + 31; j = (80 * l) // 2447
                day = l - (2447 * j) // 80; l2 = j // 11
                month = j + 2 - 12 * l2; year = 100 * (n - 49) + i + l2
                h = ms // 3600000; mi = (ms % 3600000) // 60000; sec = (ms % 60000) // 1000
                return f"{year:04d}{month:02d}{day:02d}", f"{h:02d}{mi:02d}{sec:02d}"

            def skip_qdate():
                nonlocal pos
                pos += 8  # QDate julian day (int64)

            def skip_qtime():
                nonlocal pos
                pos += 4  # QTime ms (uint32)

            def skip_qdatetime():
                skip_qdate()
                skip_qtime()
                pos += 1  # timespec (uint8)

            if u32() != MAGIC:
                return
            u32()               # schema
            mtype = u32()
            client_id = qstr()  # ID WSJT-X
            if client_id:
                self._wsjtx_id = client_id

            if mtype == 1:      # Status
                dial = u64()
                mode = qstr()
                self._q.put(("status", _banda_da_mhz(dial / 1e6), mode.upper()))

            elif mtype == 2:    # Decode
                u8()            # new
                ms = u32()      # ms da mezzanotte
                snr = i32()
                dt = f64()      # delta time
                df = u32()      # delta freq (Hz)
                mode = qstr()
                msg = qstr()
                h = ms // 3600000; mi = (ms % 3600000) // 60000
                ora = f"{h:02d}:{mi:02d}"
                self._q.put(("decode", ora, snr, mode.upper(), msg, ms, df, addr, dt))

            elif mtype == 5:    # QSO Logged
                qdt()                       # DateTimeOff
                dxcall = qstr(); dxgrid = qstr()
                freq = u64(); mode = qstr()
                rst_s = qstr(); rst_r = qstr()
                pwr = qstr(); comm = qstr(); name = qstr()
                d_on, t_on = qdt()          # DateTimeOn
                ex_s = ex_r = ""
                try:
                    qstr(); qstr(); qstr()  # op_call, my_call, my_grid
                    ex_s = qstr(); ex_r = qstr()
                except Exception:
                    pass
                q = {"call": dxcall.upper(), "gridsquare": dxgrid.upper(),
                     "freq": f"{freq/1e6:.6f}".rstrip("0").rstrip("."),
                     "band": _banda_da_mhz(freq / 1e6) or self._cur_band,
                     "mode": mode.upper(), "rst_sent": rst_s, "rst_rcvd": rst_r,
                     "qso_date": d_on, "time_on": t_on,
                     "name": name, "tx_pwr": pwr, "comment": comm}
                if ex_s:
                    q["stx"] = ex_s
                if ex_r:
                    q["srx"] = ex_r
                self._q.put(("logged", q))

        except Exception:
            pass

    # ---------------- Gestione Clicks (Singolo vs Doppio) ----------------
    def _on_box_click(self, call):
        """Pianifica il click singolo (risposta UDP WSJT-X)."""
        if self._click_timer is not None:
            self.after_cancel(self._click_timer)
            self._click_timer = None
        self._click_timer = self.after(220, lambda: self._invia_reply_wsjtx(call))

    def _on_box_double_click(self, call):
        """Annulla il click singolo ed esegue il doppio click (Apri Add Log)."""
        if self._click_timer is not None:
            self.after_cancel(self._click_timer)
            self._click_timer = None
        self._doppio_click_box(call)

    # ---------------- Invio UDP Reply a WSJT-X ----------------
    def _invia_reply_wsjtx(self, call):
        """Invia il pacchetto UDP 'Reply' a WSJT-X per avviare la chiamata."""
        sp = self._spot_data.get(call)
        if not sp or not self._sock:
            return
        addr = sp.get("addr")
        if not addr:
            return

        try:
            out = bytearray()
            out += struct.pack(">III", MAGIC, 2, 4)

            cid_b = self._wsjtx_id.encode("utf-8")
            out += struct.pack(">I", len(cid_b)) + cid_b

            out += struct.pack(">Ii", sp["ms"], sp["snr"])
            out += struct.pack(">dI", float(sp.get("dt", 0.0)), sp["df"])

            mb = sp["mode"].encode("utf-8")
            out += struct.pack(">I", len(mb)) + mb
            msg_b = sp["msg"].encode("utf-8")
            out += struct.pack(">I", len(msg_b)) + msg_b

            out += struct.pack(">BB", 0, 0)

            self._sock.sendto(out, addr)
            self.lbl_stato.configure(text=f"● Chiamata TX -> {call}", text_color="#63B3ED")
        except Exception as e:
            self.lbl_stato.configure(text=f"● Errore TX UDP: {e}", text_color="#FC8181")

    # ---------------- Log Automatico QSO (mtype 5) ----------------
    def _registra(self, qso):
        """Registra un QSO ricevuto da WSJT-X (QSO Logged)."""
        try:
            if self._modo == "contest":
                cid = (self._contest_id or "").strip()
                if not cid:
                    self.lbl_stato.configure(text="● QSO ignorato: manca il nome contest",
                                             text_color="#F6AD55")
                    return
                qso["contest_id"] = cid
                self._salva_contest(qso)
            else:
                try:
                    self.app._arricchisci_country([qso])
                except Exception:
                    pass
                self.app.qsos_caricati.append(qso)
                self.app._log_modificato = True
                self.app.qsos_caricati.sort(key=lambda x: (
                    str(x.get("qso_date", "")).strip(),
                    str(x.get("time_on", "")).strip().zfill(6)))
                self.app.qsos_filtrati = list(self.app.qsos_caricati)
                self.app._aggiorna_tree()
            self.lbl_stato.configure(text=f"● A LOG: {qso.get('call','')}",
                                     text_color="#68D391")
            try:
                self._ricalcola()
            except Exception:
                pass
        except Exception as e:
            self.lbl_stato.configure(text=f"● Errore AutoLog: {e}", text_color="#FC8181")

    def _contest_path(self):
        import os
        cid = (self._contest_id or "").strip()
        if not cid:
            return None
        try:
            call = (self.app.entry_owner.get().strip().upper() or "NOCALL")
            safe = "".join(ch if (ch.isalnum() or ch in " _-") else "_"
                           for ch in cid).strip().replace(" ", "_")
            return os.path.join(self.app._cartella_backup(), f"contest_{safe}_{call}.adi")
        except Exception:
            return None

    def _salva_contest(self, qso):
        import os
        path = self._contest_path()
        if not path:
            return
        lista = []
        if os.path.exists(path):
            try:
                import adif_io
                qs, _ = adif_io.read_from_string(open(path, encoding="utf-8").read())
                lista = [{str(k).lower(): v for k, v in dict(x).items()} for x in qs]
            except Exception:
                lista = []
        lista.append(qso)
        try:
            self.app._scrivi_adif(path, lista)
        except Exception:
            pass

    def _stato_call(self, call):
        call = call.upper()
        base = _call_base(call)
        b = (self._cur_band or "").lower()
        m = (self._cur_mode or "").upper()
        
        try:
            qsos_totali = self.app.qsos_caricati
        except Exception:
            qsos_totali = []

        # Se in modalità Contest, si controllano SOLO i QSO con lo stesso contest_id
        if self._modo == "contest":
            cid = (self._contest_id or "").strip().upper()
            qsos = [q for q in qsos_totali if str(q.get("contest_id", "")).strip().upper() == cid]
        else:
            qsos = qsos_totali

        worked = False
        for q in qsos:
            c = str(q.get("call", "")).upper()
            if not c:
                continue
            if c == call or _call_base(c) == base:
                worked = True
                qb = str(q.get("band", "")).lower()
                qm = str(q.get("mode", "")).upper()
                if (not b or qb == b) and (not m or qm == m):
                    return "DUPE", "dupe"
        if worked:
            return "NEW SLOT", "slot"
        return "NEW", "new"

    # ---------------- Loop UI & Render Box ----------------
    def _aggiorna_cty(self):
        """Scarica l'ultimo cty.dat e ricarica prefissi + bandiere."""
        if cty is None:
            return
        from tkinter import messagebox
        import os
        # percorso di destinazione: dove c'è già cty.dat, altrimenti cartella programma
        dest = None
        for base in [os.path.dirname(os.path.abspath(sys.argv[0])), os.getcwd()]:
            pth = os.path.join(base, "cty.dat")
            if os.path.exists(pth):
                dest = pth; break
        if dest is None:
            try:
                import config as _cfg
                dest = os.path.join(os.path.dirname(os.path.abspath(_cfg.__file__)), "cty.dat")
            except Exception:
                dest = os.path.join(os.getcwd(), "cty.dat")
        if not messagebox.askyesno("Aggiorna cty.dat",
                                   "Scaricare l'ultimo cty.dat da country-files.com?\n"
                                   "(Il file attuale verrà salvato come cty.dat.bak)", parent=self):
            return
        self.lbl_stato.configure(text="● Scarico cty.dat…", text_color="#63B3ED")
        self.update_idletasks()
        try:
            ok, msg = cty.aggiorna(dest)
        except Exception as e:
            ok, msg = False, str(e)
        if ok:
            self._flag_cache = {}          # ricalcola le bandiere
            try: self._ricalcola()
            except Exception: pass
            self.lbl_stato.configure(text="● " + msg, text_color="#68D391")
        else:
            self.lbl_stato.configure(text="● " + msg, text_color="#FC8181")
        messagebox.showinfo("Aggiorna cty.dat", msg, parent=self)

    def _flag_img(self, iso):
        iso = (iso or "").lower()
        if not iso or not self._flags_dir:
            return None
        if iso in self._flag_cache:
            return self._flag_cache[iso]
        img = None
        path = os.path.join(self._flags_dir, iso + ".png")
        if os.path.exists(path):
            try:
                from PIL import Image
                with Image.open(path) as _im:
                    _im.load()
                    _cp = _im.convert("RGBA")
                img = ctk.CTkImage(light_image=_cp, dark_image=_cp, size=(30, 20))
            except Exception:
                img = None
        self._flag_cache[iso] = img
        return img

    def _applica_tema(self):
        """Riafferma lo sfondo e la visibilità (dopo un cambio tema dell'app)."""
        try:
            self.configure(fg_color="#0E141B")
        except Exception:
            pass
        try:
            if self.state() == "withdrawn":
                self.deiconify()
            self.lift()
        except Exception:
            pass

    def _pompa(self):
        # Auto-recupero: il cambio tema (set_appearance_mode) può nascondere
        # la Toplevel; se risulta 'withdrawn' la ri-mostriamo subito.
        try:
            if self.state() == "withdrawn":
                self.configure(fg_color="#0E141B")
                self.deiconify(); self.lift()
        except Exception:
            pass
        try:
            _n = 0
            while _n < 40:
                ev = self._q.get_nowait()
                _n += 1
                if ev[0] == "status":
                    _, banda, mode = ev
                    if banda:
                        self._cur_band = banda
                    if mode:
                        self._cur_mode = mode
                    self.lbl_bm.configure(text=f"{self._cur_band or '—'}  {self._cur_mode or ''}")
                elif ev[0] == "decode":
                    _, ora, snr, mode, msg, ms, df, addr, dt = ev
                    # Nuovo periodo di decodifica -> svuota e riparte (stile JTAlert)
                    if self._ciclo_ms is not None and ms != self._ciclo_ms:
                        self._reset_ciclo()
                    self._ciclo_ms = ms
                    self._nuovo_spot(ora, snr, mode or self._cur_mode, msg, ms, df, addr, dt)
                elif ev[0] == "logged":
                    try:
                        self.lbl_stato.configure(text=f"● QSO ricevuto da WSJT-X: {ev[1].get('call','')}",
                                                 text_color="#63B3ED")
                    except Exception:
                        pass
                    self._registra(ev[1])
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            self._scadenza()
        except Exception:
            pass
        if self._need_regrid:
            self._need_regrid = False
            try:
                self._riorganizza_griglia()
            except Exception:
                pass
        try:
            ritardo = 30 if not self._q.empty() else 300
            self.after(ritardo, self._pompa)
        except Exception:
            pass

    def _nuovo_spot(self, ora, snr, mode, msg, ms, df, addr, dt=0.0):
        try:
            self._nuovo_spot_impl(ora, snr, mode, msg, ms, df, addr, dt)
        except Exception:
            pass

    def _nuovo_spot_impl(self, ora, snr, mode, msg, ms, df, addr, dt=0.0):
        call = _dx_call_da_messaggio(msg)
        if not call:
            return

        my_call = self._get_my_call()
        per_me = (my_call in msg.upper())

        grid = ""
        for t in msg.upper().split():
            if re.match(r"^[A-R]{2}[0-9]{2}$", t):
                grid = t
                break

        stato, tag = self._stato_call(call)
        if self._solo_nuovi and tag == "dupe" and not per_me:
            self._rimuovi_box(call)
            return

        self._spot_data[call] = {
            "ora": ora, "snr": snr, "mode": mode, "msg": msg,
            "ms": ms, "df": df, "addr": addr, "grid": grid, "dt": dt
        }

        # Colori Box
        if per_me:
            bg_color = "#742A2A"      # Rosso alert (una stazione TI sta chiamando)
            border_color = "#FEB2B2"
            txt_tag = my_call
        elif tag == "dupe":
            bg_color = "#2A1B1B"      # Scuro/Rosso
            border_color = "#E53E3E"
            txt_tag = "DUPE"
        elif tag == "slot":
            bg_color = "#152A3A"      # Scuro/Azzurro
            border_color = "#3182CE"
            txt_tag = "NEW SLOT"
        else:
            bg_color = "#122A1C"      # Scuro/Verde
            border_color = "#38A169"
            txt_tag = "NEW"

        if call in self._cards:
            w = self._cards[call]
            w["frame"].configure(fg_color=bg_color, border_color=border_color)
            w["lbl_snr"].configure(text=f"{snr:+d}dB")
            w["lbl_msg"].configure(text=msg)
            w["lbl_tag"].configure(text=txt_tag)
            w["per_me"] = per_me
            w["ts"] = time.time()
        else:
            # Box compatto a 5 colonne
            frm = ctk.CTkFrame(self.box_scroll, fg_color=bg_color, border_width=1,
                               border_color=border_color, corner_radius=6)
            
            _iso = ""
            try:
                if cty is not None:
                    _iso = cty.iso2(call)
            except Exception:
                _iso = ""
            _img = self._flag_img(_iso)
            if _img is not None:
                lbl_c = ctk.CTkLabel(frm, text=" " + call, image=_img, compound="left",
                                     font=ctk.CTkFont(size=18, weight="bold"))
            else:
                _txt_call = (_iso + " " + call) if _iso else call
                lbl_c = ctk.CTkLabel(frm, text=_txt_call, font=ctk.CTkFont(size=18, weight="bold"))
            lbl_c.pack(anchor="w", padx=6, pady=(3, 0))

            sub = ctk.CTkFrame(frm, fg_color="transparent")
            sub.pack(fill="x", padx=6, pady=0)
            
            lbl_s = ctk.CTkLabel(sub, text=f"{snr:+d}dB", font=ctk.CTkFont(size=10, weight="bold"), text_color="#CBD5E0")
            lbl_s.pack(side="left")
            
            lbl_g = ctk.CTkLabel(sub, text=grid, font=ctk.CTkFont(size=10), text_color="#A0AEC0")
            lbl_g.pack(side="right")

            lbl_m = ctk.CTkLabel(frm, text=msg, font=ctk.CTkFont(size=13, weight="bold"),
                                 text_color="#E2E8F0", anchor="w")
            lbl_m.pack(fill="x", padx=6, pady=(0, 3))

            lbl_t = ctk.CTkLabel(frm, text=txt_tag, font=ctk.CTkFont(size=9, weight="bold"),
                                 text_color=border_color, anchor="e")
            lbl_t.pack(fill="x", padx=6, pady=(0, 3))

            # Registrazione eventi click separati
            widgets_box = [frm, lbl_c, sub, lbl_s, lbl_g, lbl_m, lbl_t]
            for wid in widgets_box:
                wid.bind("<Button-1>", lambda e, c=call: self._on_box_click(c))
                wid.bind("<Double-Button-1>", lambda e, c=call: self._on_box_double_click(c))

            self._cards[call] = {
                "frame": frm, "lbl_snr": lbl_s, "lbl_msg": lbl_m, "lbl_tag": lbl_t,
                "per_me": per_me, "ts": time.time()
            }
            self._ordine.append(call)
            self._pota_box()
            self._need_regrid = True

    def _doppio_click_box(self, call):
        """Al doppio click apre la finestra manuale 'Aggiungi QSO'."""
        try:
            dlg = getattr(self.app, "_aggiungi_qso_dlg", None)
            if dlg is None or not (hasattr(dlg, "winfo_exists") and dlg.winfo_exists()):
                self.app.apri_aggiungi_qso()
                dlg = getattr(self.app, "_aggiungi_qso_dlg", None)

            def _fill():
                try:
                    if hasattr(dlg, "_aq_call"):
                        dlg._aq_call.delete(0, "end")
                        dlg._aq_call.insert(0, call)
                        dlg._aq_call.focus_set()
                        dlg._aq_call.event_generate("<KeyRelease>")
                    dlg.lift()
                except Exception:
                    pass
            self.app.after(150, _fill)
        except Exception:
            pass

    def _reset_ciclo(self):
        """Svuota i box all'inizio di un nuovo periodo di decodifica."""
        try:
            for c, w in list(self._cards.items()):
                try: w["frame"].destroy()
                except Exception: pass
            self._cards.clear()
            self._ordine.clear()
            self._spot_data.clear()
            self._need_regrid = True
        except Exception:
            pass

    def _scadenza(self):
        """Rimuove i box non più decodificati da un po' (i 'PER TE' durano di più)."""
        try:
            now = time.time()
            morti = []
            for c, w in list(self._cards.items()):
                lim = self._SCAD * 2 if w.get("per_me") else self._SCAD
                if now - w.get("ts", now) > lim:
                    morti.append(c)
            for c in morti:
                w = self._cards.pop(c, None)
                try: self._ordine.remove(c)
                except ValueError: pass
                self._spot_data.pop(c, None)
                if w:
                    try: w["frame"].destroy()
                    except Exception: pass
            if morti:
                self._need_regrid = True
        except Exception:
            pass

    def _pota_box(self):
        """Mantiene al massimo _MAX_BOX riquadri: rimuove i più vecchi
        (mai i box 'PER TE'), così la griglia resta fluida."""
        try:
            while len(self._cards) > self._MAX_BOX:
                tolto = None
                for c in list(self._ordine):
                    if c in self._cards and not self._cards[c].get("per_me"):
                        tolto = c
                        break
                if tolto is None:
                    break
                self._ordine.remove(tolto)
                w = self._cards.pop(tolto, None)
                if w:
                    try: w["frame"].destroy()
                    except Exception: pass
        except Exception:
            pass

    def _riorganizza_griglia(self):
        cols = 5
        calls = list(self._cards.keys())
        calls.sort(key=lambda c: 0 if self._get_my_call() in self._spot_data.get(c, {}).get("msg", "").upper() else 1)
        
        for idx, c in enumerate(calls):
            r = idx // cols
            col = idx % cols
            try:
                self._cards[c]["frame"].grid(row=r, column=col, padx=3, pady=3, sticky="nsew")
            except Exception:
                pass

    def _rimuovi_box(self, call):
        if call in self._cards:
            w = self._cards.pop(call)
            try: self._ordine.remove(call)
            except ValueError: pass
            try: w["frame"].destroy()
            except Exception: pass
            self._riorganizza_griglia()

    # ---------------- Controlli UI ----------------
    def _cambia_modo(self, scelta):
        self._modo = "contest" if scelta == "Contest" else "log"
        self._ricalcola()

    def _set_contest(self):
        self._contest_id = self.e_contest.get().strip()
        if self._modo == "contest":
            self._ricalcola()

    def _toggle_nuovi(self):
        self._solo_nuovi = bool(self.var_nuovi.get())
        self._ricalcola()

    def _ricalcola(self):
        for call in list(self._cards.keys()):
            sp = self._spot_data.get(call, {})
            if sp:
                self._nuovo_spot(sp["ora"], sp["snr"], sp["mode"], sp["msg"], sp["ms"], sp["df"], sp["addr"], sp.get("dt", 0.0))

    def _pulisci(self):
        for c, w in list(self._cards.items()):
            try: w["frame"].destroy()
            except Exception: pass
        self._cards.clear()
        self._spot_data.clear()
        self._ordine.clear()
        self._need_regrid = False

    def _chiudi(self):
        self._stop()
        try:
            self.destroy()
        except Exception:
            pass