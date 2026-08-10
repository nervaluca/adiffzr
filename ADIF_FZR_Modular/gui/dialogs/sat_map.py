# -*- coding: utf-8 -*-
"""
Mappa animata del passaggio satellitare per ADIF FZR.
Planisfero leggero (coste Natural Earth 110m incorporate) con footprint,
ground track, posizione osservatore e satellite che si muove nel tempo.
Si apre con doppio clic su un passaggio nella finestra "Passaggi satelliti".
"""

import customtkinter as ctk

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from radio import satellite as SAT
try:
    from radio.coastlines import COSTE
except Exception:
    COSTE = []

BG = "#0d1522"
COAST = "#3a5a80"
GRID = "#1e2f4d"
OSS = "#9edc3a"
TRACK = "#ffd54a"
FOOT = "#9edc3a"
SATCOL = "#ff6b6b"
TXT = "#e9eef7"
MUT = "#8fa2c0"


def _spezza_antimeridiano(cerchio):
    """Divide il cerchio footprint dove attraversa il bordo ±180° (lon),
    per evitare righe orizzontali che tagliano la mappa."""
    xs = [p[1] for p in cerchio]
    ys = [p[0] for p in cerchio]
    seg_x, seg_y = [[xs[0]]], [[ys[0]]]
    for i in range(1, len(xs)):
        if abs(xs[i] - xs[i - 1]) > 180:
            seg_x.append([]); seg_y.append([])
        seg_x[-1].append(xs[i]); seg_y[-1].append(ys[i])
    return seg_x, seg_y


class MappaPassaggioDialog(ctk.CTkToplevel):
    def __init__(self, parent, sat, aos_dt, los_dt,
                 oss_lat=None, oss_lon=None, nome_sat=""):
        super().__init__(parent)
        self.title(f"Mappa passaggio — {nome_sat}")
        self.geometry("1040x640")
        self.grab_set()

        self.sat = sat
        self.oss_lat = oss_lat
        self.oss_lon = oss_lon
        self.nome_sat = nome_sat

        # campiona la traccia del passaggio
        self.tr = SAT.traccia_passaggio(sat, aos_dt, los_dt, passi=80)
        self.idx = 0
        self._playing = False

        if not self.tr:
            ctk.CTkLabel(self, text="Impossibile calcolare la traccia del passaggio.",
                         text_color="#ff6b6b").pack(pady=40)
            ctk.CTkButton(self, text="Chiudi", command=self.destroy).pack()
            return

        # ── Figura matplotlib ──
        self.fig = Figure(figsize=(10, 5), dpi=100, facecolor=BG)
        self.ax = self.fig.add_subplot(111)
        self._disegna_base()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(8, 0))

        # ── Controlli ──
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=10, pady=8)

        self.btn_play = ctk.CTkButton(barra, text="▶ Play", width=90, command=self._toggle)
        self.btn_play.pack(side="left")

        self.slider = ctk.CTkSlider(barra, from_=0, to=len(self.tr) - 1,
                                    number_of_steps=len(self.tr) - 1,
                                    command=self._slide)
        self.slider.set(0)
        self.slider.pack(side="left", fill="x", expand=True, padx=12)

        self.lbl = ctk.CTkLabel(barra, text="", text_color=MUT, width=260, anchor="e")
        self.lbl.pack(side="right")

        self._disegna_frame(0)
        self.protocol("WM_DELETE_WINDOW", self._chiudi)

    # ──────────────────────────────────────────────
    def _disegna_base(self):
        ax = self.ax
        ax.clear()
        ax.set_facecolor(BG)
        for linea in COSTE:
            ax.plot([p[0] for p in linea], [p[1] for p in linea],
                    color=COAST, lw=0.6, zorder=1)
        ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
        ax.set_xticks(range(-180, 181, 60)); ax.set_yticks(range(-90, 91, 30))
        ax.grid(True, color=GRID, lw=0.4)
        ax.tick_params(colors=MUT, labelsize=7)
        for spine in ax.spines.values():
            spine.set_color(GRID)

        # traccia completa del passaggio
        ax.plot([c["lon"] for c in self.tr], [c["lat"] for c in self.tr],
                color=TRACK, lw=1.2, zorder=3)
        # osservatore
        if self.oss_lat is not None and self.oss_lon is not None:
            ax.plot(self.oss_lon, self.oss_lat, marker="*",
                    color=OSS, markersize=15, zorder=6)

        # elementi mobili (creati vuoti, aggiornati per frame)
        (self._foot_lines) = []
        (self._sat_dot,) = ax.plot([], [], marker="o", color=SATCOL,
                                    markersize=9, zorder=7)
        self.fig.tight_layout()

    def _disegna_frame(self, i):
        i = max(0, min(i, len(self.tr) - 1))
        self.idx = i
        c = self.tr[i]

        # rimuovi il footprint precedente
        for ln in getattr(self, "_foot_lines", []):
            try:
                ln.remove()
            except Exception:
                pass
        self._foot_lines = []

        cer = SAT.cerchio_footprint(c["lat"], c["lon"], c["raggio_km"], punti=120)
        for sx, sy in zip(*_spezza_antimeridiano(cer)):
            ln, = self.ax.plot(sx, sy, color=FOOT, lw=1.4, alpha=0.85, zorder=4)
            self._foot_lines.append(ln)

        self._sat_dot.set_data([c["lon"]], [c["lat"]])

        ora = c["t"].astimezone().strftime("%H:%M:%S")
        self.lbl.configure(text=f"{ora}  ·  lat {c['lat']:.1f}°  lon {c['lon']:.1f}°  "
                                f"·  footprint {c['raggio_km']:.0f} km")
        self.canvas.draw_idle()

    # ── Animazione ──
    def _toggle(self):
        self._playing = not self._playing
        self.btn_play.configure(text="⏸ Pausa" if self._playing else "▶ Play")
        if self._playing:
            if self.idx >= len(self.tr) - 1:
                self.idx = 0
            self._passo()

    def _passo(self):
        if not self._playing:
            return
        self._disegna_frame(self.idx)
        self.slider.set(self.idx)
        if self.idx >= len(self.tr) - 1:
            self._playing = False
            self.btn_play.configure(text="▶ Play")
            return
        self.idx += 1
        self.after(120, self._passo)

    def _slide(self, val):
        self._playing = False
        self.btn_play.configure(text="▶ Play")
        self._disegna_frame(int(float(val)))

    def _chiudi(self):
        self._playing = False
        self.destroy()
