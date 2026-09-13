"""
FZR ALERT — Monitor WSJT-X con dup-check integrato (contest / DX checker).

Ascolta i pacchetti UDP di WSJT-X (Decode + Status) e, per ogni nominativo
che transita nella Band Activity, controlla nel log della stazione (o nella
sessione contest) se è:
  - DUPE      (già lavorato su questa banda+modo)      -> rosso
  - NEW SLOT  (lavorato, ma non su questa banda/modo)  -> ambra
  - NEW       (mai lavorato)                            -> verde

Non trasmette e non modifica nulla su WSJT-X: solo lettura UDP.
Doppio clic su una riga -> precompila la finestra "Aggiungi QSO".
"""

import socket
import struct
import threading
import queue
import re

import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

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


_RE_CALL = re.compile(r"^[A-Z0-9]{1,3}[0-9][A-Z0-9]*[A-Z](/[A-Z0-9]+)?$")


def _pulisci_call(t):
    t = (t or "").upper().strip().strip("<>")
    return t if _RE_CALL.match(t) else ""


def _dx_call_da_messaggio(msg):
    """Estrae il nominativo 'DX' interessante da un messaggio WSJT-X.
    - 'CQ [DX/dir] CALL GRID'  -> CALL (chi chiama CQ, lavorabile)
    - 'CALL1 CALL2 report'     -> CALL2 (mittente)
    """
    toks = (msg or "").upper().split()
    if not toks:
        return ""
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
        self.title("FZR ALERT — monitor WSJT-X")
        self.geometry("780x580")
        self.minsize(640, 440)
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
        self._modo = "log"          # "log" | "contest"
        self._contest_id = ""
        self._solo_nuovi = False
        self._righe = {}            # call -> iid nel treeview

        self._costruisci_ui()
        self._avvia()
        self.after(400, self._pompa)
        self.protocol("WM_DELETE_WINDOW", self._chiudi)

    # ---------------- UI ----------------
    def _costruisci_ui(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 4))

        ctk.CTkLabel(top, text="Porta UDP:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.e_porta = ctk.CTkEntry(top, width=64, height=28)
        self.e_porta.insert(0, "2237")
        self.e_porta.pack(side="left", padx=(4, 10))

        self.btn_conn = ctk.CTkButton(top, text="Riconnetti", width=90, height=28,
                                      command=self._riconnetti)
        self.btn_conn.pack(side="left", padx=(0, 10))

        self.lbl_stato = ctk.CTkLabel(top, text="● in ascolto…",
                                      font=ctk.CTkFont(size=11, weight="bold"),
                                      text_color="#48BB78")
        self.lbl_stato.pack(side="left")

        self.lbl_bm = ctk.CTkLabel(top, text="—", font=ctk.CTkFont(size=11, weight="bold"),
                                   text_color="#63B3ED")
        self.lbl_bm.pack(side="right")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=10, pady=(0, 6))

        self.seg = ctk.CTkSegmentedButton(bar, values=["Log", "Contest"],
                                          command=self._cambia_modo, width=180, height=30,
                                          dynamic_resizing=False,
                                          font=ctk.CTkFont(size=12, weight="bold"))
        self.seg.set("Log")
        self.seg.pack(side="left")

        ctk.CTkLabel(bar, text="Contest:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(12, 4))
        self.e_contest = ctk.CTkEntry(bar, width=140, height=28)
        self.e_contest.pack(side="left")
        self.e_contest.bind("<KeyRelease>", lambda e: self._set_contest())

        self.var_nuovi = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(bar, text="Solo nuovi", variable=self.var_nuovi,
                        command=self._toggle_nuovi, checkbox_width=16, checkbox_height=16,
                        font=ctk.CTkFont(size=11)).pack(side="left", padx=(14, 0))

        ctk.CTkButton(bar, text="Pulisci", width=70, height=28, fg_color="#4A5568",
                      hover_color="#2D3748", command=self._pulisci).pack(side="right")

        # Tabella
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("ALERT.Treeview", background="#0b1219", fieldbackground="#0b1219",
                     foreground="#E2E8F0", rowheight=24, font=("Consolas", 11), borderwidth=0)
        st.configure("ALERT.Treeview.Heading", font=("Arial", 10, "bold"))

        cols = ("ora", "call", "grid", "db", "banda", "modo", "stato")
        self.tv = ttk.Treeview(wrap, columns=cols, show="headings", style="ALERT.Treeview")
        intest = {"ora": ("Ora", 60), "call": ("Nominativo", 120), "grid": ("Loc", 70),
                  "db": ("dB", 50), "banda": ("Banda", 70), "modo": ("Modo", 70),
                  "stato": ("Stato", 110)}
        for c in cols:
            t, w = intest[c]
            self.tv.heading(c, text=t)
            self.tv.column(c, width=w, anchor="w")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tv.pack(side="left", fill="both", expand=True)

        self.tv.tag_configure("dupe", foreground="#FC8181")
        self.tv.tag_configure("slot", foreground="#F6AD55")
        self.tv.tag_configure("new", foreground="#68D391")
        self.tv.bind("<Double-1>", self._doppio_click)

    # ---------------- rete ----------------
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
                data, _ = self._sock.recvfrom(8192)
                self._decodifica(data)
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

    def _decodifica(self, data):
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

            if u32() != MAGIC:
                return
            u32()               # schema
            mtype = u32()
            qstr()              # id WSJT-X

            if mtype == 1:      # Status
                dial = u64()
                mode = qstr()
                self._q.put(("status", _banda_da_mhz(dial / 1e6), mode.upper()))
            elif mtype == 2:    # Decode
                u8()            # new
                ms = u32()      # tempo (ms da mezzanotte)
                snr = i32()
                f64()           # delta time
                u32()           # delta freq
                mode = qstr()
                msg = qstr()
                h = ms // 3600000; mi = (ms % 3600000) // 60000
                ora = f"{h:02d}:{mi:02d}"
                self._q.put(("decode", ora, snr, mode.upper(), msg))
            elif mtype == 5:    # QSO Logged
                qdt()                       # DateTimeOff
                dxcall = qstr(); dxgrid = qstr()
                freq = u64(); mode = qstr()
                rst_s = qstr(); rst_r = qstr()
                pwr = qstr(); comm = qstr(); name = qstr()
                d_on, t_on = qdt()          # DateTimeOn
                ex_s = ex_r = ""
                try:
                    qstr(); qstr(); qstr()  # op_call, my_call, my_grid (versioni recenti)
                    ex_s = qstr(); ex_r = qstr()   # exchange sent/rcvd
                except Exception:
                    pass
                q = {"call": dxcall.upper(), "gridsquare": dxgrid.upper(),
                     "freq": f"{freq/1e6:.6f}".rstrip("0").rstrip("."),
                     "band": _banda_da_mhz(freq / 1e6), "mode": mode.upper(),
                     "rst_sent": rst_s, "rst_rcvd": rst_r,
                     "qso_date": d_on, "time_on": t_on,
                     "name": name, "tx_pwr": pwr, "comment": comm}
                if ex_s:
                    q["stx"] = ex_s
                if ex_r:
                    q["srx"] = ex_r
                self._q.put(("logged", q))
        except Exception:
            pass

    # ---------------- dup-check ----------------
    def _stato_call(self, call):
        call = call.upper()
        base = _call_base(call)
        b = (self._cur_band or "").lower()
        m = (self._cur_mode or "").upper()
        try:
            qsos = self.app.qsos_caricati
        except Exception:
            qsos = []
        if self._modo == "contest" and self._contest_id:
            cid = self._contest_id.upper()
            qsos = [q for q in qsos if str(q.get("contest_id", "")).upper() == cid]
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

    # ---------------- loop UI ----------------
    def _pompa(self):
        try:
            while True:
                ev = self._q.get_nowait()
                if ev[0] == "status":
                    _, banda, mode = ev
                    if banda:
                        self._cur_band = banda
                    if mode:
                        self._cur_mode = mode
                    self.lbl_bm.configure(text=f"{self._cur_band or '—'}  {self._cur_mode or ''}")
                elif ev[0] == "decode":
                    _, ora, snr, mode, msg = ev
                    self._nuovo_spot(ora, snr, mode or self._cur_mode, msg)
                elif ev[0] == "logged":
                    self._registra(ev[1])
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            self.after(400, self._pompa)
        except Exception:
            pass

    def _nuovo_spot(self, ora, snr, mode, msg):
        call = _dx_call_da_messaggio(msg)
        if not call:
            return
        # locatore se presente nel messaggio (token di 4 lettere/cifre tipo JN35)
        grid = ""
        for t in msg.upper().split():
            if re.match(r"^[A-R]{2}[0-9]{2}$", t):
                grid = t; break
        stato, tag = self._stato_call(call)
        if self._solo_nuovi and tag == "dupe":
            # rimuovi eventuale riga esistente diventata dupe
            iid = self._righe.pop(call, None)
            if iid and self.tv.exists(iid):
                self.tv.delete(iid)
            return
        vals = (ora, call, grid, str(snr), self._cur_band or "", mode or "", stato)
        iid = self._righe.get(call)
        if iid and self.tv.exists(iid):
            self.tv.item(iid, values=vals, tags=(tag,))
            self.tv.move(iid, "", 0)
        else:
            iid = self.tv.insert("", 0, values=vals, tags=(tag,))
            self._righe[call] = iid
        # limita a 250 righe
        figli = self.tv.get_children("")
        if len(figli) > 250:
            for extra in figli[250:]:
                self.tv.delete(extra)
                for k, v in list(self._righe.items()):
                    if v == extra:
                        self._righe.pop(k, None)

    # ---------------- controlli ----------------
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
        # ricolora le righe presenti con i criteri correnti
        for call, iid in list(self._righe.items()):
            if not self.tv.exists(iid):
                self._righe.pop(call, None); continue
            stato, tag = self._stato_call(call)
            if self._solo_nuovi and tag == "dupe":
                self.tv.delete(iid); self._righe.pop(call, None); continue
            vals = list(self.tv.item(iid, "values"))
            vals[6] = stato
            self.tv.item(iid, values=vals, tags=(tag,))

    def _pulisci(self):
        for iid in self.tv.get_children(""):
            self.tv.delete(iid)
        self._righe.clear()

    def _doppio_click(self, _e):
        sel = self.tv.focus()
        if not sel:
            return
        vals = self.tv.item(sel, "values")
        if not vals:
            return
        call = vals[1]
        try:
            dlg = getattr(self.app, "_aggiungi_qso_dlg", None)
            if dlg is None or not (hasattr(dlg, "winfo_exists") and dlg.winfo_exists()):
                self.app.apri_aggiungi_qso()
                dlg = getattr(self.app, "_aggiungi_qso_dlg", None)

            def _fill():
                try:
                    if hasattr(dlg, "_aq_call"):
                        dlg._aq_call.delete(0, "end"); dlg._aq_call.insert(0, call)
                        dlg._aq_call.focus_set()
                        try:
                            dlg._aq_call.event_generate("<KeyRelease>")
                        except Exception:
                            pass
                    dlg.lift(); dlg.focus_force()
                except Exception:
                    pass
            self.app.after(250, _fill)
        except Exception:
            pass

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
            self.lbl_stato.configure(text=f"● loggato: {qso.get('call','')}",
                                     text_color="#68D391")
        except Exception:
            pass

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

    def _chiudi(self):
        self._stop()
        try:
            self.destroy()
        except Exception:
            pass
