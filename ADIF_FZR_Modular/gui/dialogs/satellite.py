# -*- coding: utf-8 -*-
"""
Cruscotto satellitare per ADIF FZR (finestra unica).
Sinistra: mappa con posizione IN TEMPO REALE del satellite selezionato
          (footprint, osservatore, traccia del prossimo passaggio).
Destra:   selettore satellite, dati live (el/az/distanza), tabella passaggi.
Motore: radio/satellite.py (skyfield).  Mappa: coste incorporate + matplotlib.
"""

import math
import os
import sys
import threading
import time
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
    import matplotlib.patheffects as _pe
    _BORDO = [_pe.withStroke(linewidth=3, foreground="#0d1522")]  # testo leggibile sulla mappa
except Exception as _e:
    _MPL_OK = False
    _MPL_ERR = repr(_e)

from config import locator_to_latlon, estrai_locator_da_testo, T
import config as _config_mod


def _tl(it, en):
    try:
        return en if getattr(_config_mod, "LINGUA", "IT") == "EN" else it
    except Exception:
        return it

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
DXCOL = "#4fc3f7"

# ── Sfondo NASA Blue Marble (pubblico dominio), equirettangolare -180..180 ──
_MARBLE_NOME = "world_map.jpg"
_MARBLE_NOMI = ("worldmap.jpg", "world_map.jpg", "WorldMap.jpg")
_MARBLE_IMG = None          # caricata una volta sola, poi riusata
_MARBLE_TENTATA = False


def _carica_marble():
    """Cerca world_map.jpg accanto al programma (sorgente o eseguibile
    PyInstaller) e la carica. Ritorna l'array immagine o None."""
    global _MARBLE_IMG, _MARBLE_TENTATA
    if _MARBLE_TENTATA:
        return _MARBLE_IMG
    _MARBLE_TENTATA = True
    basi = []
    if getattr(sys, "frozen", False):
        basi += [getattr(sys, "_MEIPASS", ""), os.path.dirname(sys.executable)]
    qui = os.path.dirname(os.path.abspath(__file__))           # gui/dialogs
    pkg = os.path.dirname(os.path.dirname(qui))                # ADIF_FZR_Modular
    basi += [qui, os.path.dirname(qui), pkg, os.path.dirname(pkg), os.getcwd()]
    subs = ("", "assets", "img", "images", "maps", "data")
    # 1) trova il file (vari nomi possibili: worldmap.jpg / world_map.jpg)
    trovato = None
    for base in basi:
        if not base:
            continue
        for sub in subs:
            for nome in _MARBLE_NOMI:
                percorso = os.path.join(base, sub, nome)
                if os.path.exists(percorso):
                    trovato = percorso
                    break
            if trovato:
                break
        if trovato:
            break
    if not trovato:
        _LOG("mappa NASA non trovata, uso le sole coste")
        return None
    # 2) lettura robusta: prima matplotlib, poi fallback Pillow (JPEG)
    try:
        import matplotlib.image as mpimg
        _MARBLE_IMG = mpimg.imread(trovato)
        _LOG("mappa NASA caricata: " + trovato)
        return _MARBLE_IMG
    except Exception as e:
        _LOG("imread fallita (%r), provo Pillow" % e)
    try:
        from PIL import Image
        import numpy as _np
        _MARBLE_IMG = _np.asarray(Image.open(trovato).convert("RGB"))
        _LOG("mappa NASA caricata via Pillow: " + trovato)
        return _MARBLE_IMG
    except Exception as e:
        _LOG("mappa NASA trovata ma non leggibile: %r" % e)
        return None



