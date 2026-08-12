import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import customtkinter as ctk
import theme as TH
from tkinter import colorchooser, messagebox
import tkinter.ttk as _ttk
from config import T

class ColoriDialog(ctk.CTkToplevel):
    def __init__(self, parent, colori_correnti):
        super().__init__(parent)
        self.title(T("colori_titolo"))
        self.geometry("380x320")
        self.resizable(False, False)
        self.grab_set()
        self.colori = dict(colori_correnti)
        self.risultato = None

        ctk.CTkLabel(self, text=T("colori_titolo"), font=ctk.CTkFont(size=16, weight="bold")).pack(pady=12)

        etichette = {
            'primario': T("colori_primario"),
            'secondario': T("colori_secondario"),
            'riga_pari': T("colori_riga_pari"),
        }

        self.anteprime = {}
        frame = ctk.CTkFrame(self)
        frame.pack(padx=20, fill="both", expand=True)

        for idx, (chiave, nome) in enumerate(etichette.items()):
            ctk.CTkLabel(frame, text=nome).grid(row=idx, column=0, sticky="w", padx=10, pady=8)
            btn = ctk.CTkButton(frame, text="  ", width=60, height=28,
                                fg_color=self.colori[chiave],
                                command=lambda k=chiave: self.scegli_colore(k))
            btn.grid(row=idx, column=1, padx=10)
            self.anteprime[chiave] = btn

        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(pady=12, fill="x", padx=20)
        ctk.CTkButton(frame_btn, text=T("colori_salva"), command=self.salva, fg_color=TH.PRIMARY).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(frame_btn, text=T("colori_ripristina"), command=self.ripristina, fg_color="#718096").pack(side="left", expand=True, padx=5)

    def scegli_colore(self, chiave):
        colore = colorchooser.askcolor(color=self.colori[chiave], title=f"Scegli colore")[1]
        if colore:
            self.colori[chiave] = colore
            self.anteprime[chiave].configure(fg_color=colore)

    def ripristina(self):
        self.colori = {'primario': '#1A365D', 'secondario': '#2B6CB0', 'riga_pari': '#F7FAFC'}
        for k, btn in self.anteprime.items():
            btn.configure(fg_color=self.colori[k])

    def salva(self):
        self.risultato = self.colori
        self.destroy()



# ─────────────────────────────────────────────
#  Dialogo Colori HTML Web
# ─────────────────────────────────────────────
class ColoriHtmlDialog(ctk.CTkToplevel):
    DEFAULT = {
        'primario':   '#1A365D',
        'secondario': '#2B6CB0',
        'bg_scuro':   '#0D1117',
        'bg_chiaro':  '#F7FAFC',
    }

    def __init__(self, parent, colori_correnti):
        super().__init__(parent)
        self.title(T("colori_html_titolo"))
        self.geometry("400x280")
        self.resizable(False, False)
        self.grab_set()
        self.colori = dict(colori_correnti)
        self.risultato = None

        ctk.CTkLabel(self, text=T("colori_html_titolo"),
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=12)

        etichette = {
            'primario':   T("colori_html_primario"),
            'secondario': T("colori_html_secondario"),
            'bg_scuro':   T("colori_html_bg_scuro"),
            'bg_chiaro':  T("colori_html_bg_chiaro"),
        }
        self.anteprime = {}
        frame = ctk.CTkFrame(self)
        frame.pack(padx=20, fill="both", expand=True)

        for idx, (chiave, nome) in enumerate(etichette.items()):
            ctk.CTkLabel(frame, text=nome, anchor="w").grid(
                row=idx, column=0, sticky="w", padx=10, pady=7)
            btn = ctk.CTkButton(frame, text="  ", width=60, height=28,
                                fg_color=self.colori.get(chiave, self.DEFAULT[chiave]),
                                command=lambda k=chiave: self._scegli(k))
            btn.grid(row=idx, column=1, padx=10)
            self.anteprime[chiave] = btn

        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(pady=12, fill="x", padx=20)
        ctk.CTkButton(frame_btn, text=T("colori_html_salva"),
                      command=self._salva, fg_color=TH.PRIMARY).pack(
                      side="left", expand=True, padx=(0,6), fill="x")
        ctk.CTkButton(frame_btn, text=T("colori_html_ripristina"),
                      command=self._ripristina, fg_color="#718096").pack(
                      side="left", expand=True, fill="x")

    def _scegli(self, chiave):
        colore = colorchooser.askcolor(
            color=self.colori.get(chiave, self.DEFAULT[chiave]))[1]
        if colore:
            self.colori[chiave] = colore
            self.anteprime[chiave].configure(fg_color=colore)

    def _ripristina(self):
        self.colori = dict(self.DEFAULT)
        for k, btn in self.anteprime.items():
            btn.configure(fg_color=self.colori[k])

    def _salva(self):
        self.risultato = self.colori
        self.destroy()


