# -*- coding: utf-8 -*-
"""
Cruscotto satellitare per ADIF FZR (finestra unica).
Sinistra: mappa con posizione IN TEMPO REALE del satellite selezionato
          (footprint, osservatore, traccia del prossimo passaggio).
Destra:   selettore satellite, dati live (el/az/distanza), tabella passaggi.
Motore: radio/satellite.py (skyfield).  Mappa: coste incorporate + matplotlib.
"""

import os
import threading
import traceback
from datetime import datetime, timezone

import customtkinter as ctk
from tkinter import messagebox
import tkinter.ttk as ttk

_MPL_OK = True
_MPL_ERR = ""
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
except Exception as _e:
    _MPL_OK = False
    _MPL_ERR = repr(_e)

from config import locator_to_latlon, estrai_locator_da_testo, T
from radio import satellite as SAT
try:
    from radio.coastlines import COSTE
except Exception:
    COSTE = []

def _LOG(msg):
    try:
        _f = os.path.join(os.path.expanduser("~"), "adif_fzr_sat_log.txt")
        with open(_f, "a", encoding="utf-8") as _h:
            _h.write(str(msg) + "\n")
    except Exception:
        pass

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".adif_fzr_tle")
INTERVALLO_LIVE_MS = 5000   # aggiornamento posizione ogni 5 s

BG = "#0d1522"; COAST = "#3a5a80"; GRID = "#1e2f4d"
OSS = "#9edc3a"; TRACK = "#ffd54a"; FOOT = "#9edc3a"; SATCOL = "#ff6b6b"
TXT = "#e9eef7"; MUT = "#8fa2c0"


def _spezza(cerchio):
    xs = [p[1] for p in cerchio]; ys = [p[0] for p in cerchio]
    sx, sy = [[xs[0]]], [[ys[0]]]
    for i in range(1, len(xs)):
        if abs(xs[i] - xs[i - 1]) > 180:
            sx.append([]); sy.append([])
        sx[-1].append(xs[i]); sy[-1].append(ys[i])
    return sx, sy