def _con_nan(punti):
    """(lat, lon) -> xs, ys in un'unica linea, spezzata con NaN dove attraversa
    il bordo ±180°. Una sola Line2D invece di tante: si sposta con set_data."""
    xs, ys = [], []
    for sx, sy in zip(*_spezza(punti)):
        if xs:
            xs.append(float("nan")); ys.append(float("nan"))
        xs += sx; ys += sy
    return xs, ys


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
        self.geometry("1380x760")
        self.resizable(True, True)
        # NON modale (niente grab_set: bloccava DX Cluster, menu e barra), ma
        # figlia della finestra principale come DX Cluster e Award: resta sopra
        # il logbook senza galleggiare sopra gli altri programmi.
        try:
            self.transient(parent)
        except Exception:
            pass
        self.lift()
        self.after(60, self._ripristina_pulsanti_titolo)
        # CTkToplevel su Windows si ridisegna dopo la creazione: porta davanti
        # di nuovo quando la finestra e' davvero pronta
        self.after(250, self._in_primo_piano)

        self._sats = {}
        self._passaggi = []
        self._selezionati = set(self._carica_selezione())
        self._sat_corrente = None
        self._busy = False
        self._live_on = False
        self._live_after = None
        self._tempi = {}
        self._foot_lines = []
        self._track_line = None
        self._orbit_lines = []
        self._polar_artists = []
        self._prossimo = None          # prossimo passaggio (dict) per lo sky plot
        self._prossimo_track = []      # sua traccia az/el
        self._anim_idx = None

        if not _MPL_OK:
            ctk.CTkLabel(self, text=_tl("Errore matplotlib (finestra mappa)", "Matplotlib error (map window)"),
                         font=ctk.CTkFont(size=15, weight="bold"),
                         text_color="#ff6b6b").pack(pady=(16, 6))
            box = ctk.CTkTextbox(self, width=760, height=180)
            box.pack(padx=16, pady=8)
            box.insert("1.0", "matplotlib non si e' caricato:\n\n" + _MPL_ERR +
                       "\n\nQuesto e' il vero motivo per cui la finestra non si apre.")
            ctk.CTkButton(self, text=_tl("Chiudi", "Close"), command=self.destroy).pack(pady=8)
            return

        if not getattr(SAT, "SKYFIELD_OK", True):
            ctk.CTkLabel(self, text=_tl("Passaggi satelliti", "Satellite passes"),
                         font=ctk.CTkFont(size=16, weight="bold")).pack(pady=12)
            ctk.CTkLabel(self,
                text=("La libreria 'skyfield' non e' installata.\n"
                      "Installala con:  pip install skyfield\npoi riapri."),
                text_color="#ff6b6b", justify="center").pack(pady=30)
            ctk.CTkButton(self, text=_tl("Chiudi", "Close"), command=self.destroy).pack()
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
        self.fig = Figure(figsize=(9, 5), dpi=100, facecolor=BG)
        _LOG("5: Figure creata")
        # mappa a sinistra, sky plot polare a destra
        gs = self.fig.add_gridspec(1, 2, width_ratios=[3.0, 1.15], wspace=0.08)
        self.ax = self.fig.add_subplot(gs[0, 0])
        self.axp = self.fig.add_subplot(gs[0, 1], projection="polar")
        self.var_orbita = ctk.BooleanVar(value=True)
        self.var_marble = ctk.BooleanVar(value=_carica_marble() is not None)
        self._disegna_base()
        self._disegna_polare_base()
        _LOG("6: prima di FigureCanvasTkAgg")
        self.canvas = FigureCanvasTkAgg(self.fig, master=sx)
        # Blitting: lo sfondo (coste, griglia, sky plot vuoto) si
        # disegna una volta e si tiene in memoria; ogni aggiornamento ridisegna
        # solo gli elementi che si muovono.
        self._bg = None
        self.canvas.mpl_connect("draw_event", self._su_draw)
        _LOG("7: canvas creato OK")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.lbl_map = ctk.CTkLabel(sx, text=_tl("Seleziona un satellite per vederne la posizione", "Select a satellite to see its position"),
                                    text_color=MUT)
        self.lbl_map.pack(pady=(4, 0))

        # ── opzioni mappa ──
        optbar = ctk.CTkFrame(sx, fg_color="transparent")
        optbar.pack(fill="x", pady=(2, 0))
        self.chk_marble = ctk.CTkCheckBox(optbar, text=_tl("Mappa NASA", "NASA map"), variable=self.var_marble,
                                          command=self._cambia_sfondo)
        self.chk_marble.pack(side="left", padx=(6, 12))
        if _carica_marble() is None:
            self.chk_marble.configure(state="disabled", text=_tl("Mappa NASA (worldmap.jpg mancante)", "NASA map (worldmap.jpg missing)"))
        ctk.CTkCheckBox(optbar, text=_tl("Traccia orbita", "Orbit track"), variable=self.var_orbita,
                        command=self._ridisegna_mappa).pack(side="left", padx=(0, 12))

        # ── barra REPLAY passaggio (footprint animato) ──
        animbar = ctk.CTkFrame(sx, fg_color="transparent")
        animbar.pack(fill="x", pady=(2, 0))
        self.btn_anim = ctk.CTkButton(animbar, text=_tl("⏸ Pausa", "⏸ Pause"), width=96, state="disabled",
                                      command=self._anim_play_pause)
        self.btn_anim.pack(side="left", padx=(4, 6))
        self.sld_anim = ctk.CTkSlider(animbar, from_=0, to=1, number_of_steps=100,
                                      command=self._anim_scrub)
        self.sld_anim.set(0)
        self.sld_anim.pack(side="left", fill="x", expand=True, padx=6)
        self.sld_anim.configure(state="disabled")
        ctk.CTkButton(animbar, text="🔴 Live", width=72, fg_color="#7a2e2e",
                      hover_color="#96271b", command=self._torna_live).pack(side="left", padx=(6, 4))
        self.lbl_anim = ctk.CTkLabel(sx, text=_tl("Clicca un passaggio nella tabella per vedere il footprint muoversi.", "Click a pass in the table to watch the footprint move."),
                                     text_color=MUT, justify="left", anchor="w")
        self.lbl_anim.pack(fill="x", padx=6, pady=(2, 0))

        # stato animazione
        self._anim_track = []
        self._anim_frame = 0
        self._anim_playing = False
        self._anim_after = None
        self._anim_artists = []
        self._anim_track_lines = []
        self._anim_pass = None
        self._anim_mutual_per_frame = []
        self._anim_riepilogo = ""
        self._sld_sync = False

        # ── DESTRA: controlli + dati + passaggi ──
        dx = ctk.CTkFrame(self)
        dx.grid(row=0, column=1, sticky="nsew", padx=(6, 10), pady=10)

        top = ctk.CTkFrame(dx, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(top, text=_tl("Locatore:", "Locator:")).grid(row=0, column=0, padx=(0, 4), sticky="e")
        self.var_loc = ctk.StringVar(value=self._locatore_operatore())
        ctk.CTkEntry(top, textvariable=self.var_loc, width=100).grid(row=0, column=1)
        ctk.CTkLabel(top, text=_tl("Ore:", "Hours:")).grid(row=0, column=2, padx=(10, 4), sticky="e")
        self.var_ore = ctk.StringVar(value="24")
        ctk.CTkOptionMenu(top, values=["6", "12", "24", "48"], variable=self.var_ore,
                          width=64).grid(row=0, column=3)
        ctk.CTkLabel(top, text=_tl("El.min:", "Min El:")).grid(row=0, column=4, padx=(10, 4), sticky="e")
        self.var_elev = ctk.StringVar(value="10")
        ctk.CTkOptionMenu(top, values=["0", "5", "10", "20"], variable=self.var_elev,
                          width=64).grid(row=0, column=5)
        ctk.CTkLabel(top, text=_tl("Stazione DX:", "DX station:")).grid(row=1, column=0, padx=(0, 4),
                                                    pady=(6, 0), sticky="e")
        self.var_dx = ctk.StringVar(value="")
        ent_dx = ctk.CTkEntry(top, textvariable=self.var_dx, width=100,
                              placeholder_text="es. FN20")
        ent_dx.grid(row=1, column=1, pady=(6, 0))
        ent_dx.bind("<Return>", lambda _e: self._dx_cambiato())
        ent_dx.bind("<FocusOut>", lambda _e: self._dx_cambiato())
        ctk.CTkLabel(top, text=_tl("locatore del corrispondente: posizione e Az/El da lui", "correspondent's locator: position and Az/El from there"),
                     text_color=MUT, font=ctk.CTkFont(size=10)
                     ).grid(row=1, column=2, columnspan=4, padx=(10, 0), pady=(6, 0), sticky="w")
        self._dx_ultimo = ""

        # ── SELEZIONE SATELLITE ─────────────────────────────────────
        # Due righe separate evitano che i pulsanti escano dalla finestra
        # quando la colonna destra è stretta.
        selrow = ctk.CTkFrame(dx, fg_color="transparent")
        selrow.pack(fill="x", padx=8, pady=(4, 2))

        ctk.CTkLabel(selrow, text="Satellite:").pack(side="left")
        self.var_sat = ctk.StringVar(value="")
        self.menu_sat = ctk.CTkOptionMenu(
            selrow, values=["—"], variable=self.var_sat,
            width=190, command=self._cambia_sat
        )
        self.menu_sat.pack(side="left", padx=6)

        ctk.CTkButton(
            selrow, text=_tl("Scegli…", "Choose…"), width=90,
            command=self._apri_selezione
        ).pack(side="left")

        # Seconda riga: funzioni operative.
        btnrow = ctk.CTkFrame(dx, fg_color="transparent")
        btnrow.pack(fill="x", padx=8, pady=(2, 6))

        ctk.CTkButton(
            btnrow, text=_tl("🔄 Aggiorna TLE", "🔄 Update TLE"), width=125,
            fg_color="#2B6CB0", hover_color="#2C5282",
            command=self._aggiorna_tle
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btnrow, text=_tl("➕ TLE manuale", "➕ Manual TLE"), width=125,
            fg_color="#4A5568", hover_color="#3B4453",
            command=self._dialog_tle_manuale
        ).pack(side="left", padx=(0, 6))

        # Ponte al logging: apre Aggiungi QSO col satellite selezionato,
        # precompilando TX/RX/SAT_MODE dal database frequenze.
        try:
            _txt_log = T("aq_logga_sat")
        except Exception:
            _txt_log = "➕ Logga QSO"

        ctk.CTkButton(
            btnrow, text=_txt_log, width=140,
            fg_color="#276749", hover_color="#2F855A",
            command=self._logga_qso
        ).pack(side="right")

        # pannello dati live
        self.box_live = ctk.CTkFrame(dx)
        self.box_live.pack(fill="x", padx=8, pady=6)
        self.lbl_live = ctk.CTkLabel(self.box_live, text=_tl("Posizione live: —", "Live position: —"),
                                     text_color=TXT, justify="left", anchor="w",
                                     font=ctk.CTkFont(size=13))
        self.lbl_live.pack(fill="x", padx=10, pady=8)

        # ── PUNTAMENTO ANTENNA (riquadro grande) ──────────────────
        self.box_punta = ctk.CTkFrame(dx, fg_color="#12233d", border_width=2,
                                      border_color="#2a3c5a")
        self.box_punta.pack(fill="x", padx=8, pady=(0, 6))
        ctk.CTkLabel(self.box_punta, text="PUNTAMENTO ANTENNA", text_color=MUT,
                     font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(8, 0))
        self.lbl_punta = ctk.CTkLabel(self.box_punta, text="—",
                                      text_color=TXT,
                                      font=ctk.CTkFont(size=30, weight="bold"))
        self.lbl_punta.pack(pady=(2, 0))
        self.lbl_punta_sub = ctk.CTkLabel(self.box_punta, text="",
                                          text_color=MUT, font=ctk.CTkFont(size=12))
        self.lbl_punta_sub.pack(pady=(0, 10))

        # tabella passaggi
        cont = ctk.CTkFrame(dx)
        cont.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        cols = ("inizio", "durata", "elmax", "az")
        self.tree = ttk.Treeview(cont, columns=cols, show="headings",
                                 height=12, style="Sat.Treeview")
        for c, (t, w) in {"inizio": (_tl("Inizio (AOS)", "Start (AOS)"), 130), "durata": (_tl("Durata", "Duration"), 70),
                          "elmax": (_tl("El. max", "Max El."), 70), "az": ("Antenna", 120)}.items():
            self.tree.heading(c, text=t); self.tree.column(c, width=w, anchor="center")
        vsb = ttk.Scrollbar(cont, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("top", background="#1e3a1e", foreground="#c8f7c8")
        self.tree.tag_configure("buono", background="#233046", foreground="#e9eef7")
        self.tree.bind("<<TreeviewSelect>>", self._passaggio_selezionato)

        self.lbl_stato = ctk.CTkLabel(dx, text="", text_color=MUT, anchor="w")
        self.lbl_stato.pack(fill="x", padx=10, pady=(0, 6))

        _LOG("8: fine init, avvio caricamento")
        self.protocol("WM_DELETE_WINDOW", self._chiudi)
        self.after(200, self._carica_e_calcola)

    def _in_primo_piano(self):
        try:
            self.deiconify(); self.lift(); self.focus_force()
        except Exception:
            pass

    def _ripristina_pulsanti_titolo(self):
        """Su Windows transient() toglie Riduci/Ingrandisci: li rimette
        (stesso metodo della finestra Award). Senza effetti altrove."""
        try:
            import ctypes
            GWL_STYLE = -16
            WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x00020000, 0x00010000
            SWP_FLAGS = 0x0002 | 0x0001 | 0x0004 | 0x0020  # NOMOVE|NOSIZE|NOZORDER|FRAMECHANGED
            u = ctypes.windll.user32
            hwnd = u.GetParent(self.winfo_id())
            stile = u.GetWindowLongW(hwnd, GWL_STYLE)
            u.SetWindowLongW(hwnd, GWL_STYLE, stile | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
            u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FLAGS)
        except Exception:
            pass

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
        self._bg = None
        ax = self.ax; ax.clear(); ax.set_facecolor(BG)
        v = getattr(self, "var_marble", None)
        if v is not None and v.get() and _carica_marble() is not None:
            # disegnata solo nei ridisegni completi: nel live e nel replay
            # resta nello sfondo in memoria
            ax.imshow(_carica_marble(), extent=(-180, 180, -90, 90), origin="upper",
                      aspect="auto", interpolation="nearest", zorder=0)
            griglia = dict(color="#ffffff", lw=0.3, alpha=0.25)
        else:
            for l in COSTE:
                ax.plot([p[0] for p in l], [p[1] for p in l], color=COAST, lw=0.6, zorder=1)
            griglia = dict(color=GRID, lw=0.4)
        ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
        ax.set_xticks(range(-180, 181, 60)); ax.set_yticks(range(-90, 91, 30))
        ax.grid(True, **griglia); ax.tick_params(colors=MUT, labelsize=7)
        for s in ax.spines.values(): s.set_color(GRID)
        if self._coord():
            la, lo = self._coord()
            ax.plot(lo, la, marker="*", color=OSS, markersize=15, zorder=6)
        dx = self._coord_dx()
        if dx:
            ax.plot(dx[1], dx[0], marker="D", color=DXCOL, markersize=8, zorder=6)
            ax.annotate(self._loc_dx(), (dx[1], dx[0]), textcoords="offset points",
                        xytext=(7, -12), color=DXCOL, fontsize=8, weight="bold", zorder=6,
                        path_effects=_BORDO)
        # elementi mobili: creati una volta, poi solo spostati (set_data)
        kw = dict(animated=True)
        (self._orb_past,) = ax.plot([], [], color=TRACK, lw=1.0, ls="-", alpha=0.35,
                                    zorder=3, **kw)
        (self._orb_fut,) = ax.plot([], [], color=TRACK, lw=1.0, ls="--", alpha=0.8,
                                   zorder=3, **kw)
        (self._foot_line,) = ax.plot([], [], color=FOOT, lw=1.6, alpha=0.9, zorder=4, **kw)
        (self._sat_dot,) = ax.plot([], [], marker="o", color=SATCOL, markersize=11,
                                   zorder=7, **kw)
        self._sat_txt = ax.annotate("", (0, 0), textcoords="offset points",
                                    xytext=(10, 8), color=SATCOL, fontsize=9,
                                    weight="bold", zorder=8, path_effects=_BORDO, **kw)
        self.fig.subplots_adjust(left=0.04, right=0.955, top=0.95, bottom=0.07)

    # ── traccia dell'orbita attorno a un istante ──
    def _disegna_orbita(self, sat, quando):
        if not self.var_orbita.get() or sat is None or not hasattr(SAT, "traccia_orbita"):
            self._orb_past.set_data([], []); self._orb_fut.set_data([], [])
            return
        passato, futuro = SAT.traccia_orbita(sat, quando)
        self._orb_past.set_data(*(_con_nan(passato) if len(passato) > 1 else ([], [])))
        self._orb_fut.set_data(*(_con_nan(futuro) if len(futuro) > 1 else ([], [])))

    def _disegna_footprint(self, lat, lon, raggio_km):
        cer = SAT.cerchio_footprint(lat, lon, raggio_km, 120)
        self._foot_line.set_data(*(_con_nan(cer) if cer else ([], [])))

    def _cambia_sfondo(self):
        """Casella Mappa NASA: ridisegna lo sfondo mantenendo live o replay."""
        if self._anim_track and self._anim_idx is not None:
            frame = self._anim_frame
            self._avvia_animazione(self._anim_idx)
            self._anim_frame = frame
        else:
            self._disegna_base()
            self._aggiorna_live(riavvia=True)

    def _ridisegna_mappa(self):
        """Chiamata dalla casella Traccia orbita."""
        if not self._anim_track:
            if not self.var_orbita.get():
                self._disegna_orbita(None, None)
            else:
                nome = self._sat_corrente or self.var_sat.get()
                self._disegna_orbita(self._sats.get(nome), datetime.now(timezone.utc))
        self._aggiorna_canvas()

    # ── sky plot polare (Az/El dal tuo QTH) ──
    # ── blitting ──
    def _dinamici(self):
        return [self._orb_past, self._orb_fut,
                self._foot_line, self._sat_dot, self._sat_txt,
                self._p_track, self._p_ini, self._p_fin, self._p_dot, self._p_txt]

    def _su_draw(self, _evt=None):
        """Dopo ogni ridisegno completo (anche ridimensionando la finestra):
        salva lo sfondo e ci disegna sopra gli elementi mobili."""
        try:
            self._bg = self.canvas.copy_from_bbox(self.fig.bbox)
            for a in self._dinamici():
                self.fig.draw_artist(a)
            self.canvas.blit(self.fig.bbox)
        except Exception:
            self._bg = None

    def _aggiorna_canvas(self):
        t0 = time.perf_counter()
        if self._bg is None:
            self.canvas.draw()            # ridisegno completo -> _su_draw
            _LOG("[tempi] ridisegno completo %.0f ms" % ((time.perf_counter() - t0) * 1000))
            return
        try:
            self.canvas.restore_region(self._bg)
            for a in self._dinamici():
                self.fig.draw_artist(a)
            self.canvas.blit(self.fig.bbox)
        except Exception:
            self._bg = None
            self.canvas.draw()

    def _misura(self, chiave, t0, ogni):
        """Accumula i tempi e ogni 'ogni' campioni scrive la media nel log
        (~/adif_fzr_sat_log.txt), per capire cosa pesa sul PC reale."""
        ms = (time.perf_counter() - t0) * 1000
        acc = self._tempi.setdefault(chiave, [0.0, 0, 0.0])
        acc[0] += ms; acc[1] += 1; acc[2] = max(acc[2], ms)
        if acc[1] >= ogni:
            _LOG("[tempi] %s: media %.0f ms, max %.0f ms su %d"
                 % (chiave, acc[0] / acc[1], acc[2], acc[1]))
            self._tempi[chiave] = [0.0, 0, 0.0]

    def _disegna_polare_base(self):
        self._bg = None
        ax = self.axp
        ax.clear()
        ax.set_facecolor(BG)
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_rlim(0, 90)
        ax.set_rticks([30, 60, 90])
        ax.set_yticklabels(["60°", "30°", "0°"], color=MUT, fontsize=7)
        ax.set_rlabel_position(135)
        ax.set_xticks([math.radians(a) for a in range(0, 360, 45)])
        ax.set_xticklabels(["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
                           color=MUT, fontsize=8)
        ax.grid(True, color=GRID, lw=0.6)
        ax.spines["polar"].set_color(COAST)
        ax.set_title("Cielo dal tuo QTH", color=MUT, fontsize=9, pad=10)
        kw = dict(animated=True)
        (self._p_track,) = ax.plot([], [], color=TRACK, lw=1.4, alpha=0.8, zorder=3, **kw)
        (self._p_ini,) = ax.plot([], [], marker="o", color=OSS, markersize=5, zorder=4, **kw)
        (self._p_fin,) = ax.plot([], [], marker="s", color=MUT, markersize=5, zorder=4, **kw)
        (self._p_dot,) = ax.plot([], [], marker="o", color=SATCOL, markersize=10,
                                 zorder=5, **kw)
        self._p_txt = ax.text(0.5, -0.12, "", transform=ax.transAxes, ha="center",
                              va="top", color=TXT, fontsize=8, **kw)
        self._p_track_id = None

    def _polare_mostra(self, track, punto=None, etichetta="", futuro=False):
        """Sky plot: curva di un passaggio (lista di dict con az/el) ed
        eventualmente la posizione corrente (az, el). Sposta gli elementi
        esistenti; la curva si ricalcola solo se cambia il passaggio."""
        chiave = (id(track), len(track or []), futuro)
        if chiave != self._p_track_id:
            self._p_track_id = chiave
            pts = [(c["az"], c["el"]) for c in (track or []) if "az" in c and c["el"] >= 0]
            if len(pts) >= 2:
                th = [math.radians(a) for a, _ in pts]
                r = [90 - e for _, e in pts]
                self._p_track.set_data(th, r)
                self._p_track.set_linestyle("--" if futuro else "-")
                self._p_ini.set_data([th[0]], [r[0]])
                self._p_fin.set_data([th[-1]], [r[-1]])
            else:
                for a in (self._p_track, self._p_ini, self._p_fin):
                    a.set_data([], [])
        if punto is not None and punto[1] >= 0:
            self._p_dot.set_data([math.radians(punto[0])], [90 - punto[1]])
        else:
            self._p_dot.set_data([], [])
        self._p_txt.set_text(etichetta or "")

    # ── stazione DX ──
    def _loc_dx(self):
        var = getattr(self, "var_dx", None)
        return (var.get() or "").strip().upper() if var is not None else ""

    def _coord_dx(self):
        loc = self._loc_dx()
        if not loc:
            return None
        try: return locator_to_latlon(loc)
        except Exception: return None

    def _dx_cambiato(self):
        loc = self._loc_dx()
        if loc == self._dx_ultimo:
            return
        self._dx_ultimo = loc
        if loc and not self._coord_dx():
            self.lbl_stato.configure(text=f"Locatore DX non valido: {loc}")
            return
        if self._anim_track and self._anim_idx is not None:
            self._avvia_animazione(self._anim_idx)   # rifà anche l'analisi mutua
        else:
            self._disegna_base()
            self._aggiorna_live(riavvia=True)

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
        ctk.CTkLabel(win, text=_tl("Spunta i satelliti da seguire", "Check the satellites to track"),
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 2))
        barra = ctk.CTkFrame(win, fg_color="transparent"); barra.pack(fill="x", padx=12, pady=4)
        ctk.CTkButton(barra, text=_tl("Tutti", "All"), width=70,
                      command=lambda: [v.set(True) for v in self._sel_vars.values()]).pack(side="left", padx=4)
        ctk.CTkButton(barra, text=_tl("Nessuno", "None"), width=80,
                      command=lambda: [v.set(False) for v in self._sel_vars.values()]).pack(side="left", padx=4)
        ctk.CTkButton(barra, text=_tl("Preferiti", "Favorites"), width=90,
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
    def _carica_e_calcola(self, forza=False):
        self.lbl_stato.configure(text=_tl("Scarico TLE…", "Downloading TLE…") if forza else _tl("Carico TLE…", "Loading TLE…"))
        threading.Thread(target=lambda: self._carica_tle_worker(forza), daemon=True).start()

    def _carica_tle_worker(self, forza=False):
        path, agg, msg = SAT.scarica_tle(CACHE_DIR, max_age_ore=6, forza=forza)
        # Fonde i TLE di Celestrak con quelli inseriti a mano (persistenti).
        self._sats = SAT.carica_satelliti_e_manuali(CACHE_DIR, path)
        eta = SAT.eta_cache_ore(CACHE_DIR)
        if eta is not None:
            msg = f"{msg} · TLE di {eta:.0f}h fa"
        self.after(0, lambda: (self._aggiorna_menu(), self._calcola(msg)))

    def _aggiorna_tle(self):
        """Forza il download dei TLE da Celestrak, ignorando la cache."""
        self._carica_e_calcola(forza=True)

    def _dialog_tle_manuale(self):
        """Finestra per incollare un TLE a mano (satelliti non nel gruppo
        amateur di Celestrak). Viene salvato in modo persistente e unito."""
        win = ctk.CTkToplevel(self)
        win.title("Inserisci TLE manuale")
        win.geometry("540x330")
        win.resizable(False, False)
        win.after(60, lambda: (win.lift(), win.focus_force()))
        ctk.CTkLabel(win, text=_tl("Incolla il TLE completo (3 righe)", "Paste the full TLE (3 lines)"),
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(14, 2))
        ctk.CTkLabel(win, justify="left", text_color=MUT, font=ctk.CTkFont(size=10),
                     text=_tl("Riga 1: nome del satellite\nRighe 2-3: le due righe di elementi (iniziano con '1 ' e '2 ')", "Line 1: satellite name\nLines 2-3: the two element lines (starting with '1 ' and '2 ')")).pack()
        txt = ctk.CTkTextbox(win, width=500, height=130,
                             font=ctk.CTkFont(family="Consolas", size=11))
        txt.pack(padx=18, pady=10)
        txt.insert("1.0", "ISS (ZARYA)\n1 25544U ...\n2 25544 ...")
        lbl = ctk.CTkLabel(win, text="", text_color=MUT)
        lbl.pack()

        def salva():
            righe = [r.strip() for r in txt.get("1.0", "end").splitlines() if r.strip()]
            if len(righe) < 3:
                lbl.configure(text=_tl("Servono 3 righe: nome, riga 1, riga 2.", "3 lines needed: name, line 1, line 2."),
                              text_color="#e0a44a")
                return
            nome, l1, l2 = righe[0], righe[1], righe[2]
            ok, msg = SAT.salva_tle_manuale(CACHE_DIR, nome, l1, l2)
            lbl.configure(text=msg, text_color=("#5fd08f" if ok else "#e0a44a"))
            if ok:
                try:
                    self._selezionati.add(nome)
                    self._salva_selezione()
                except Exception:
                    pass
                self.var_sat.set(nome)
                self._sat_corrente = nome
                self._carica_e_calcola()
                win.after(1000, win.destroy)

        ctk.CTkButton(win, text=_tl("💾 Salva TLE", "💾 Save TLE"), command=salva,
                      fg_color="#276749", hover_color="#2F855A").pack(pady=10)

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
        try:
            app.logga_qso_da_satellite(nome)
        except Exception as e:
            messagebox.showerror("Errore", f"Apertura Aggiungi QSO fallita:\n{e}",
                                 parent=self)

    def _calcola(self, msg=""):
        self._stop_anim_soft()
        coord = self._coord()
        if not coord:
            self.lbl_stato.configure(text=_tl("Inserisci un locatore valido (es. JN35TW)", "Enter a valid locator (e.g. JN35TW)"))
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
        self._prepara_prossimo()
        self._disegna_base()
        self._aggiorna_live(riavvia=True)

    def _prepara_prossimo(self):
        """Trova il passaggio in corso o il prossimo e ne calcola la curva Az/El
        per lo sky plot (una volta sola, non a ogni aggiornamento live)."""
        self._prossimo = None
        self._prossimo_track = []
        coord = self._coord()
        now = datetime.now(timezone.utc)
        for p in self._passaggi:
            if p.get("los") and p["los"] > now:
                self._prossimo = p
                break
        if not self._prossimo or not coord:
            return
        sat = self._sats.get(self._prossimo.get("sat"))
        if sat is None:
            return
        try:
            self._prossimo_track = SAT.traccia_passaggio(
                sat, self._prossimo["aos"], self._prossimo["los"], passi=60,
                oss_lat=coord[0], oss_lon=coord[1])
        except TypeError:
            # radio/satellite.py vecchio, senza az/el: sky plot senza curva
            self._prossimo_track = []

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
        # Un solo ciclo attivo: prima si annullava nulla e ogni cambio di
        # satellite / ricalcolo / "Live" avviava un ciclo in piu' in parallelo.
        if self._live_after is not None:
            try: self.after_cancel(self._live_after)
            except Exception: pass
            self._live_after = None
        if riavvia:
            self._live_on = True
        if not self._live_on:
            return
        t0 = time.perf_counter()
        nome = self._sat_corrente or self.var_sat.get()
        sat = self._sats.get(nome)
        coord = self._coord()
        if sat and coord:
            now = datetime.now(timezone.utc)
            sp = SAT.subpoint(sat, now)
            if sp:
                lat, lon, alt = sp
                raggio = SAT.raggio_footprint_km(alt)
                # traccia orbita
                self._disegna_orbita(sat, now)
                # footprint
                self._disegna_footprint(lat, lon, raggio)
                self._sat_dot.set_data([lon], [lat])
                self._sat_txt.set_text(nome)
                self._sat_txt.xy = (lon, lat)
                # dati live osservatore->sat
                pos = SAT.posizione_attuale(sat, coord[0], coord[1])
                if pos:
                    el, az, dist = pos
                    sopra = "SI ✓" if el > 0 else "no"
                    riga_dx = ""
                    dx = self._coord_dx()
                    if dx and hasattr(SAT, "azel_da"):
                        pdx = SAT.azel_da(sat, dx[0], dx[1], now)
                        if pdx:
                            eld, azd, _ = pdx
                            vis = "visibile" if eld > 0 else "sotto l'orizzonte"
                            mut = "   ·   MUTUO ORA ✓" if (eld > 0 and el > 0) else ""
                            riga_dx = (f"\nDa {self._loc_dx()}:  El {eld:.1f}°   "
                                       f"Az {azd:.0f}° {SAT.punto_cardinale(azd)}   ({vis}){mut}")
                    self.lbl_live.configure(
                        text=(f"Posizione live ({now.astimezone().strftime('%H:%M:%S')})\n"
                              f"Sub-point: lat {lat:.1f}°  lon {lon:.1f}°   alt {alt:.0f} km\n"
                              f"Da te:  El {el:.1f}°   Az {az:.0f}° {SAT.punto_cardinale(az)}   "
                              f"Dist {dist:.0f} km\n"
                              f"Visibile ora: {sopra}   ·   Footprint {raggio:.0f} km"
                              f"{riga_dx}"))
                    self._aggiorna_puntamento(el, az)
                    self._aggiorna_polare_live(now, el, az)
                self.lbl_map.configure(text=f"{nome} — posizione in tempo reale")
                self._aggiorna_canvas()
        self._misura("aggiornamento live", t0, 12)
        self._live_after = self.after(INTERVALLO_LIVE_MS, self._aggiorna_live)

    def _aggiorna_polare_live(self, now, el, az):
        """Sky plot in tempo reale: passaggio in corso con il satellite,
        oppure la curva tratteggiata del prossimo passaggio."""
        p = self._prossimo
        if p and p.get("los") and p["los"] <= now:
            self._prepara_prossimo()           # passaggio finito: passa al successivo
            p = self._prossimo
        if p and p["aos"] <= now <= p["los"]:
            self._polare_mostra(self._prossimo_track, (az, el),
                                f"in corso · LOS {p['los'].astimezone():%H:%M}")
        elif p:
            mins = (p["aos"] - now).total_seconds() / 60.0
            self._polare_mostra(self._prossimo_track, None,
                                f"prossimo {p['aos'].astimezone():%H:%M} "
                                f"(tra {mins:.0f} min) · El max {p.get('el_max') or 0:.0f}°",
                                futuro=True)
        else:
            self._polare_mostra([], None, "nessun passaggio in vista")

    def _aggiorna_puntamento(self, el, az):
        """Aggiorna il riquadro grande 'PUNTAMENTO ANTENNA':
        - satellite visibile (El>0): Az/El live in verde ('punta qui');
        - sotto l'orizzonte: Az del prossimo AOS in ambra, con ora e
          minuti al sorgere ('pre-punta')."""
        try:
            if el > 0:
                self.lbl_punta.configure(
                    text=f"Az {az:.0f}° {SAT.punto_cardinale(az)}   ·   El {el:.0f}°",
                    text_color="#5fd08f")
                self.box_punta.configure(border_color="#2f9e5e", fg_color="#12281c")
                self.lbl_punta_sub.configure(
                    text="🟢 VISIBILE ORA — punta l'antenna qui", text_color="#5fd08f")
                return
            # sotto l'orizzonte: cerca il prossimo passaggio
            now = datetime.now(timezone.utc)
            prossimo = None
            for p in self._passaggi:
                if p.get("aos") and p["aos"] > now:
                    prossimo = p
                    break
            if prossimo:
                azp = prossimo["az_aos"]
                dt_min = (prossimo["aos"] - now).total_seconds() / 60.0
                ora_loc = prossimo["aos"].astimezone().strftime("%H:%M")
                self.lbl_punta.configure(
                    text=f"Az {azp:.0f}° {SAT.punto_cardinale(azp)}",
                    text_color="#e0a44a")
                self.box_punta.configure(border_color="#5a4a2a", fg_color="#241d10")
                self.lbl_punta_sub.configure(
                    text=(f"pre-punta · sorge alle {ora_loc} (tra {dt_min:.0f} min)"
                          f"  ·  El max {prossimo.get('el_max', 0) or 0:.0f}°"),
                    text_color="#e0a44a")
            else:
                self.lbl_punta.configure(text="—", text_color=MUT)
                self.box_punta.configure(border_color="#2a3c5a", fg_color="#12233d")
                self.lbl_punta_sub.configure(text=_tl("nessun passaggio in vista", "no pass in view"),
                                             text_color=MUT)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════
    #  REPLAY PASSAGGIO — footprint animato + analisi mutua
    # ══════════════════════════════════════════════════════════════
    # Regioni DX di riferimento (lat, lon) per capire dove "apre" il passaggio.
    _REGIONI_DX = [
        ("Nord America Est", 41.0, -74.0),
        ("Nord America Ovest", 37.0, -122.0),
        ("Centro America", 19.4, -99.1),
        ("Sud America", -23.5, -46.6),
        ("Africa australe", -26.2, 28.0),
        ("Medio Oriente", 31.0, 35.0),
        ("Asia / Giappone", 35.7, 139.7),
        ("Oceania / VK", -33.9, 151.2),
        ("Nord Europa / Russia", 55.8, 37.6),
    ]

    @staticmethod
    def _dist_km(lat1, lon1, lat2, lon2):
        import math
        R = 6371.0
        p1 = math.radians(lat1); p2 = math.radians(lat2)
        dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * R * math.asin(min(1.0, math.sqrt(a)))

    def _passaggio_selezionato(self, _event=None):
        try:
            sel = self.tree.selection()
            if not sel:
                return
            idx = self.tree.index(sel[0])
            if 0 <= idx < len(self._passaggi):
                self._avvia_animazione(idx)
        except Exception:
            pass

    def _avvia_animazione(self, idx):
        p = self._passaggi[idx]
        nome = p.get("sat") or self._sat_corrente or self.var_sat.get()
        sat = self._sats.get(nome)
        if not sat:
            self.lbl_anim.configure(text=_tl("Satellite non disponibile per l'animazione.", "Satellite not available for animation."))
            return
        if not hasattr(SAT, "traccia_passaggio"):
            self.lbl_anim.configure(
                text=_tl("Aggiorna radio/satellite.py: manca 'traccia_passaggio' (replay non disponibile).", "Update radio/satellite.py: 'traccia_passaggio' missing (replay unavailable)."))
            return
        obs = self._coord()
        try:
            track = SAT.traccia_passaggio(sat, p.get("aos"), p.get("los"), passi=90,
                                          oss_lat=obs[0] if obs else None,
                                          oss_lon=obs[1] if obs else None)
        except TypeError:
            track = SAT.traccia_passaggio(sat, p.get("aos"), p.get("los"), passi=90)
        if not track:
            self.lbl_anim.configure(text=_tl("Traccia non disponibile per questo passaggio.", "Track not available for this pass."))
            return

        self._live_on = False              # ferma il tempo reale
        if self._anim_after:
            try: self.after_cancel(self._anim_after)
            except Exception: pass
            self._anim_after = None

        self._anim_pass = p
        self._anim_track = track
        self._anim_idx = idx

        # Analisi mutua: per ogni istante, quali regioni DX vedono il sat
        # CONTEMPORANEAMENTE a te (entrambi dentro il footprint).
        regioni = list(self._REGIONI_DX)
        dx = self._coord_dx()
        if dx:
            regioni.insert(0, (self._loc_dx(), dx[0], dx[1]))
        self._anim_mutual_per_frame = []
        raggiunti = set()
        for s in track:
            mutual = []
            if obs:
                obs_in = self._dist_km(obs[0], obs[1], s["lat"], s["lon"]) <= s["raggio_km"]
                if obs_in:
                    for (nm, tlat, tlon) in regioni:
                        if self._dist_km(tlat, tlon, s["lat"], s["lon"]) <= s["raggio_km"]:
                            mutual.append(nm); raggiunti.add(nm)
            self._anim_mutual_per_frame.append(mutual)

        # Disegna mappa base + traccia completa del passaggio
        self._disegna_base()
        self._anim_artists = []
        self._anim_track_lines = []
        try:
            segx, segy = _spezza([(s["lat"], s["lon"]) for s in track])
            for a, b in zip(segx, segy):
                ln, = self.ax.plot(a, b, color=TRACK, lw=1.0, alpha=0.5, zorder=3)
                self._anim_track_lines.append(ln)
        except Exception:
            pass

        # Slider
        n = len(track)
        try:
            self.sld_anim.configure(state="normal", from_=0, to=max(1, n - 1),
                                    number_of_steps=max(1, n - 1))
        except Exception:
            pass
        self.btn_anim.configure(state="normal", text=_tl("⏸ Pausa", "⏸ Pause"))

        titolo = p["aos"].astimezone().strftime("%d/%m %H:%M")
        if raggiunti:
            self._anim_riepilogo = ("Passaggio %s — apertura mutua verso: %s"
                                    % (titolo, ", ".join(sorted(raggiunti))))
        elif obs:
            self._anim_riepilogo = ("Passaggio %s — nessuna regione DX in finestra mutua "
                                    "(copertura locale/EU)" % titolo)
        else:
            self._anim_riepilogo = ("Passaggio %s — imposta il locatore per l'analisi mutua" % titolo)

        self.lbl_map.configure(text=_tl("%s — replay passaggio (footprint in movimento)", "%s — pass replay (moving footprint)") % nome)
        self._anim_frame = 0
        self._anim_playing = True
        self._anim_tick()

    def _anim_tick(self):
        if not self._anim_track:
            return
        t0 = time.perf_counter()
        self._anim_disegna_frame(self._anim_frame)
        self._misura("fotogramma replay", t0, 50)
        if self._anim_playing:
            self._anim_frame += 1
            if self._anim_frame >= len(self._anim_track):
                self._anim_frame = 0        # loop continuo
            self._anim_after = self.after(120, self._anim_tick)

    def _anim_disegna_frame(self, i):
        if not self._anim_track:
            return
        i = max(0, min(i, len(self._anim_track) - 1))
        s = self._anim_track[i]
        # footprint, satellite e sky plot: si spostano, non si ricreano
        try:
            self._disegna_footprint(s["lat"], s["lon"], s["raggio_km"])
        except Exception:
            pass
        if "az" in s:
            self._polare_mostra(self._anim_track, (s["az"], s["el"]),
                                f"replay · Az {s['az']:.0f}° El {s['el']:.0f}°")
        self._sat_dot.set_data([s["lon"]], [s["lat"]])
        self._sat_txt.set_text(self._anim_pass.get("sat", ""))
        self._sat_txt.xy = (s["lon"], s["lat"])
        # sincronizza lo slider senza ritriggerare lo scrub
        self._sld_sync = True
        try: self.sld_anim.set(i)
        except Exception: pass
        self._sld_sync = False
        # etichetta info
        tt = s["t"].astimezone().strftime("%H:%M:%S")
        mut = self._anim_mutual_per_frame[i] if i < len(self._anim_mutual_per_frame) else []
        mut_txt = ("mutuo ora: " + ", ".join(mut)) if mut else "mutuo ora: —"
        self.lbl_anim.configure(
            text="%s\nt %s  ·  footprint %.0f km  ·  %s"
                 % (self._anim_riepilogo, tt, s["raggio_km"], mut_txt))
        self._aggiorna_canvas()

    def _anim_play_pause(self):
        if not self._anim_track:
            return
        self._anim_playing = not self._anim_playing
        self.btn_anim.configure(text=_tl("⏸ Pausa", "⏸ Pause") if self._anim_playing else "▶ Riprendi")
        if self._anim_playing:
            self._anim_tick()

    def _anim_scrub(self, val):
        if self._sld_sync or not self._anim_track:
            return
        self._anim_playing = False
        try: self.btn_anim.configure(text=_tl("▶ Riprendi", "▶ Resume"))
        except Exception: pass
        try:
            self._anim_frame = int(round(float(val)))
        except Exception:
            return
        self._anim_disegna_frame(self._anim_frame)

    def _stop_anim_soft(self):
        """Ferma l'animazione senza ridisegnare (usato prima di un ricalcolo)."""
        self._anim_playing = False
        if getattr(self, "_anim_after", None):
            try: self.after_cancel(self._anim_after)
            except Exception: pass
            self._anim_after = None
        self._anim_track = []
        self._anim_idx = None
        try:
            self.btn_anim.configure(text=_tl("⏸ Pausa", "⏸ Pause"), state="disabled")
            self.sld_anim.set(0); self.sld_anim.configure(state="disabled")
        except Exception:
            pass

    def _torna_live(self):
        """Chiude il replay e torna alla posizione in tempo reale."""
        self._stop_anim_soft()
        try:
            self.lbl_anim.configure(text=_tl("Clicca un passaggio nella tabella per vedere il footprint muoversi.", "Click a pass in the table to watch the footprint move."))
        except Exception:
            pass
        self._disegna_base()
        self._aggiorna_live(riavvia=True)

    def _chiudi(self):
        self._live_on = False
        if getattr(self, "_live_after", None):
            try: self.after_cancel(self._live_after)
            except Exception: pass
            self._live_after = None
        self._anim_playing = False
        if getattr(self, "_anim_after", None):
            try: self.after_cancel(self._anim_after)
            except Exception: pass
            self._anim_after = None
        self.destroy()