# ─────────────────────────────────────────────
#  Dialogo Opzioni Registro PDF
# ─────────────────────────────────────────────
class OpzioniRegistroPDFDialog(ctk.CTkToplevel):
    """Dialog per personalizzare il registro PDF:
    ordine e larghezza colonne, titolo, font size celle."""

    def __init__(self, parent, campi_disponibili, ordine_campi,
                 checkboxes, width_pdf, titolo_custom, font_size):
        super().__init__(parent)
        self.title("Opzioni Registro PDF")
        self.geometry("560x620")
        self.resizable(False, True)
        self.grab_set(); self.lift(); self.focus_force()

        self.campi_disponibili = campi_disponibili
        self.risultato = None  # (ordine, width_pdf, titolo, font_size) se salvato

        # Copia lavoro dell'ordine
        self._ordine = [t for t in ordine_campi if t in campi_disponibili]
        # Aggiungi eventuali campi non ancora nell'ordine
        for t in campi_disponibili:
            if t not in self._ordine:
                self._ordine.append(t)

        ctk.CTkLabel(self, text=T("orp_titolo"),
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(14,4))

        # ── Titolo personalizzato ──────────────────
        frame_titolo = ctk.CTkFrame(self)
        frame_titolo.pack(fill="x", padx=16, pady=(6,4))
        ctk.CTkLabel(frame_titolo, text=T("orp_titolo_reg"),
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10, pady=(6,2))
        self.entry_titolo = ctk.CTkEntry(frame_titolo, width=480,
                                          placeholder_text=T("orp_titolo_ph"))
        if titolo_custom:
            self.entry_titolo.insert(0, titolo_custom)
        self.entry_titolo.pack(padx=10, pady=(0,8))

        # ── Font size celle ────────────────────────
        frame_font = ctk.CTkFrame(self)
        frame_font.pack(fill="x", padx=16, pady=(0,4))
        ctk.CTkLabel(frame_font, text=T("orp_dim_testo"),
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=10, pady=8)
        self.var_fontsize = ctk.StringVar(value=str(font_size))
        ctk.CTkEntry(frame_font, textvariable=self.var_fontsize,
                     width=50, justify="center").pack(side="left", padx=(0,8))
        ctk.CTkLabel(frame_font, text=T("orp_consigliato"),
                     font=ctk.CTkFont(size=9), text_color="gray").pack(side="left")

        # ── Colonne: ordine e larghezza ───────────
        ctk.CTkLabel(self, text=T("orp_colonne"),
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=16, pady=(8,2))
        ctk.CTkLabel(self,
                     text=T("orp_colonne_hint"),
                     font=ctk.CTkFont(size=9), text_color="gray").pack(anchor="w", padx=16)

        self._scroll = ctk.CTkScrollableFrame(self, height=320)
        self._scroll.pack(fill="x", padx=16, pady=(4,4))

        self._var_w  = {}  # tag -> StringVar larghezza
        self._rows   = []  # lista di frame nell'ordine corrente

        def _build_rows():
            for w in self._scroll.winfo_children():
                w.destroy()
            self._rows.clear()
            for tag in self._ordine:
                info = campi_disponibili[tag]
                w_val = width_pdf.get(tag, info['width_base'])
                if tag not in self._var_w:
                    self._var_w[tag] = ctk.StringVar(value=str(w_val))
                else:
                    self._var_w[tag].set(str(w_val))

                row = ctk.CTkFrame(self._scroll, fg_color="transparent")
                row.pack(fill="x", pady=1)
                self._rows.append((tag, row))

                # ☑ checkbox attiva
                ctk.CTkCheckBox(row, text="", variable=checkboxes[tag],
                                 width=24, checkbox_width=16, checkbox_height=16
                                 ).pack(side="left", padx=(0,4))

                # Nome campo
                ctk.CTkLabel(row, text=info['nome'], width=90,
                             anchor="w", font=ctk.CTkFont(size=10)).pack(side="left")

                # Larghezza
                ctk.CTkEntry(row, textvariable=self._var_w[tag],
                             width=48, justify="center",
                             font=ctk.CTkFont(size=10)).pack(side="left", padx=(4,8))

                # Frecce su/giù
                def _su(t=tag):
                    i = self._ordine.index(t)
                    if i > 0:
                        self._ordine[i], self._ordine[i-1] = self._ordine[i-1], self._ordine[i]
                        _build_rows()
                def _giu(t=tag):
                    i = self._ordine.index(t)
                    if i < len(self._ordine) - 1:
                        self._ordine[i], self._ordine[i+1] = self._ordine[i+1], self._ordine[i]
                        _build_rows()

                ctk.CTkButton(row, text="↑", width=26, height=22,
                              fg_color=TH.PRIMARY, command=_su,
                              font=ctk.CTkFont(size=10)).pack(side="left", padx=(0,2))
                ctk.CTkButton(row, text="↓", width=26, height=22,
                              fg_color=TH.PRIMARY, command=_giu,
                              font=ctk.CTkFont(size=10)).pack(side="left")

                # Tag piccolo per riferimento
                ctk.CTkLabel(row, text=tag, width=120,
                             anchor="w", font=ctk.CTkFont(size=8),
                             text_color="gray").pack(side="left", padx=(8,0))

        _build_rows()

        # ── Pulsanti ──────────────────────────────
        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(fill="x", padx=16, pady=(4,14))

        def _ripristina():
            self._ordine = list(campi_disponibili.keys())
            for tag, info in campi_disponibili.items():
                self._var_w[tag].set(str(info['width_base']))
            self.entry_titolo.delete(0, "end")
            self.var_fontsize.set("7")
            _build_rows()

        def _salva():
            try:
                fs = max(5, min(14, int(self.var_fontsize.get())))
            except ValueError:
                fs = 7
            new_width = {tag: int(float(self._var_w[tag].get()))
                         for tag in self._ordine
                         if self._var_w[tag].get().strip().isdigit() or
                            (self._var_w[tag].get().replace('.','',1).isdigit())}
            self.risultato = (
                list(self._ordine),
                new_width,
                self.entry_titolo.get().strip(),
                fs,
            )
            self.destroy()

        ctk.CTkButton(frame_btn, text=T("orp_ripristina"), width=150, height=32,
                      fg_color="#718096", command=_ripristina).pack(side="left", padx=(0,8))
        ctk.CTkButton(frame_btn, text=T("orp_salva"), height=32,
                      fg_color=TH.SUCCESS_H, hover_color=TH.SUCCESS,
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=_salva).pack(side="left", expand=True, fill="x", padx=(0,8))
        ctk.CTkButton(frame_btn, text=T("orp_annulla"), width=90, height=32,
                      fg_color="#4A5568", command=self.destroy).pack(side="left")


# ─────────────────────────────────────────────
#  Dialogo Unisci File ADIF
# ─────────────────────────────────────────────