class SatellitiDialog(ctk.CTkToplevel):
    def __init__(self, parent, app_ref=None):
        _LOG("=== apertura cruscotto ===")
        super().__init__(parent)
        _LOG("1: toplevel creato")
        self.app_ref = app_ref
        self.title("Satelliti — cruscotto")
        self.geometry("1180x680")
        self.resizable(True, True)
        self.grab_set()

        self._sats = {}
        self._passaggi = []
        self._selezionati = set(self._carica_selezione())
        self._sat_corrente = None
        self._busy = False
        self._live_on = False
        self._foot_lines = []
        self._track_line = None

        if not _MPL_OK:
            ctk.CTkLabel(self, text="Errore matplotlib (finestra mappa)",
                         font=ctk.CTkFont(size=15, weight="bold"),
                         text_color="#ff6b6b").pack(pady=(16, 6))
            box = ctk.CTkTextbox(self, width=760, height=180)
            box.pack(padx=16, pady=8)
            box.insert("1.0", "matplotlib non si e' caricato:\n\n" + _MPL_ERR +
                       "\n\nQuesto e' il vero motivo per cui la finestra non si apre.")
            ctk.CTkButton(self, text="Chiudi", command=self.destroy).pack(pady=8)
            return

        if not SAT.SKYFIELD_OK:
            ctk.CTkLabel(self, text="Passaggi satelliti",
                         font=ctk.CTkFont(size=16, weight="bold")).pack(pady=12)
            ctk.CTkLabel(self,
                text=("La libreria 'skyfield' non e' installata.\n"
                      "Installala con:  pip install skyfield\npoi riapri."),
                text_color="#ff6b6b", justify="center").pack(pady=30)
            ctk.CTkButton(self, text="Chiudi", command=self.destroy).pack()
            return

        _LOG("2: prima di stile_scuro")
        self._stile_scuro()
        _LOG("3: stile ok, prima del layout")

        # ══ layout a due colonne ══
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # ── SINISTRA: mappa ──
        sx = ctk.CTkFrame(self)
        sx.grid(row=0, column=0, sticky="nsew", padx=(10, 6), pady=10)
        _LOG("4: prima di creare Figure matplotlib")
        self.fig = Figure(figsize=(7, 5), dpi=100, facecolor=BG)
        _LOG("5: Figure creata")
        self.ax = self.fig.add_subplot(111)
        self._disegna_base()
        _LOG("6: prima di FigureCanvasTkAgg")
        self.canvas = FigureCanvasTkAgg(self.fig, master=sx)
        _LOG("7: canvas creato OK")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.lbl_map = ctk.CTkLabel(sx, text="Seleziona un satellite per vederne la posizione",
                                    text_color=MUT)
        self.lbl_map.pack(pady=(4, 0))

        # ── DESTRA: controlli + dati + passaggi ──
        dx = ctk.CTkFrame(self)
        dx.grid(row=0, column=1, sticky="nsew", padx=(6, 10), pady=10)

        top = ctk.CTkFrame(dx, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(top, text="Locatore:").grid(row=0, column=0, padx=(0, 4), sticky="e")
        self.var_loc = ctk.StringVar(value=self._locatore_operatore())
        ctk.CTkEntry(top, textvariable=self.var_loc, width=100).grid(row=0, column=1)
        ctk.CTkLabel(top, text="Ore:").grid(row=0, column=2, padx=(10, 4), sticky="e")
        self.var_ore = ctk.StringVar(value="24")
        ctk.CTkOptionMenu(top, values=["6", "12", "24", "48"], variable=self.var_ore,
                          width=64).grid(row=0, column=3)
        ctk.CTkLabel(top, text="El.min:").grid(row=0, column=4, padx=(10, 4), sticky="e")
        self.var_elev = ctk.StringVar(value="10")
        ctk.CTkOptionMenu(top, values=["0", "5", "10", "20"], variable=self.var_elev,
                          width=64).grid(row=0, column=5)

        selrow = ctk.CTkFrame(dx, fg_color="transparent")
        selrow.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(selrow, text="Satellite:").pack(side="left")
        self.var_sat = ctk.StringVar(value="")
        self.menu_sat = ctk.CTkOptionMenu(selrow, values=["—"], variable=self.var_sat,
                                          width=180, command=self._cambia_sat)
        self.menu_sat.pack(side="left", padx=6)
        ctk.CTkButton(selrow, text="Scegli…", width=70,
                      command=self._apri_selezione).pack(side="left")
        # Ponte al logging: apre Aggiungi QSO col satellite selezionato,
        # precompilando TX/RX/SAT_MODE dal database frequenze.
        try:
            _txt_log = T("aq_logga_sat")
        except Exception:
            _txt_log = "➕ Logga QSO"
        ctk.CTkButton(selrow, text=_txt_log, width=110,
                      fg_color="#276749", hover_color="#2F855A",
                      command=self._logga_qso).pack(side="right")

        # pannello dati live
        self.box_live = ctk.CTkFrame(dx)
        self.box_live.pack(fill="x", padx=8, pady=6)
        self.lbl_live = ctk.CTkLabel(self.box_live, text="Posizione live: —",
                                     text_color=TXT, justify="left", anchor="w",
                                     font=ctk.CTkFont(size=13))
        self.lbl_live.pack(fill="x", padx=10, pady=8)

        # tabella passaggi
        cont = ctk.CTkFrame(dx)
        cont.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        cols = ("inizio", "durata", "elmax", "az")
        self.tree = ttk.Treeview(cont, columns=cols, show="headings",
                                 height=12, style="Sat.Treeview")
        for c, (t, w) in {"inizio": ("Inizio (AOS)", 130), "durata": ("Durata", 70),
                          "elmax": ("El. max", 70), "az": ("Antenna", 120)}.items():
            self.tree.heading(c, text=t); self.tree.column(c, width=w, anchor="center")
        vsb = ttk.Scrollbar(cont, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("top", background="#1e3a1e", foreground="#c8f7c8")
        self.tree.tag_configure("buono", background="#233046", foreground="#e9eef7")

        self.lbl_stato = ctk.CTkLabel(dx, text="", text_color=MUT, anchor="w")
        self.lbl_stato.pack(fill="x", padx=10, pady=(0, 6))

        _LOG("8: fine init, avvio caricamento")
        self.protocol("WM_DELETE_WINDOW", self._chiudi)
        self.after(200, self._carica_e_calcola)

    # ── stile tabella scura ──
    def _stile_scuro(self):
        st = ttk.Style(self)
        try: st.theme_use("default")
        except Exception: pass
        st.configure("Sat.Treeview", background="#152238", fieldbackground="#152238",
                     foreground=TXT, rowheight=24, borderwidth=0)
        st.configure("Sat.Treeview.Heading", background="#233046", foreground=TXT,
                     relief="flat", font=("Segoe UI", 10, "bold"))
        st.map("Sat.Treeview", background=[("selected", "#2a3aa0")],
               foreground=[("selected", "#ffffff")])

    # ── mappa base ──
    def _disegna_base(self):
        ax = self.ax; ax.clear(); ax.set_facecolor(BG)
        for l in COSTE:
            ax.plot([p[0] for p in l], [p[1] for p in l], color=COAST, lw=0.6, zorder=1)
        ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
        ax.set_xticks(range(-180, 181, 60)); ax.set_yticks(range(-90, 91, 30))
        ax.grid(True, color=GRID, lw=0.4); ax.tick_params(colors=MUT, labelsize=7)
        for s in ax.spines.values(): s.set_color(GRID)
        if self._coord():
            la, lo = self._coord()
            ax.plot(lo, la, marker="*", color=OSS, markersize=15, zorder=6)
        self._foot_lines = []
        self._track_line = None
        (self._sat_dot,) = ax.plot([], [], marker="o", color=SATCOL, markersize=11, zorder=7)
        self._sat_txt = ax.annotate("", (0, 0), textcoords="offset points",
                                    xytext=(10, 8), color=SATCOL, fontsize=9, weight="bold")
        self.fig.tight_layout()

    # ── dati operatore ──
    def _locatore_operatore(self):
        try:
            app = self.app_ref
            if app is not None:
                if getattr(app, "profilo_attivo", None) and hasattr(app, "_carica_profili"):
                    dati = app._carica_profili().get(app.profilo_attivo, {})
                    for k in ("locator", "my_gridsquare", "gridsquare", "grid"):
                        v = (dati.get(k) or "").strip()
                        if v: return v.upper()
                if hasattr(app, "entry_details"):
                    loc = estrai_locator_da_testo(app.entry_details.get())
                    if loc: return loc.upper()
        except Exception:
            pass
        return ""

    def _coord(self):
        var = getattr(self, "var_loc", None)
        if var is None:
            return None
        loc = (var.get() or "").strip().upper()
        if not loc: return None
        try: return locator_to_latlon(loc)
        except Exception: return None

    # ── selezione satelliti persistente ──
    def _file_sel(self): return os.path.join(CACHE_DIR, "satelliti_scelti.txt")

    def _carica_selezione(self):
        try:
            with open(self._file_sel(), encoding="utf-8") as f:
                r = [x.strip() for x in f if x.strip()]
            if r: return r
        except Exception: pass
        return list(SAT.SAT_PREFERITI)

    def _salva_selezione(self):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(self._file_sel(), "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(self._selezionati)))
        except Exception: pass

    def _apri_selezione(self):
        nomi = sorted(self._sats.keys()) if self._sats else list(SAT.SAT_PREFERITI)
        win = ctk.CTkToplevel(self); win.title("Scegli i satelliti")
        win.geometry("380x520"); win.grab_set()
        ctk.CTkLabel(win, text="Spunta i satelliti da seguire",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 2))
        barra = ctk.CTkFrame(win, fg_color="transparent"); barra.pack(fill="x", padx=12, pady=4)
        ctk.CTkButton(barra, text="Tutti", width=70,
                      command=lambda: [v.set(True) for v in self._sel_vars.values()]).pack(side="left", padx=4)
        ctk.CTkButton(barra, text="Nessuno", width=80,
                      command=lambda: [v.set(False) for v in self._sel_vars.values()]).pack(side="left", padx=4)
        ctk.CTkButton(barra, text="Preferiti", width=90,
                      command=lambda: [self._sel_vars[n].set(n in SAT.SAT_PREFERITI) for n in self._sel_vars]).pack(side="left", padx=4)
        scroll = ctk.CTkScrollableFrame(win, width=340, height=380)
        scroll.pack(fill="both", expand=True, padx=12, pady=6)
        self._sel_vars = {}
        for nome in nomi:
            v = ctk.BooleanVar(value=(nome in self._selezionati))
            self._sel_vars[nome] = v
            ctk.CTkCheckBox(scroll, text=nome, variable=v).pack(anchor="w", pady=1)

        def ok():
            self._selezionati = {n for n, v in self._sel_vars.items() if v.get()}
            self._salva_selezione(); win.destroy(); self._aggiorna_menu(); self._calcola()
        ctk.CTkButton(win, text="OK", command=ok).pack(pady=(4, 12))

    # ── caricamento + calcolo ──
    def _carica_e_calcola(self):
        self.lbl_stato.configure(text="Scarico TLE…")
        threading.Thread(target=self._carica_tle_worker, daemon=True).start()

    def _carica_tle_worker(self):
        path, agg, msg = SAT.scarica_tle(CACHE_DIR, max_age_ore=6)
        self._sats = SAT.carica_satelliti(path) if path else {}
        self.after(0, lambda: (self._aggiorna_menu(), self._calcola(msg)))

    def _aggiorna_menu(self):
        disp = [n for n in sorted(self._sats.keys()) if n in self._selezionati] or \
               sorted(self._sats.keys())[:30]
        if not disp: disp = ["—"]
        self.menu_sat.configure(values=disp)
        if self.var_sat.get() not in disp:
            self.var_sat.set(disp[0]); self._sat_corrente = disp[0]

    def _cambia_sat(self, nome):
        self._sat_corrente = nome
        self._calcola()

    def _logga_qso(self):
        """Apre Aggiungi QSO nell'app principale col satellite selezionato,
        precompilando TX/RX/SAT_MODE dal database frequenze."""
        nome = (getattr(self, "_sat_corrente", None) or self.var_sat.get() or "").strip()
        if not nome or nome == "—":
            messagebox.showinfo("Satellite", "Seleziona prima un satellite.",
                                parent=self)
            return
        app = self.app_ref
        if app is None or not hasattr(app, "logga_qso_da_satellite"):
            messagebox.showwarning(
                "Logging non disponibile",
                "Impossibile raggiungere la finestra Aggiungi QSO.",
                parent=self)
            return
        # La finestra satellite è modale (grab_set): senza rilasciare il grab
        # la finestra Aggiungi QSO che si apre non riceverebbe i click.
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            app.logga_qso_da_satellite(nome)
        except Exception as e:
            messagebox.showerror("Errore", f"Apertura Aggiungi QSO fallita:\n{e}",
                                 parent=self)

    def _calcola(self, msg=""):
        coord = self._coord()
        if not coord:
            self.lbl_stato.configure(text="Inserisci un locatore valido (es. JN35TW)")
            return
        lat, lon = coord
        nome = self._sat_corrente or self.var_sat.get()
        solo = {nome} if nome and nome in self._sats else None
        self._passaggi = SAT.prossimi_passaggi(
            self._sats, lat, lon, elev_m=0.0,
            ore=int(self.var_ore.get()), elev_min=float(self.var_elev.get()), solo=solo)
        self._riempi_tabella()
        n = len(self._passaggi)
        self.lbl_stato.configure(text=f"{nome}: {n} passaggi · {len(self._sats)} sat in memoria · {msg}")
        self._disegna_base()
        self._aggiorna_live(riavvia=True)

    def _riempi_tabella(self):
        self.tree.delete(*self.tree.get_children())
        for p in self._passaggi:
            el = p["el_max"] or 0
            tag = "top" if el >= 45 else ("buono" if el >= 25 else "")
            az = f"{SAT.punto_cardinale(p['az_aos'])}→{SAT.punto_cardinale(p['az_los'])}"
            self.tree.insert("", "end", tags=(tag,), values=(
                p["aos"].astimezone().strftime("%d/%m %H:%M"),
                f"{p['durata_min']:.0f} min", f"{el:.0f}°", az))

    # ── posizione LIVE (ogni 5 s) ──
    def _aggiorna_live(self, riavvia=False):
        if riavvia:
            self._live_on = True
        if not self._live_on:
            return
        nome = self._sat_corrente or self.var_sat.get()
        sat = self._sats.get(nome)
        coord = self._coord()
        if sat and coord:
            now = datetime.now(timezone.utc)
            sp = SAT.subpoint(sat, now)
            if sp:
                lat, lon, alt = sp
                raggio = SAT.raggio_footprint_km(alt)
                # footprint
                for ln in self._foot_lines:
                    try: ln.remove()
                    except Exception: pass
                self._foot_lines = []
                for a, b in zip(*_spezza(SAT.cerchio_footprint(lat, lon, raggio, 120))):
                    ln, = self.ax.plot(a, b, color=FOOT, lw=1.4, alpha=0.5, zorder=4)
                    self._foot_lines.append(ln)
                self._sat_dot.set_data([lon], [lat])
                self._sat_txt.set_text(nome)
                self._sat_txt.xy = (lon, lat)
                # dati live osservatore->sat
                pos = SAT.posizione_attuale(sat, coord[0], coord[1])
                if pos:
                    el, az, dist = pos
                    sopra = "SI ✓" if el > 0 else "no"
                    self.lbl_live.configure(
                        text=(f"Posizione live ({now.astimezone().strftime('%H:%M:%S')})\n"
                              f"Sub-point: lat {lat:.1f}°  lon {lon:.1f}°   alt {alt:.0f} km\n"
                              f"Da te:  El {el:.1f}°   Az {az:.0f}° {SAT.punto_cardinale(az)}   "
                              f"Dist {dist:.0f} km\n"
                              f"Visibile ora: {sopra}   ·   Footprint {raggio:.0f} km"))
                self.lbl_map.configure(text=f"{nome} — posizione in tempo reale")
                self.canvas.draw_idle()
        self.after(INTERVALLO_LIVE_MS, self._aggiorna_live)

    def _chiudi(self):
        self._live_on = False
        self.destroy()
