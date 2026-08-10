import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import customtkinter as ctk
import tkinter.ttk as _ttk
from config import T

class GraficiDialog(ctk.CTkToplevel):
    def __init__(self, parent, qsos, colori_pdf):
        super().__init__(parent)
        self.title(T("graf_titolo"))
        self.geometry("820x540")
        self.resizable(True, True)
        self.grab_set()
        self.qsos = qsos
        self.colori_pdf = colori_pdf

        ctk.CTkLabel(self, text=T("graf_header"),
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=10)

        # Tab view
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=15, pady=5)
        self.tabs.add(T("graf_tab_anno"))
        self.tabs.add(T("graf_tab_mese"))
        self.tabs.add(T("graf_tab_mese_anno"))

        self._build_tab_anno(self.tabs.tab(T("graf_tab_anno")))
        self._build_tab_mese(self.tabs.tab(T("graf_tab_mese")))
        self._build_tab_mensile(self.tabs.tab(T("graf_tab_mese_anno")))

        ctk.CTkButton(self, text=T("chiudi"), command=self.destroy,
                      fg_color="#718096", width=120).pack(pady=8)

    def _conta(self):
        per_anno = {}
        per_mese = {}
        per_anno_mese = {}
        nomi_mesi = T("nomi_mesi_it")
        for qso in self.qsos:
            d = str(qso.get('qso_date', '')).strip()
            if len(d) == 8:
                anno = d[0:4]
                mese_n = int(d[4:6]) if d[4:6].isdigit() else 0
                mese = nomi_mesi[mese_n-1] if 1 <= mese_n <= 12 else "?"
                per_anno[anno] = per_anno.get(anno, 0) + 1
                per_mese[mese_n] = per_mese.get(mese_n, 0) + 1
                chiave = f"{anno}-{mese_n:02d}"
                per_anno_mese[chiave] = per_anno_mese.get(chiave, 0) + 1
        return per_anno, per_mese, per_anno_mese, nomi_mesi

    def _barra_canvas(self, parent, dati_ord, label_fn, colore, title):
        """Disegna un grafico a barre in un Canvas tkinter."""
        import tkinter as tk
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=10, pady=5)

        W, H = 760, 340
        PAD_L, PAD_R, PAD_T, PAD_B = 55, 20, 20, 60

        canvas_w = tk.Canvas(frame, width=W, height=H, bg="#F7FAFC", highlightthickness=0)
        canvas_w.pack(fill="both", expand=True)

        if not dati_ord:
            canvas_w.create_text(W//2, H//2, text=T("graf_no_data"), font=("Arial",13), fill="#718096")
            return

        valori = [v for _, v in dati_ord]
        labels = [label_fn(k) for k, _ in dati_ord]
        max_v = max(valori) if valori else 1
        n = len(dati_ord)

        area_w = W - PAD_L - PAD_R
        area_h = H - PAD_T - PAD_B
        bar_w = max(8, min(60, area_w // n - 4))
        gap = (area_w - bar_w * n) // (n + 1)

        # Griglia orizzontale
        steps = 5
        for i in range(steps + 1):
            y = PAD_T + area_h - int(area_h * i / steps)
            val = int(max_v * i / steps)
            canvas_w.create_line(PAD_L, y, W - PAD_R, y, fill="#CBD5E0", dash=(3, 4))
            canvas_w.create_text(PAD_L - 5, y, text=str(val), anchor="e", font=("Arial", 8), fill="#4A5568")

        # Barre
        hex_c = colore.lstrip('#')
        r2, g2, b2 = int(hex_c[0:2],16), int(hex_c[2:4],16), int(hex_c[4:6],16)
        col_hover = f"#{min(255,r2+40):02X}{min(255,g2+40):02X}{min(255,b2+40):02X}"

        for i, (k, v) in enumerate(dati_ord):
            x0 = PAD_L + gap + i * (bar_w + gap)
            x1 = x0 + bar_w
            bh = int(area_h * v / max_v) if max_v > 0 else 0
            y0 = PAD_T + area_h - bh
            y1 = PAD_T + area_h
            rect = canvas_w.create_rectangle(x0, y0, x1, y1, fill=colore, outline="", width=0)
            canvas_w.create_text((x0+x1)//2, y0 - 6, text=str(v), font=("Arial", 8, "bold"), fill="#1A365D")
            lab = labels[i]
            canvas_w.create_text((x0+x1)//2, y1 + 10, text=lab, font=("Arial", 8),
                                  fill="#4A5568", angle=35 if n > 12 else 0, anchor="n" if n <= 12 else "ne")

        # Asse X e Y
        canvas_w.create_line(PAD_L, PAD_T, PAD_L, PAD_T + area_h, fill="#4A5568", width=1)
        canvas_w.create_line(PAD_L, PAD_T + area_h, W - PAD_R, PAD_T + area_h, fill="#4A5568", width=1)
        canvas_w.create_text(W//2, 8, text=title, font=("Arial", 10, "bold"), fill="#1A365D")

    def _build_tab_anno(self, tab):
        per_anno, _, _, _ = self._conta()
        dati = sorted(per_anno.items())
        self._barra_canvas(tab, dati, lambda k: k, self.colori_pdf['primario'], T("graf_title_anno"))

    def _build_tab_mese(self, tab):
        _, per_mese, _, nomi_mesi = self._conta()
        dati = [(m, per_mese.get(m, 0)) for m in range(1, 13)]
        self._barra_canvas(tab, dati, lambda k: nomi_mesi[k-1], self.colori_pdf['secondario'], T("graf_title_mese"))

    def _build_tab_mensile(self, tab):
        _, _, per_anno_mese, _ = self._conta()
        dati = sorted(per_anno_mese.items())
        self._barra_canvas(tab, dati, lambda k: k, "#48BB78", T("graf_title_ma"))

# ─────────────────────────────────────────────
#  Cloudlog — upload QSO via API ufficiale
# ─────────────────────────────────────────────
import urllib.request
import urllib.error
import json as _cl_json


