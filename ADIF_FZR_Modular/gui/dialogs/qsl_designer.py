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
import customtkinter as ctk
from tkinter import filedialog, messagebox, colorchooser
import tkinter.ttk as _ttk
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from config import T
from utils.dxcc import dxcc_da_nominativo

class QSLCardDesignerDialog(ctk.CTkToplevel):
    """Editor visuale per QSL card 140×90mm.
    Drag-and-drop dei campi sul canvas, immagine di sfondo,
    esportazione PDF (1 per pagina o 2×2 su A4 landscape)."""

    SCALE   = 4          # px per mm sul canvas
    CARD_W  = 140        # mm
    CARD_H  = 90         # mm
    TEMPLATE_PATH = os.path.join(os.path.expanduser("~"), ".adif_fzr_qslcard_template.json")

    CAMPI = {
        'call':         'Callsign DX',
        'my_call':      'Mio Callsign',
        'qso_date':     'Data QSO',
        'time_on':      'Ora UTC',
        'band':         'Banda',
        'mode':         'Modo',
        'rst_sent':     'RST inviato',
        'freq':         'Frequenza (MHz)',
        'gridsquare':   'Locator DX',
        'name':         'Nome op. DX',
        'country':      'DXCC',
        'my_gridsquare':'Mio Locator',
        '__static__':   'Testo fisso…',
    }

    def __init__(self, parent, qsos, stazione, colori_pdf):
        super().__init__(parent)
        self.title("QSL Card Designer — 140×90mm")
        self.geometry("1020x620")
        self.resizable(True, True)
        self.grab_set(); self.lift(); self.focus_force()

        self.qsos        = qsos
        self.stazione    = stazione
        self.colori_pdf  = colori_pdf
        self.bg_image_path = None      # percorso immagine di sfondo
        self._bg_photo   = None        # PhotoImage per canvas
        self._elementi   = []          # lista di dict per ogni campo sul canvas
        self._sel_idx    = None        # indice elemento selezionato
        self._drag_data  = {}

        CW = self.CARD_W * self.SCALE
        CH = self.CARD_H * self.SCALE

        # ── Layout principale ──────────────────
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=8, pady=8)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=0)
        main.rowconfigure(0, weight=1)

        # ── Canvas editor ──────────────────────
        frame_canvas = ctk.CTkFrame(main)
        frame_canvas.grid(row=0, column=0, sticky="nsew", padx=(0,6))
        ctk.CTkLabel(frame_canvas, text=T("qcd_editor"),
                     font=ctk.CTkFont(size=11), text_color="gray").pack(pady=(6,2))

        import tkinter as _tk
        self.canvas = _tk.Canvas(frame_canvas, width=CW, height=CH,
                                  bg="#FFFFFF", cursor="crosshair",
                                  highlightthickness=1, highlightbackground="#4A5568")
        self.canvas.pack(padx=10, pady=(0,10))

        # Bordo card
        self.canvas.create_rectangle(0, 0, CW-1, CH-1,
                                      outline="#2B6CB0", width=2, tags="border")

        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_dbl)

        # ── Pannello destro ────────────────────
        panel = ctk.CTkScrollableFrame(main, width=280, fg_color="transparent")
        panel.grid(row=0, column=1, sticky="nsew")

        # — Sfondo —
        ctk.CTkLabel(panel, text=T("qcd_sfondo"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#2B6CB0").pack(anchor="w", padx=6, pady=(4,2))
        self.lbl_bg = ctk.CTkLabel(panel, text=T("qcd_no_img"),
                                    font=ctk.CTkFont(size=10), text_color="gray")
        self.lbl_bg.pack(anchor="w", padx=6)
        frame_bg = ctk.CTkFrame(panel, fg_color="transparent")
        frame_bg.pack(fill="x", padx=6, pady=(2,8))
        ctk.CTkButton(frame_bg, text="📷 Carica sfondo",
                      command=self._carica_sfondo, height=28,
                      font=ctk.CTkFont(size=11)).pack(side="left", padx=(0,4))
        ctk.CTkButton(frame_bg, text="✕", width=28, height=28,
                      fg_color="#718096", command=self._rimuovi_sfondo).pack(side="left")

        # — Campi —
        ctk.CTkLabel(panel, text=T("qcd_aggiungi_campo"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#2B6CB0").pack(anchor="w", padx=6, pady=(4,2))
        for campo, nome in self.CAMPI.items():
            ctk.CTkButton(panel, text=f"+ {nome}", height=26, anchor="w",
                          fg_color="transparent", border_width=1,
                          hover_color="#2D3748", font=ctk.CTkFont(size=10),
                          command=lambda c=campo, n=nome: self._aggiungi_campo(c, n)
                          ).pack(fill="x", padx=6, pady=1)

        # — Proprietà campo selezionato —
        ctk.CTkLabel(panel, text=T("qcd_proprieta"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#2B6CB0").pack(anchor="w", padx=6, pady=(10,2))

        self.frame_props = ctk.CTkFrame(panel)
        self.frame_props.pack(fill="x", padx=6, pady=(0,6))
        self.lbl_nessuna_sel = ctk.CTkLabel(self.frame_props,
                                             text=T("qcd_clicca_campo"),
                                             font=ctk.CTkFont(size=10), text_color="gray")
        self.lbl_nessuna_sel.pack(pady=8)

        self.var_font_size  = ctk.StringVar(value="12")
        self.var_bold       = ctk.BooleanVar(value=False)
        self.var_italic     = ctk.BooleanVar(value=False)
        self.var_color      = ctk.StringVar(value="#000000")
        self.var_align      = ctk.StringVar(value="left")
        self.var_static_txt = ctk.StringVar(value="")
        self._props_widgets = []   # tenuti per show/hide

        # — Azioni —
        ctk.CTkLabel(panel, text=T("qcd_azioni"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#2B6CB0").pack(anchor="w", padx=6, pady=(8,2))
        ctk.CTkButton(panel, text=T("qcd_elimina_sel"), height=28,
                      fg_color="#718096", command=self._elimina_sel,
                      font=ctk.CTkFont(size=10)).pack(fill="x", padx=6, pady=1)
        ctk.CTkButton(panel, text="🧹 Azzera tutto", height=28,
                      fg_color="#718096", command=self._azzera,
                      font=ctk.CTkFont(size=10)).pack(fill="x", padx=6, pady=1)
        ctk.CTkButton(panel, text=T("qcd_salva_tpl"), height=28,
                      fg_color="#276749", command=self._salva_template,
                      font=ctk.CTkFont(size=10)).pack(fill="x", padx=6, pady=(6,1))
        ctk.CTkButton(panel, text=T("qcd_carica_tpl"), height=28,
                      fg_color="#276749", command=self._carica_template,
                      font=ctk.CTkFont(size=10)).pack(fill="x", padx=6, pady=1)

        # — Genera PDF —
        ctk.CTkLabel(panel, text=T("qcd_genera_pdf"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#2B6CB0").pack(anchor="w", padx=6, pady=(10,2))
        self.var_layout = ctk.StringVar(value="1per")
        ctk.CTkRadioButton(panel, text="1 card per pagina",
                           variable=self.var_layout, value="1per").pack(anchor="w", padx=10)
        ctk.CTkRadioButton(panel, text="2×2 per foglio A4 (da ritagliare)",
                           variable=self.var_layout, value="4per").pack(anchor="w", padx=10)
        self.var_qso_scope = ctk.StringVar(value="tutti")
        ctk.CTkRadioButton(panel, text=f"Tutti i QSO ({len(qsos)})",
                           variable=self.var_qso_scope, value="tutti").pack(anchor="w", padx=10, pady=(4,0))
        ctk.CTkRadioButton(panel, text=T("qcd_solo_primo"),
                           variable=self.var_qso_scope, value="primo").pack(anchor="w", padx=10)
        ctk.CTkButton(panel, text=T("qcd_genera_pdf_btn"),
                      command=self._genera_pdf, height=38,
                      fg_color="#4A5568", hover_color="#2D3748",
                      font=ctk.CTkFont(size=12, weight="bold")).pack(
                      fill="x", padx=6, pady=(8,4))

        # Carica template se esiste
        self._carica_template(silent=True)

    # ── Canvas helpers ─────────────────────────

    def _canvas_pos(self, event):
        return event.x, event.y

    def _mm_from_px(self, px, py):
        return px / self.SCALE, py / self.SCALE

    def _px_from_mm(self, mx, my):
        return mx * self.SCALE, my * self.SCALE

    def _etichetta_canvas(self, el):
        """Testo mostrato nel canvas per un elemento."""
        if el['campo'] == '__static__':
            return el.get('testo_statico', 'Testo fisso')
        return self.CAMPI.get(el['campo'], el['campo'])

    def _disegna_elemento(self, el):
        """Disegna/aggiorna un elemento sul canvas."""
        px, py = self._px_from_mm(el['x_mm'], el['y_mm'])
        font_px = max(8, int(el['font_size'] * self.SCALE / 4))
        weight = "bold" if el.get('bold') else "normal"
        slant  = "italic" if el.get('italic') else "roman"

        import tkinter.font as _tkfont
        try:
            fn = _tkfont.Font(family="Helvetica", size=font_px,
                              weight=weight, slant=slant)
        except Exception:
            fn = ("Helvetica", font_px)

        testo = self._etichetta_canvas(el)
        sel = (self._sel_idx is not None and
               self._elementi[self._sel_idx] is el) if self._sel_idx is not None else False

        tag = el['_tag']
        self.canvas.delete(tag)

        anchor = {"left": "nw", "center": "n", "right": "ne"}.get(el.get('align','left'), 'nw')
        txt_id = self.canvas.create_text(
            px, py, text=testo, anchor=anchor,
            fill=el.get('color', '#000000'),
            font=fn, tags=(tag, "campo"))

        # Rettangolo di selezione
        if sel:
            bb = self.canvas.bbox(txt_id)
            if bb:
                self.canvas.create_rectangle(
                    bb[0]-2, bb[1]-2, bb[2]+2, bb[3]+2,
                    outline="#E53E3E", width=1, dash=(3,3), tags=(tag,))

        el['_id'] = txt_id

    def _ridisegna_tutto(self):
        self.canvas.delete("campo")
        for el in self._elementi:
            self._disegna_elemento(el)

    # ── Drag-and-drop ──────────────────────────

    def _find_elemento_at(self, x, y):
        items = self.canvas.find_overlapping(x-4, y-4, x+4, y+4)
        for item in reversed(items):
            tags = self.canvas.gettags(item)
            for el in self._elementi:
                if el.get('_tag') in tags and el.get('_id') == item:
                    return self._elementi.index(el)
                if el.get('_tag') in tags:
                    return self._elementi.index(el)
        return None

    def _on_press(self, event):
        idx = self._find_elemento_at(event.x, event.y)
        self._sel_idx = idx
        self._drag_data = {'x': event.x, 'y': event.y}
        self._ridisegna_tutto()
        self._aggiorna_props()

    def _on_drag(self, event):
        if self._sel_idx is None:
            return
        dx = event.x - self._drag_data['x']
        dy = event.y - self._drag_data['y']
        el = self._elementi[self._sel_idx]
        el['x_mm'] = max(0, min(self.CARD_W, el['x_mm'] + dx / self.SCALE))
        el['y_mm'] = max(0, min(self.CARD_H, el['y_mm'] + dy / self.SCALE))
        self._drag_data = {'x': event.x, 'y': event.y}
        self._disegna_elemento(el)

    def _on_release(self, event):
        pass

    def _on_dbl(self, event):
        """Doppio click: modifica testo statico."""
        idx = self._find_elemento_at(event.x, event.y)
        if idx is None:
            return
        el = self._elementi[idx]
        if el['campo'] != '__static__':
            return
        from tkinter.simpledialog import askstring
        nuovo = askstring("Testo fisso", "Inserisci il testo:", parent=self,
                          initialvalue=el.get('testo_statico', ''))
        if nuovo is not None:
            el['testo_statico'] = nuovo
            self._disegna_elemento(el)

    # ── Proprietà campo selezionato ────────────

    def _aggiorna_props(self):
        for w in self._props_widgets:
            try: w.destroy()
            except Exception: pass
        self._props_widgets.clear()

        if self._sel_idx is None:
            self.lbl_nessuna_sel.pack(pady=8)
            return

        self.lbl_nessuna_sel.pack_forget()
        el = self._elementi[self._sel_idx]

        def row(lbl, widget):
            f = ctk.CTkFrame(self.frame_props, fg_color="transparent")
            f.pack(fill="x", padx=6, pady=2)
            ctk.CTkLabel(f, text=lbl, width=80, anchor="e",
                         font=ctk.CTkFont(size=10)).pack(side="left")
            widget_built = widget(f)
            widget_built.pack(side="left", padx=(4,0))
            self._props_widgets.append(f)

        # Testo statico
        if el['campo'] == '__static__':
            self.var_static_txt.set(el.get('testo_statico', ''))
            def _upd_txt(*_):
                el['testo_statico'] = self.var_static_txt.get()
                self._disegna_elemento(el)
            f2 = ctk.CTkFrame(self.frame_props, fg_color="transparent")
            f2.pack(fill="x", padx=6, pady=2)
            ctk.CTkLabel(f2, text=T("qcd_testo"), width=80, anchor="e",
                         font=ctk.CTkFont(size=10)).pack(side="left")
            e = ctk.CTkEntry(f2, textvariable=self.var_static_txt, width=140)
            e.pack(side="left", padx=(4,0))
            e.bind("<KeyRelease>", _upd_txt)
            self._props_widgets.append(f2)

        # Font size
        self.var_font_size.set(str(el.get('font_size', 12)))
        def _upd_size(*_):
            try:
                el['font_size'] = max(6, min(48, int(self.var_font_size.get())))
                self._disegna_elemento(el)
            except ValueError: pass
        f3 = ctk.CTkFrame(self.frame_props, fg_color="transparent")
        f3.pack(fill="x", padx=6, pady=2)
        ctk.CTkLabel(f3, text=T("qcd_dimensione"), width=80, anchor="e",
                     font=ctk.CTkFont(size=10)).pack(side="left")
        e2 = ctk.CTkEntry(f3, textvariable=self.var_font_size, width=50, justify="center")
        e2.pack(side="left", padx=(4,0))
        e2.bind("<KeyRelease>", _upd_size)
        self._props_widgets.append(f3)

        # Bold / Italic
        self.var_bold.set(el.get('bold', False))
        self.var_italic.set(el.get('italic', False))
        def _upd_style(*_):
            el['bold'] = self.var_bold.get()
            el['italic'] = self.var_italic.get()
            self._disegna_elemento(el)
        f4 = ctk.CTkFrame(self.frame_props, fg_color="transparent")
        f4.pack(fill="x", padx=6, pady=2)
        cb1 = ctk.CTkCheckBox(f4, text=T("qcd_grassetto"), variable=self.var_bold,
                               command=_upd_style, font=ctk.CTkFont(size=10))
        cb1.pack(side="left", padx=(4,0))
        cb2 = ctk.CTkCheckBox(f4, text=T("qcd_corsivo"), variable=self.var_italic,
                               command=_upd_style, font=ctk.CTkFont(size=10))
        cb2.pack(side="left", padx=(8,0))
        self._props_widgets.append(f4)

        # Colore
        self.var_color.set(el.get('color', '#000000'))
        def _scegli_colore():
            c = colorchooser.askcolor(color=self.var_color.get(), parent=self)[1]
            if c:
                self.var_color.set(c); el['color'] = c
                btn_col.configure(fg_color=c)
                self._disegna_elemento(el)
        f5 = ctk.CTkFrame(self.frame_props, fg_color="transparent")
        f5.pack(fill="x", padx=6, pady=2)
        ctk.CTkLabel(f5, text=T("qcd_colore"), width=80, anchor="e",
                     font=ctk.CTkFont(size=10)).pack(side="left")
        btn_col = ctk.CTkButton(f5, text="  ", width=40, height=24,
                                 fg_color=self.var_color.get(),
                                 command=_scegli_colore)
        btn_col.pack(side="left", padx=(4,0))
        self._props_widgets.append(f5)

        # Allineamento
        self.var_align.set(el.get('align', 'left'))
        def _upd_align(v):
            el['align'] = v; self._disegna_elemento(el)
        f6 = ctk.CTkFrame(self.frame_props, fg_color="transparent")
        f6.pack(fill="x", padx=6, pady=(2,6))
        ctk.CTkLabel(f6, text=T("qcd_allinea"), width=80, anchor="e",
                     font=ctk.CTkFont(size=10)).pack(side="left")
        for val, lbl in [("left","◀"), ("center","▬"), ("right","▶")]:
            ctk.CTkButton(f6, text=lbl, width=30, height=24,
                          command=lambda v=val: _upd_align(v),
                          fg_color="#4A5568" if self.var_align.get()!=val else "#2B6CB0"
                          ).pack(side="left", padx=2)
        self._props_widgets.append(f6)

    # ── Azioni ─────────────────────────────────

    def _aggiungi_campo(self, campo, nome):
        tag = f"el_{len(self._elementi)}_{campo}"
        el = {
            'campo': campo, '_tag': tag, '_id': None,
            'x_mm': 10.0, 'y_mm': 10.0 + len(self._elementi) * 8,
            'font_size': 14 if campo == 'call' else 10,
            'bold': campo in ('call', 'my_call'),
            'italic': False, 'color': '#000000', 'align': 'left',
            'testo_statico': 'Testo fisso',
        }
        # Evita duplicati (tranne testo statico)
        if campo != '__static__':
            for e in self._elementi:
                if e['campo'] == campo:
                    messagebox.showinfo("Info",
                        f"Il campo '{nome}' è già sulla card.", parent=self)
                    return
        self._elementi.append(el)
        self._sel_idx = len(self._elementi) - 1
        self._disegna_elemento(el)
        self._aggiorna_props()

    def _elimina_sel(self):
        if self._sel_idx is None:
            return
        el = self._elementi.pop(self._sel_idx)
        self.canvas.delete(el['_tag'])
        self._sel_idx = None
        self._aggiorna_props()

    def _azzera(self):
        if messagebox.askyesno("Azzera", "Rimuovere tutti i campi dalla card?", parent=self):
            for el in self._elementi:
                self.canvas.delete(el['_tag'])
            self._elementi.clear()
            self._sel_idx = None
            self._aggiorna_props()

    # ── Sfondo ─────────────────────────────────

    def _carica_sfondo(self):
        path = filedialog.askopenfilename(
            title=T("qcd_sel_sfondo"),
            filetypes=[("Immagini", "*.png *.jpg *.jpeg *.bmp *.gif"),
                       ("Tutti i file", "*.*")])
        if not path:
            return
        self.bg_image_path = path
        self.lbl_bg.configure(text=os.path.basename(path))
        self._aggiorna_bg_canvas()

    def _rimuovi_sfondo(self):
        self.bg_image_path = None
        self._bg_photo = None
        self.canvas.delete("bg")
        self.lbl_bg.configure(text=T("qcd_no_img"))

    def _aggiorna_bg_canvas(self):
        if not self.bg_image_path:
            return
        try:
            from PIL import Image, ImageTk
            img = Image.open(self.bg_image_path).resize(
                (self.CARD_W * self.SCALE, self.CARD_H * self.SCALE),
                Image.LANCZOS)
            self._bg_photo = ImageTk.PhotoImage(img)
            self.canvas.delete("bg")
            self.canvas.create_image(0, 0, anchor="nw",
                                      image=self._bg_photo, tags="bg")
            self.canvas.tag_lower("bg")
            self.canvas.tag_raise("border")
        except Exception as ex:
            messagebox.showwarning("Attenzione",
                f"Impossibile caricare l'immagine:\n{ex}", parent=self)

    # ── Template ───────────────────────────────

    def _salva_template(self):
        try:
            dati = {
                'bg_image_path': self.bg_image_path,
                'elementi': [
                    {k: v for k, v in el.items() if not k.startswith('_')}
                    for el in self._elementi
                ],
            }
            with open(self.TEMPLATE_PATH, 'w', encoding='utf-8') as f:
                json.dump(dati, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Salvato",
                f"Template salvato in:\n{self.TEMPLATE_PATH}", parent=self)
        except Exception as ex:
            messagebox.showerror(T("dxc_errore"), str(ex), parent=self)

    def _carica_template(self, silent=False):
        if not os.path.exists(self.TEMPLATE_PATH):
            return
        try:
            with open(self.TEMPLATE_PATH, 'r', encoding='utf-8') as f:
                dati = json.load(f)
            # Azzera canvas
            for el in self._elementi:
                self.canvas.delete(el.get('_tag',''))
            self._elementi.clear()

            self.bg_image_path = dati.get('bg_image_path')
            if self.bg_image_path and os.path.exists(self.bg_image_path):
                self.lbl_bg.configure(text=os.path.basename(self.bg_image_path))
                self._aggiorna_bg_canvas()

            for i, ed in enumerate(dati.get('elementi', [])):
                tag = f"el_{i}_{ed.get('campo','x')}"
                el = {**ed, '_tag': tag, '_id': None}
                self._elementi.append(el)
                self._disegna_elemento(el)

            if not silent:
                messagebox.showinfo("Caricato", "Template caricato.", parent=self)
        except Exception as ex:
            if not silent:
                messagebox.showerror(T("dxc_errore"), str(ex), parent=self)

    # ── Generazione PDF ────────────────────────

    def _valore_campo(self, campo, qso):
        """Restituisce il valore del campo per un QSO."""
        if campo == '__static__':
            return None  # gestito separatamente
        if campo == 'my_call':
            return self.stazione
        if campo == 'my_gridsquare':
            return str(qso.get('my_gridsquare', '') or qso.get('my_locator', '')).upper()
        if campo == 'qso_date':
            d = str(qso.get('qso_date', ''))
            if len(d) == 8:
                return f"{d[6:8]}/{d[4:6]}/{d[0:4]}"
            return d
        if campo == 'time_on':
            t = str(qso.get('time_on', ''))
            if len(t) >= 4:
                return f"{t[:2]}:{t[2:4]} UTC"
            return t
        v = str(qso.get(campo, '')).strip()
        return v.upper() if campo in ('call','band','mode','country','gridsquare','my_gridsquare') else v

    def _genera_pdf(self):
        if not self._elementi:
            messagebox.showwarning("Attenzione",
                "Aggiungi almeno un campo alla card prima di generare il PDF.",
                parent=self)
            return

        qsos = self.qsos if self.var_qso_scope.get() == 'tutti' else self.qsos[:1]
        if not qsos:
            messagebox.showwarning("Attenzione", "Nessun QSO da stampare.", parent=self)
            return

        save_path = filedialog.asksaveasfilename(
            title=T("qcd_salva_pdf"),
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"{self.stazione}_QSL_cards.pdf",
            parent=self)
        if not save_path:
            return

        try:
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.lib.units import mm
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.colors import HexColor
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            CW = self.CARD_W * mm
            CH = self.CARD_H * mm
            layout = self.var_layout.get()

            if layout == '1per':
                # Una card per pagina — pagina = dimensione card
                c = rl_canvas.Canvas(save_path, pagesize=(CW, CH))
                for qso in qsos:
                    self._disegna_card_pdf(c, qso, 0, 0, CW, CH, mm)
                    c.showPage()
            else:
                # 4 per foglio A4 landscape (2 colonne × 2 righe)
                PW, PH = landscape(A4)
                c = rl_canvas.Canvas(save_path, pagesize=(PW, PH))
                # Margini per centrare 2×2 card su A4 landscape
                mg_x = (PW - 2 * CW) / 2
                mg_y = (PH - 2 * CH) / 2
                posizioni = [
                    (mg_x,        mg_y + CH),
                    (mg_x + CW,   mg_y + CH),
                    (mg_x,        mg_y),
                    (mg_x + CW,   mg_y),
                ]
                slot = 0
                for qso in qsos:
                    x0, y0 = posizioni[slot % 4]
                    self._disegna_card_pdf(c, qso, x0, y0, CW, CH, mm)
                    slot += 1
                    if slot % 4 == 0:
                        # Linee di taglio
                        c.setStrokeColorRGB(0.7, 0.7, 0.7)
                        c.setDash(4, 4)
                        c.line(mg_x + CW, 0, mg_x + CW, PH)
                        c.line(0, mg_y + CH, PW, mg_y + CH)
                        c.setDash()
                        c.showPage()

                # Ultima pagina incompleta
                if slot % 4 != 0:
                    c.setStrokeColorRGB(0.7, 0.7, 0.7)
                    c.setDash(4, 4)
                    c.line(mg_x + CW, 0, mg_x + CW, PH)
                    c.line(0, mg_y + CH, PW, mg_y + CH)
                    c.setDash()
                    c.showPage()

            c.save()
            messagebox.showinfo("PDF generato",
                f"PDF salvato con {len(qsos)} card{'s' if len(qsos)>1 else ''}.\n{save_path}",
                parent=self)
            if os.path.exists(save_path):
                try: os.startfile(save_path)
                except Exception: pass

        except Exception as ex:
            messagebox.showerror("Errore PDF", str(ex), parent=self)

    def _disegna_card_pdf(self, c, qso, x0, y0, CW, CH, mm):
        """Disegna una singola QSL card sul canvas ReportLab."""
        from reportlab.lib.colors import HexColor

        # Sfondo immagine
        if self.bg_image_path and os.path.exists(self.bg_image_path):
            try:
                from reportlab.lib.utils import ImageReader
                img_rl = ImageReader(self.bg_image_path)
                c.drawImage(img_rl, x0, y0, CW, CH, mask='auto')
            except Exception:
                pass
        else:
            # Sfondo bianco
            c.setFillColorRGB(1, 1, 1)
            c.rect(x0, y0, CW, CH, fill=1, stroke=0)

        # Bordo
        c.setStrokeColorRGB(0.17, 0.37, 0.69)
        c.setLineWidth(0.5)
        c.rect(x0, y0, CW, CH, fill=0, stroke=1)

        # Campi
        for el in self._elementi:
            campo = el['campo']
            if campo == '__static__':
                testo = el.get('testo_statico', '')
            else:
                testo = self._valore_campo(campo, qso)
            if not testo:
                continue

            # Posizione: origine in basso a sinistra in ReportLab
            x = x0 + el['x_mm'] * mm
            y = y0 + (self.CARD_H - el['y_mm']) * mm

            fs = max(6, el.get('font_size', 10))
            bold   = el.get('bold', False)
            italic = el.get('italic', False)
            if bold and italic:    fn = "Helvetica-BoldOblique"
            elif bold:             fn = "Helvetica-Bold"
            elif italic:           fn = "Helvetica-Oblique"
            else:                  fn = "Helvetica"

            try:
                col = HexColor(el.get('color', '#000000'))
            except Exception:
                col = HexColor('#000000')

            c.setFont(fn, fs)
            c.setFillColor(col)

            align = el.get('align', 'left')
            if align == 'center':
                c.drawCentredString(x, y, testo)
            elif align == 'right':
                c.drawRightString(x, y, testo)
            else:
                c.drawString(x, y, testo)


# ─────────────────────────────────────────────
#  Paesi con bureau QSL IARU attivo (fonte: iaru.org/reference/qsl-bureau-2/)
#  Aggiornato maggio 2023. I paesi CLOSED sono esclusi.
#  Il campo COUNTRY ADIF viene normalizzato uppercase per il confronto.
# ─────────────────────────────────────────────
_BUREAU_PAESI = {
    "MONACO","FIJI","TUNISIA","AZERBAIJAN","REPUBLIC OF GEORGIA","SRI LANKA",
    "ISRAEL","CYPRUS","TANZANIA","NIGERIA","WESTERN SAMOA","UGANDA","KENYA",
    "SENEGAL","JAMAICA","ALGERIA","BARBADOS","GUYANA","CROATIA","GHANA","MALTA",
    "ZAMBIA","KUWAIT","MALAYSIA","DEMOCRATIC REPUBLIC OF CONGO","SINGAPORE",
    "TRINIDAD & TOBAGO","TRINIDAD AND TOBAGO","OMAN","QATAR","PAKISTAN",
    "CHINA","TAIWAN","ANDORRA","MOZAMBIQUE","CHILE","CUBA","BOLIVIA",
    "PORTUGAL","URUGUAY","GERMANY","PHILIPPINES","BOSNIA & HERZEGOVINA",
    "BOSNIA-HERZEGOVINA","SPAIN","IRELAND","ARMENIA","LIBERIA","MOLDOVA",
    "ESTONIA","BELARUS","TAJIKISTAN","TURKMENISTAN","FRANCE","NEW CALEDONIA",
    "FRENCH POLYNESIA","UNITED KINGDOM","ENGLAND","SCOTLAND","WALES",
    "NORTHERN IRELAND","HUNGARY","SWITZERLAND","LIECHTENSTEIN","ECUADOR",
    "DOMINICAN REPUBLIC","COLOMBIA","REPUBLIC OF KOREA","SOUTH KOREA",
    "KOREA","PANAMA","HONDURAS","THAILAND","ITALY","DJIBOUTI","GRENADA",
    "DOMINICA","JAPAN","MONGOLIA","JORDAN","NORWAY","ARGENTINA","LUXEMBOURG",
    "LITHUANIA","BULGARIA","PERU","LEBANON","AUSTRIA","FINLAND",
    "CZECH REPUBLIC","SLOVAKIA","BELGIUM","DENMARK","FAROE ISLANDS","ARUBA",
    "NETHERLANDS","CURACAO","BRAZIL","RUSSIA","BANGLADESH","SLOVENIA",
    "SWEDEN","POLAND","GREECE","SAN MARINO","TURKEY","ICELAND","GUATEMALA",
    "COSTA RICA","GABON","COTE D'IVOIRE","IVORY COAST","MALI","UZBEKISTAN",
    "KAZAKHSTAN","UKRAINE","ANTIGUA & BARBUDA","NAMIBIA","BRUNEI","CANADA",
    "AUSTRALIA","BRITISH VIRGIN ISLANDS","TURKS & CAICOS ISLANDS","BERMUDA",
    "HONG KONG","INDIA","UNITED STATES","UNITED STATES OF AMERICA","USA",
    "INDONESIA","IRAQ","SYRIA","LATVIA","NICARAGUA","ROMANIA","EL SALVADOR",
    "SERBIA","VENEZUELA","NORTH MACEDONIA","KOSOVO","ALBANIA","GIBRALTAR",
    "SAINT HELENA","NEW ZEALAND","PARAGUAY","SOUTH AFRICA",
}

def _ha_bureau(qso):
    """True se il COUNTRY del QSO ha un bureau QSL IARU attivo."""
    country = str(qso.get('country', '')).upper().strip()
    return bool(country) and country in _BUREAU_PAESI


# ─────────────────────────────────────────────
#  QSL Card Dialog — formato etichetta 70x36mm
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
#  Dialogo Selezione QSO per stampa QSL
# ─────────────────────────────────────────────
class SelezioneQSODialog(ctk.CTkToplevel):
    def __init__(self, parent, qsos, stazione, colori_pdf):
        super().__init__(parent)
        self.title(T("qsl_seleziona"))
        self.geometry("960x600")
        self.resizable(True, True)
        self.minsize(1000, 750)
        self.grab_set()
        self.qsos       = qsos
        self.stazione   = stazione
        self.colori_pdf = colori_pdf
        self.app_ref    = parent
        self.var_checks = []   # BooleanVar per ogni riga
        self.risultato_qsos = None  # QSO selezionati da passare a QSLCardDialog

        self._build()

    def _build(self):
        import tkinter as tk
        import tkinter.ttk as ttk

        # Header
        ctk.CTkLabel(self, text=T("qsl_sel_header"),
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=8)

        # ── Filtri intelligenti QSL ────────────────────────────
        frame_flt = ctk.CTkFrame(self, fg_color="#141414", corner_radius=8)
        frame_flt.pack(fill="x", padx=15, pady=(0,4))

        ctk.CTkLabel(frame_flt, text="🎯 Filtri intelligenti — applica per preselezionare i QSO",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#90CDF4").pack(anchor="w", padx=10, pady=(6,2))

        row_f = ctk.CTkFrame(frame_flt, fg_color="transparent")
        row_f.pack(fill="x", padx=8, pady=(0,6))

        # Variabili filtro
        self.flt_escludi_lotw  = ctk.BooleanVar(value=False)
        self.flt_escludi_eqsl  = ctk.BooleanVar(value=False)
        self.flt_solo_vhf_sat  = ctk.BooleanVar(value=False)
        self.flt_escludi_digi  = ctk.BooleanVar(value=False)
        self.flt_solo_non_sent = ctk.BooleanVar(value=False)

        MODI_DIGI = {"FT8","FT4","JS8","WSPR","JT65","JT9","JT6M","FSK441",
                     "MSK144","Q65","VARA","OLIVIA","CONTESTIA","RTTY","PSK31",
                     "PSK63","MFSK","FREEDV","PACKET","APRS"}
        BANDE_VHF = {"6M","4M","2M","1.25M","70CM","33CM","23CM","13CM",
                     "9CM","6CM","3CM","1.25CM","6MM"}

        def _band_is_vhf(q):
            b = str(q.get("band","")).upper().strip()
            if b in BANDE_VHF: return True
            try: return float(str(q.get("freq","0")).strip()) >= 50.0
            except: return False

        def _is_digi(q):
            m = str(q.get("mode","")).upper().strip()
            s = str(q.get("submode","")).upper().strip()
            return m in MODI_DIGI or s in MODI_DIGI

        def _is_lotw(q):
            r = str(q.get("lotw_qsl_rcvd","")).upper().strip()
            d = str(q.get("lotw_qslrdate","")).strip()
            return r in ("Y","V") or (not r and d and d != "00000000")

        def _is_eqsl(q):
            r = str(q.get("eqsl_qsl_rcvd","")).upper().strip()
            d = str(q.get("eqsl_qslrdate","")).strip()
            return r == "Y" or (not r and d and d != "00000000")

        def _applica_filtri():
            n_prima = len(self._selected)
            nuova_sel = set()
            for i, qso in enumerate(self.qsos):
                if i not in self._selected:
                    continue
                if self.flt_escludi_lotw.get()  and _is_lotw(qso): continue
                if self.flt_escludi_eqsl.get()  and _is_eqsl(qso): continue
                if self.flt_solo_vhf_sat.get()  and not (_band_is_vhf(qso) or qso.get("sat_name","")): continue
                if self.flt_escludi_digi.get()  and _is_digi(qso): continue
                if self.flt_solo_non_sent.get() and str(qso.get("qsl_sent","")).upper().strip() == "Y": continue
                nuova_sel.add(i)
            self._selected = nuova_sel
            self._popola()
            rimasti = len(self._selected)
            esclusi = n_prima - rimasti
            self._aggiorna_count()
            if esclusi:
                messagebox.showinfo("Filtro applicato",
                    f"Filtro applicato sulla selezione corrente.\n\n"
                    f"QSO rimasti selezionati: {rimasti}\n"
                    f"QSO deselezionati dal filtro: {esclusi}",
                    parent=self)

        checks = [
            (self.flt_escludi_lotw,  "☑ Escludi confermati LoTW"),
            (self.flt_escludi_eqsl,  "☑ Escludi confermati eQSL"),
            (self.flt_escludi_digi,  "☑ Escludi modi digitali"),
            (self.flt_solo_vhf_sat,  "☑ Solo VHF/UHF/SAT"),
            (self.flt_solo_non_sent, "☑ Solo non ancora spediti"),
        ]
        for var, testo in checks:
            ctk.CTkCheckBox(row_f, text=testo, variable=var,
                             font=ctk.CTkFont(size=10), height=22
                             ).pack(side="left", padx=(0,14))

        ctk.CTkButton(row_f, text="▶ Applica filtri", height=26, width=120,
                      fg_color="#C05621", hover_color="#9C4221",
                      font=ctk.CTkFont(size=10, weight="bold"),
                      command=_applica_filtri).pack(side="left", padx=(8,0))

        ctk.CTkButton(row_f, text=T("etq_cerca_mgr"), height=26, width=170,
                      fg_color="#276749", hover_color="#2F855A",
                      font=ctk.CTkFont(size=10, weight="bold"),
                      command=self._cerca_manager_batch).pack(side="left", padx=(8,0))

        # Toolbar
        frame_tb = ctk.CTkFrame(self, fg_color="transparent")
        frame_tb.pack(fill="x", padx=15, pady=4)

        ctk.CTkButton(frame_tb, text=T("qsl_sel_tutti"), width=130, height=28,
                      fg_color="#2B6CB0", command=self._sel_tutti).pack(side="left", padx=(0,4))
        ctk.CTkButton(frame_tb, text=T("qsl_sel_nessuno"), width=130, height=28,
                      fg_color="#718096", command=self._sel_nessuno).pack(side="left", padx=4)
        ctk.CTkButton(frame_tb, text=T("qsl_sel_inverti"), width=130, height=28,
                      fg_color="#4A5568", command=self._inverti).pack(side="left", padx=4)
        ctk.CTkButton(frame_tb, text=T("qsl_sel_non_sent"), width=140, height=28,
                      fg_color="#276749", command=self._sel_non_sent).pack(side="left", padx=4)

        self.lbl_count = ctk.CTkLabel(frame_tb, text="",
                                       font=ctk.CTkFont(size=11), text_color="#48BB78")
        self.lbl_count.pack(side="right", padx=10)

        # Treeview con checkbox simulato
        frame_tree = ctk.CTkFrame(self)
        frame_tree.pack(fill="both", expand=True, padx=15, pady=4)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Sel.Treeview",
                        background="#0D0D0D", foreground="#E2E8F0",
                        rowheight=22, fieldbackground="#0D0D0D",
                        font=("Arial", 9))
        style.configure("Sel.Treeview.Heading",
                        background="#1A365D", foreground="white",
                        font=("Arial", 9, "bold"))
        style.map("Sel.Treeview",
                  background=[("selected", "#2B6CB0")],
                  foreground=[("selected", "white")])

        cols = ("✓", "Data", "UTC", "Callsign", "Banda", "Modo",
                "RST TX", "RST RX", "Country", "QSL_SENT")
        self.tree = ttk.Treeview(frame_tree, columns=cols,
                                  show="headings", style="Sel.Treeview")

        widths = {"✓": 30, "Data": 80, "UTC": 55, "Callsign": 90,
                  "Banda": 55, "Modo": 55, "RST TX": 55, "RST RX": 55,
                  "Country": 150, "QSL_SENT": 70}
        for col in cols:
            self.tree.heading(col, text=col,
                              command=lambda c=col: self._sort(c))
            self.tree.column(col, width=widths.get(col, 80), anchor="center")

        self.tree.tag_configure("selected",   background="#1A3A5C", foreground="#90CDF4")
        self.tree.tag_configure("unselected", background="#0D0D0D", foreground="#E2E8F0")
        self.tree.tag_configure("sent",       background="#0A2D1A", foreground="#9AE6B4")

        sb_v = ttk.Scrollbar(frame_tree, orient="vertical",   command=self.tree.yview)
        sb_h = ttk.Scrollbar(frame_tree, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb_v.pack(side="right", fill="y")
        sb_h.pack(side="bottom", fill="x")

        self.tree.bind("<Button-1>", self._toggle_check)
        self.tree.bind("<space>", self._toggle_check_selected)

        # Popola
        self._selected = set()  # indici QSO selezionati
        self._popola()

        # Pulsanti azione
        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(fill="x", padx=15, pady=8)
        ctk.CTkButton(frame_btn, text="🖨  " + T("qsl_sel_stampa"),
                      command=self._stampa,
                      fg_color="#4A5568", hover_color="#2D3748",
                      height=38, font=ctk.CTkFont(size=12, weight="bold")).pack(
                      side="left", expand=True, padx=(0,6), fill="x")
        ctk.CTkButton(frame_btn, text="☑  " + T("qsl_sel_usa"),
                      command=self._usa_come_filtro,
                      fg_color="#2B6CB0", hover_color="#1A365D",
                      height=38, font=ctk.CTkFont(size=12)).pack(
                      side="left", expand=True, padx=3, fill="x")
        ctk.CTkButton(frame_btn, text=T("chiudi"), command=self.destroy,
                      fg_color="#718096", height=38, width=100).pack(
                      side="right", padx=(6,0))

    def _popola(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, qso in enumerate(self.qsos):
            data = str(qso.get("qso_date",""))
            if len(data)==8: data=f"{data[6:8]}/{data[4:6]}/{data[0:4]}"
            utc = str(qso.get("time_on",""))
            if len(utc)>=4: utc=f"{utc[0:2]}:{utc[2:4]}"
            sent = str(qso.get("qsl_sent","")).upper().strip()
            sel = idx in self._selected
            tag = "sent" if sent=="Y" else ("selected" if sel else "unselected")
            self.tree.insert("", "end", iid=str(idx), values=(
                "☑" if sel else "☐",
                data, utc,
                str(qso.get("call","")).upper(),
                str(qso.get("band","")).upper(),
                str(qso.get("mode","")).upper(),
                str(qso.get("rst_sent","")),
                str(qso.get("rst_rcvd","")),
                str(qso.get("country","")).upper(),
                sent if sent else "-",
            ), tags=(tag,))
        self._aggiorna_count()

    def _toggle_check(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        idx = int(item)
        if idx in self._selected:
            self._selected.discard(idx)
        else:
            self._selected.add(idx)
        self._aggiorna_riga(idx)
        self._aggiorna_count()

    def _toggle_check_selected(self, event):
        for item in self.tree.selection():
            idx = int(item)
            if idx in self._selected:
                self._selected.discard(idx)
            else:
                self._selected.add(idx)
            self._aggiorna_riga(idx)
        self._aggiorna_count()

    def _aggiorna_riga(self, idx):
        qso = self.qsos[idx]
        sent = str(qso.get("qsl_sent","")).upper().strip()
        sel = idx in self._selected
        tag = "sent" if sent=="Y" else ("selected" if sel else "unselected")
        vals = list(self.tree.item(str(idx), "values"))
        vals[0] = "☑" if sel else "☐"
        self.tree.item(str(idx), values=vals, tags=(tag,))

    def _aggiorna_count(self):
        n = len(self._selected)
        tot = len(self.qsos)
        self.lbl_count.configure(text=T("qsl_sel_count", n=n, tot=tot))

    def _sel_tutti(self):
        self._selected = set(range(len(self.qsos)))
        self._popola()

    def _sel_nessuno(self):
        self._selected = set()
        self._popola()

    def _inverti(self):
        tutti = set(range(len(self.qsos)))
        self._selected = tutti - self._selected
        self._popola()

    def _reset_qsl_sent(self):
        if not messagebox.askyesno("Reset QSL_SENT",
            "Azzera QSL_SENT=Y in memoria per tutti i QSO?\n\n"
            "Il file su disco NON viene modificato."):
            return
        n = sum(1 for q in self.qsos_tutti
                if str(q.get('qsl_sent','')).upper().strip() == 'Y')
        for q in self.qsos_tutti:
            if str(q.get('qsl_sent','')).upper().strip() == 'Y':
                q['qsl_sent'] = 'N'
        self._modifiche_pendenti = False
        self._aggiorna_lbl_memoria()
        self._aggiorna_count()
        self._popola()
        messagebox.showinfo("Reset", f"QSL_SENT azzerato in memoria per {n} QSO.")

    def _sel_non_sent(self):
        self._selected = set(
            i for i, q in enumerate(self.qsos)
            if str(q.get("qsl_sent","")).upper().strip() != "Y"
        )
        self._popola()

    def _sort(self, col):
        pass  # ordinamento futuro


    # ── Ricerca QSL Manager batch su IK3QAR ─────────────────────

    def _cerca_manager_batch(self):
        """Interroga IK3QAR
        per tutti i QSO selezionati privi di QSL_VIA."""
        import threading as _threading
        import tkinter as _tk
        import tkinter.ttk as _ttk

        # QSO selezionati senza QSL_VIA già popolato
        qsos_da_cercare = [
            (i, self.qsos[i])
            for i in sorted(self._selected)
            if not str(self.qsos[i].get("qsl_via", "")).strip()
        ]
        if not qsos_da_cercare:
            messagebox.showinfo("Info",
                "Nessun QSO selezionato senza QSL_VIA già compilato.",
                parent=self)
            return

        # Deduplica per callsign — cerchiamo ogni call una volta sola
        call_a_idx = {}  # call -> lista di indici qso
        for idx, qso in qsos_da_cercare:
            call = str(qso.get("call", "")).upper().strip()
            if call:
                call_a_idx.setdefault(call, []).append(idx)

        calls_unici = list(call_a_idx.keys())
        n_tot = len(calls_unici)
        if n_tot == 0:
            messagebox.showwarning("Attenzione",
                "Nessun callsign valido trovato nei QSO selezionati.", parent=self)
            return

        # Progress dialog
        prog = ctk.CTkToplevel(self)
        prog.title("Ricerca QSL Manager IK3QAR…")
        prog.geometry("440x180")
        prog.resizable(False, False)
        prog.grab_set()
        ctk.CTkLabel(prog, text="🔍 Interrogo IK3QAR…",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(16,4))
        lbl_prog = ctk.CTkLabel(prog, text="", font=ctk.CTkFont(size=10), text_color="gray")
        lbl_prog.pack()
        bar = ctk.CTkProgressBar(prog, width=380)
        bar.pack(pady=(8,4))
        bar.set(0)
        lbl_n = ctk.CTkLabel(prog, text=f"0 / {n_tot}", font=ctk.CTkFont(size=10))
        lbl_n.pack()

        # Risultati condivisi
        risultati = {}   # call -> (manager, anno, info) o None
        _stop = [False]
        _done = [False]

        def _fetch_thread():
            # Loop IK3QAR
            for i, call in enumerate(calls_unici):
                if _stop[0]:
                    break
                url = (f"https://www.ik3qar.it/manager/man_result.php"
                       f"?call={urllib.parse.quote(call)}")
                trovato_ik3qar = None
                try:
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "ADIF-FZR/2.3"})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        html = resp.read().decode("iso-8859-1", errors="replace")
                    righe = re.findall(
                        r'<td[^>]*>\s*(?:<[^>]+>)*([A-Z0-9/]+)(?:</[^>]+>)*\s*</td>'
                        r'\s*<td[^>]*>\s*(?:<[^>]+>)*([A-Z0-9/]+)(?:</[^>]+>)*\s*</td>'
                        r'\s*<td[^>]*>\s*(\d{4})\s*</td>'
                        r'\s*<td[^>]*>\s*(.*?)\s*</td>',
                        html, re.IGNORECASE | re.DOTALL)
                    trovati = [(m, y, re.sub('<[^>]+>', '', info).strip())
                               for c, m, y, info in righe if c.upper() == call]
                    trovato_ik3qar = trovati[-1] if trovati else None
                except Exception:
                    pass

                if trovato_ik3qar:
                    risultati[call] = trovato_ik3qar
                else:
                    risultati[call] = None

                def _upd(i=i, call=call):
                    if prog.winfo_exists():
                        bar.set((i+1)/n_tot)
                        lbl_n.configure(text=f"{i+1} / {n_tot}")
                        lbl_prog.configure(text=f"{call}…")
                prog.after(0, _upd)
                import time as _time
                _time.sleep(0.25)

            _done[0] = True
            def _finish():
                if prog.winfo_exists():
                    prog.destroy()
                self._mostra_risultati_manager(risultati, call_a_idx)
            prog.after(0, _finish)

        ctk.CTkButton(prog, text=T("cm_annulla"), height=28, fg_color="#718096",
                      command=lambda: _stop.__setitem__(0, True)).pack(pady=4)

        _threading.Thread(target=_fetch_thread, daemon=True).start()

    def _mostra_risultati_manager(self, risultati, call_a_idx):
        """Mostra tabella di revisione risultati IK3QAR e aggiorna QSL_VIA in blocco."""
        import tkinter as _tk
        import tkinter.ttk as _ttk

        trovati = {c: r for c, r in risultati.items() if r is not None}
        if not trovati:
            messagebox.showinfo("Risultato",
                "Nessun manager trovato nel database IK3QAR per i QSO selezionati.",
                parent=self)
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Risultati IK3QAR — {len(trovati)} manager trovati")
        dlg.geometry("760x480")
        dlg.resizable(True, True)
        dlg.grab_set(); dlg.lift(); dlg.focus_force()

        ctk.CTkLabel(dlg, text=f"🔍 {len(trovati)} manager trovati su {len(risultati)} callsign cercati",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12,4), padx=16)
        ctk.CTkLabel(dlg, text=T("etq_spunta_righe"),
                     font=ctk.CTkFont(size=10), text_color="gray").pack(pady=(0,8))

        frame_t = ctk.CTkFrame(dlg)
        frame_t.pack(fill="both", expand=True, padx=12, pady=(0,6))

        style = _ttk.Style()
        style.theme_use("default")
        style.configure("Mgr.Treeview",
            background="#0D0D0D", foreground="#E2E8F0",
            rowheight=24, fieldbackground="#0D0D0D", font=("Arial",9))
        style.configure("Mgr.Treeview.Heading",
            background="#1A365D", foreground="white", font=("Arial",9,"bold"))

        cols = ("sel", "call", "manager", "anno", "n_qso", "info")
        tv = _ttk.Treeview(frame_t, columns=cols, show="headings", style="Mgr.Treeview")
        tv.heading("sel",     text="✔")
        tv.heading("call",    text=T("cm_callsign_dx"))
        tv.heading("manager", text=T("cm_qsl_manager"))
        tv.heading("anno",    text=T("cm_anno"))
        tv.heading("n_qso",   text=T("cm_n_qso"))
        tv.heading("info",    text=T("cm_note"))
        tv.column("sel",      width=30,  stretch=False)
        tv.column("call",     width=120, stretch=False)
        tv.column("manager",  width=120, stretch=False)
        tv.column("anno",     width=55,  stretch=False)
        tv.column("n_qso",    width=55,  stretch=False)
        tv.column("info",     width=310)

        sb = _ttk.Scrollbar(frame_t, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        vars_sel = {}
        iid_to_call = {}

        for call, risultato in trovati.items():
            manager, anno, info = risultato
            n_qso = len(call_a_idx.get(call, []))
            iid = tv.insert("", "end",
                values=("☑", call, manager, anno, n_qso, info))
            vars_sel[iid] = True
            iid_to_call[iid] = (call, manager)

        def _toggle(event):
            row = tv.identify_row(event.y)
            col = tv.identify_column(event.x)
            if row and col == "#1":
                vars_sel[row] = not vars_sel[row]
                vals = list(tv.item(row, "values"))
                vals[0] = "☑" if vars_sel[row] else "☐"
                tv.item(row, values=vals)

        tv.bind("<Button-1>", _toggle)

        # Pulsanti
        frame_btn = ctk.CTkFrame(dlg, fg_color="transparent")
        frame_btn.pack(fill="x", padx=12, pady=(0,12))

        def _sel_tutti():
            for iid in vars_sel:
                vars_sel[iid] = True
                vals = list(tv.item(iid, "values"))
                vals[0] = "☑"; tv.item(iid, values=vals)
        def _sel_nessuno():
            for iid in vars_sel:
                vars_sel[iid] = False
                vals = list(tv.item(iid, "values"))
                vals[0] = "☐"; tv.item(iid, values=vals)

        ctk.CTkButton(frame_btn, text="☑ Tutti", width=70, height=30,
                      fg_color="#4A5568", command=_sel_tutti).pack(side="left", padx=(0,4))
        ctk.CTkButton(frame_btn, text="☐ Nessuno", width=80, height=30,
                      fg_color="#4A5568", command=_sel_nessuno).pack(side="left", padx=(0,12))

        def _applica():
            n_agg = 0
            for iid, selezionato in vars_sel.items():
                if not selezionato:
                    continue
                call, manager = iid_to_call[iid]
                for idx in call_a_idx.get(call, []):
                    self.qsos[idx]["qsl_via"] = manager.upper()
                    n_agg += 1
            # Aggiorna anche il log nel main app se disponibile
            try:
                self.app_ref._aggiorna_tree()
            except Exception:
                pass
            self._popola()
            dlg.destroy()
            messagebox.showinfo("Aggiornamento completato",
                f"QSL_VIA aggiornato su {n_agg} QSO nel log.\n\n"
                f"Ricorda di salvare il file ADIF per rendere permanente la modifica.",
                parent=self)

        ctk.CTkButton(frame_btn, text=f"✔ Applica selezionati ({len(trovati)} call)",
                      command=_applica, height=34,
                      fg_color="#276749", hover_color="#2F855A",
                      font=ctk.CTkFont(size=11, weight="bold")).pack(
                      side="left", expand=True, fill="x", padx=(0,6))
        ctk.CTkButton(frame_btn, text=T("cm_annulla"), width=80, height=34,
                      fg_color="#718096", command=dlg.destroy).pack(side="left")

    def _qso_selezionati(self):
        return [self.qsos[i] for i in sorted(self._selected)]

    def _stampa(self):
        qsos_sel = self._qso_selezionati()
        if not qsos_sel:
            messagebox.showwarning(T("attenzione"), T("qsl_sel_nessuno_sel"))
            return
        self.risultato_qsos = qsos_sel
        self.destroy()
        # Apri direttamente QSLCardDialog con i QSO selezionati
        dlg = QSLCardDialog(self.app_ref, qsos_sel, self.stazione, self.colori_pdf)

    def _usa_come_filtro(self):
        qsos_sel = self._qso_selezionati()
        if not qsos_sel:
            messagebox.showwarning(T("attenzione"), T("qsl_sel_nessuno_sel"))
            return
        self.risultato_qsos = qsos_sel
        self.destroy()
        # Apri QSLCardDialog con i QSO selezionati come base
        dlg = QSLCardDialog(self.app_ref, qsos_sel, self.stazione, self.colori_pdf)

    def destroy(self):
        try:
            _ripristina_tema_ttk()
        except Exception:
            pass
        super().destroy()


# ─────────────────────────────────────────────
#  QSLMasterDialog — Finestra unica QSL
#  Filtri + Selezione manuale + Stampa
# ─────────────────────────────────────────────
class QSLMasterDialog(ctk.CTkToplevel):
    FORMATI = {
        "Personalizzato  51x27mm  — 4x11 = 44/A4":   (51.0, 27.0, 4, 11, 3.0,  0.0, 0.0, 0.0, "A4"),
        "Personalizzato  70x36mm  — 3x8 = 24/A4":    (70.0, 36.0, 3, 8,  5.0, 11.0, 0.0, 0.0, "A4"),
        "Avery L7159     63.5x33.9mm — 3x8 = 24/A4": (63.5, 33.9, 3, 8,  7.2, 13.5, 2.5, 0.0, "A4"),
        "Avery L7160     63.5x38.1mm — 3x7 = 21/A4": (63.5, 38.1, 3, 7,  7.2, 15.1, 2.5, 0.0, "A4"),
        "Avery L7163     99.1x38.1mm — 2x7 = 14/A4": (99.1, 38.1, 2, 7,  4.7, 15.1, 2.5, 0.0, "A4"),
        "Avery 5160      66.7x25.4mm — 3x10 = 30/Letter": (66.7, 25.4, 3, 10, 4.8, 12.7, 3.2, 0.0, "LETTER"),
    }
    DEFAULT_FORMATO = "Personalizzato  70x36mm  — 3x8 = 24/A4"

    def __init__(self, parent, qsos, stazione, colori_pdf):
        super().__init__(parent)
        self.title(T("qsl_card"))
        self.geometry("1000x700")
        self.resizable(True, True)
        self.minsize(900, 550)
        self.grab_set()
        self.qsos_tutti   = qsos
        self.stazione     = stazione
        self.colori_pdf   = colori_pdf
        self.app_ref      = parent
        self._selected    = set()  # nessuno selezionato per default
        self._modifiche_pendenti = False

        # Variabili
        self.var_formato     = ctk.StringVar(value=self.DEFAULT_FORMATO)
        self.var_margin_top  = ctk.StringVar(value="11.0")
        self.var_margin_left = ctk.StringVar(value="5.0")
        self.var_gap_v       = ctk.StringVar(value="0.0")
        self.var_border      = ctk.BooleanVar(value=True)
        self.var_lotw        = ctk.BooleanVar(value=True)
        self.var_country     = ctk.BooleanVar(value=True)

        # Memoria
        self.memoria_path = os.path.join(os.path.expanduser("~"), ".adif_qsl_memoria.json")
        self.memoria_per_prefisso = self._carica_memoria()
        self.lbl_memoria = None

        self._build()

    def _build(self):
        import tkinter.ttk as ttk

        # ── AREA SUPERIORE: filtri e opzioni ────────────────
        frame_top = ctk.CTkFrame(self)
        frame_top.pack(fill="x", padx=10, pady=6)

        # Colonna sinistra — filtri
        frame_filtri = ctk.CTkFrame(frame_top)
        frame_filtri.pack(side="left", fill="both", expand=True, padx=(0,6))

        ctk.CTkLabel(frame_filtri, text=T("cm_filtri"),
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=6, sticky="w", padx=8, pady=4)

        # Date
        date_valide = sorted([str(q.get('qso_date','')).strip()
                               for q in self.qsos_tutti
                               if len(str(q.get('qso_date','')).strip())==8])
        data_min = date_valide[0]  if date_valide else "19000101"
        data_max = date_valide[-1] if date_valide else "29991231"
        def fmt(d): return f"{d[6:8]}/{d[4:6]}/{d[0:4]}" if len(d)==8 else ""

        ctk.CTkLabel(frame_filtri, text=T("filtri_da")).grid(row=1, column=0, padx=8, sticky="e")
        self.entry_da = ctk.CTkEntry(frame_filtri, width=95)
        self.entry_da.insert(0, fmt(data_min))
        self.entry_da.grid(row=1, column=1, padx=4)
        ctk.CTkButton(frame_filtri, text="📅", width=26, height=26, fg_color="#2B6CB0",
                      command=lambda: CalendarPopup(self, self.entry_da)).grid(row=1, column=2, padx=2)

        ctk.CTkLabel(frame_filtri, text=T("filtri_a")).grid(row=1, column=3, padx=8, sticky="e")
        self.entry_a = ctk.CTkEntry(frame_filtri, width=95)
        self.entry_a.insert(0, fmt(data_max))
        self.entry_a.grid(row=1, column=4, padx=4)
        ctk.CTkButton(frame_filtri, text="📅", width=26, height=26, fg_color="#2B6CB0",
                      command=lambda: CalendarPopup(self, self.entry_a)).grid(row=1, column=5, padx=2)

        # Callsign
        ctk.CTkLabel(frame_filtri, text=T("cm_call_lbl")).grid(row=2, column=0, padx=8, pady=4, sticky="e")
        self.entry_call = ctk.CTkEntry(frame_filtri, placeholder_text=T("cm_ph_ik1"), width=95)
        self.entry_call.grid(row=2, column=1, padx=4)
        ctk.CTkButton(frame_filtri, text=T("applica_btn"), width=80, height=26,
                      fg_color="#2B6CB0",
                      command=self._applica_filtri).grid(row=2, column=2, columnspan=2, padx=4)
        ctk.CTkButton(frame_filtri, text=T("reset_btn"), width=60, height=26,
                      fg_color="#718096",
                      command=self._reset_filtri).grid(row=2, column=4, padx=4)

        # ── Filtri intelligenti ───────────────────────────────
        frame_smart = ctk.CTkFrame(self, fg_color="#141414", corner_radius=6)
        frame_smart.pack(fill="x", padx=15, pady=(0,4))
        ctk.CTkLabel(frame_smart, text="🎯 Filtri intelligenti:",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#90CDF4").pack(side="left", padx=(10,8), pady=4)

        self.flt_escludi_lotw  = ctk.BooleanVar(value=False)
        self.flt_escludi_eqsl  = ctk.BooleanVar(value=False)
        self.flt_solo_vhf_sat  = ctk.BooleanVar(value=False)
        self.flt_escludi_digi  = ctk.BooleanVar(value=False)
        self.flt_solo_non_sent = ctk.BooleanVar(value=False)

        MODI_DIGI = {"FT8","FT4","JS8","WSPR","JT65","JT9","JT6M","FSK441",
                     "MSK144","Q65","VARA","OLIVIA","CONTESTIA","RTTY","PSK31",
                     "PSK63","MFSK","FREEDV","PACKET","APRS"}
        BANDE_VHF = {"6M","4M","2M","1.25M","70CM","33CM","23CM","13CM",
                     "9CM","6CM","3CM","1.25CM","6MM"}

        def _band_is_vhf(q):
            b = str(q.get("band","")).upper().strip()
            if b in BANDE_VHF: return True
            try: return float(str(q.get("freq","0")).strip()) >= 50.0
            except: return False

        def _is_digi(q):
            m = str(q.get("mode","")).upper().strip()
            s = str(q.get("submode","")).upper().strip()
            return m in MODI_DIGI or s in MODI_DIGI

        def _is_lotw(q):
            r = str(q.get("lotw_qsl_rcvd","")).upper().strip()
            d = str(q.get("lotw_qslrdate","")).strip()
            return r in ("Y","V") or (not r and d and d != "00000000")

        def _is_eqsl(q):
            r = str(q.get("eqsl_qsl_rcvd","")).upper().strip()
            d = str(q.get("eqsl_qslrdate","")).strip()
            return r == "Y" or (not r and d and d != "00000000")

        def _applica_smart():
            # Applica prima i filtri data/call normali
            self._applica_filtri()
            # Poi deseleziona dalla _selected i QSO che non passano i filtri smart
            nuova = set()
            for i in sorted(self._selected):
                if i >= len(self.qsos_tutti):
                    continue
                qso = self.qsos_tutti[i]
                if self.flt_escludi_lotw.get()  and _is_lotw(qso): continue
                if self.flt_escludi_eqsl.get()  and _is_eqsl(qso): continue
                if self.flt_solo_vhf_sat.get()  and not (_band_is_vhf(qso) or qso.get("sat_name","")): continue
                if self.flt_escludi_digi.get()  and _is_digi(qso): continue
                if self.flt_solo_non_sent.get() and str(qso.get("qsl_sent","")).upper().strip() == "Y": continue
                nuova.add(i)
            rimossi = len(self._selected) - len(nuova)
            self._selected = nuova
            # Ridisegna la treeview (metodo nativo di QSLMasterDialog)
            self._popola()
            self._aggiorna_count()
            if rimossi:
                messagebox.showinfo("Filtro applicato",
                    f"Filtro intelligente applicato.\n{rimossi} QSO deselezionati.",
                    parent=self)

        for var, testo in [
            (self.flt_escludi_lotw,  "- LoTW"),
            (self.flt_escludi_eqsl,  "- eQSL"),
            (self.flt_escludi_digi,  "- Digitale"),
            (self.flt_solo_vhf_sat,  "Solo VHF/SAT"),
            (self.flt_solo_non_sent, "Non spediti"),
        ]:
            ctk.CTkCheckBox(frame_smart, text=testo, variable=var,
                             font=ctk.CTkFont(size=9), height=20,
                             checkbox_width=14, checkbox_height=14
                             ).pack(side="left", padx=(0,10))

        ctk.CTkButton(frame_smart, text="▶ Applica", height=24, width=80,
                      fg_color="#C05621", hover_color="#9C4221",
                      font=ctk.CTkFont(size=9, weight="bold"),
                      command=_applica_smart).pack(side="left", padx=(4,0))

        # Colonna destra — formato + opzioni
        frame_opt = ctk.CTkFrame(frame_top)
        frame_opt.pack(side="left", fill="both", padx=(6,0))

        ctk.CTkLabel(frame_opt, text=T("qsl_formato_opt"),
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=4, sticky="w", padx=8, pady=4)

        ctk.CTkLabel(frame_opt, text=T("qsl_formato_lbl")).grid(row=1, column=0, padx=8, sticky="e")
        self._menu_formato = ctk.CTkOptionMenu(frame_opt, variable=self.var_formato,
                          values=list(self.FORMATI.keys()) + ["▶ Formato personalizzato…"],
                          command=self._on_formato_cambiato,
                          width=280)
        self._menu_formato.grid(row=1, column=1, columnspan=3, padx=4, pady=2, sticky="w")

        ctk.CTkLabel(frame_opt, text=T("etq_top_mm")).grid(row=2, column=0, padx=8, pady=3, sticky="e")
        ctk.CTkEntry(frame_opt, textvariable=self.var_margin_top, width=50, justify="center").grid(row=2, column=1, padx=4)
        ctk.CTkLabel(frame_opt, text=T("etq_sin_mm")).grid(row=2, column=2, padx=4, sticky="e")
        ctk.CTkEntry(frame_opt, textvariable=self.var_margin_left, width=50, justify="center").grid(row=2, column=3, padx=4)

        ctk.CTkCheckBox(frame_opt, text=T("etq_bordo"), variable=self.var_border).grid(row=3, column=0, padx=8, pady=2, sticky="w")
        self.var_raggruppa = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(frame_opt, text=T("qsl_raggruppa"),
                        variable=self.var_raggruppa).grid(row=4, column=0, columnspan=2, padx=8, pady=2, sticky="w")
        self.var_colori_etichetta = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(frame_opt, text=T("etq_etich_colori"),
                        variable=self.var_colori_etichetta).grid(row=4, column=2, columnspan=2, padx=8, pady=2, sticky="w")
        ctk.CTkCheckBox(frame_opt, text=T("etq_lotw_eqsl"), variable=self.var_lotw).grid(row=3, column=1, padx=4, sticky="w")
        ctk.CTkCheckBox(frame_opt, text=T("etq_country"), variable=self.var_country).grid(row=3, column=2, padx=4, sticky="w")

        # ── TOOLBAR SELEZIONE ────────────────────────────────
        frame_tb = ctk.CTkFrame(self, fg_color="transparent")
        frame_tb.pack(fill="x", padx=10, pady=2)

        ctk.CTkButton(frame_tb, text=T("qsl_sel_tutti_btn"),    width=120, height=26,
                      fg_color="#2B6CB0", command=self._sel_tutti).pack(side="left", padx=2)
        ctk.CTkButton(frame_tb, text=T("qsl_desel_tutti"),  width=130, height=26,
                      fg_color="#718096", command=self._sel_nessuno).pack(side="left", padx=2)
        ctk.CTkButton(frame_tb, text=T("etq_inverti"),            width=80,  height=26,
                      fg_color="#4A5568", command=self._inverti).pack(side="left", padx=2)
        ctk.CTkButton(frame_tb, text=T("etq_solo_non_inv"),   width=140, height=26,
                      fg_color="#276749", command=self._sel_non_sent).pack(side="left", padx=2)
        ctk.CTkButton(frame_tb, text=T("qsl_reset_sent"), width=130, height=26,
                      fg_color="#C05621", hover_color="#9C4221",
                      command=self._reset_qsl_sent).pack(side="left", padx=2)

        self.lbl_count = ctk.CTkLabel(frame_tb, text="",
                                       font=ctk.CTkFont(size=11), text_color="#48BB78")
        self.lbl_count.pack(side="left", padx=10)

        self.lbl_memoria = ctk.CTkLabel(frame_tb, text="",
                                         font=ctk.CTkFont(size=10), text_color="gray")
        self.lbl_memoria.pack(side="right", padx=10)
        self._aggiorna_lbl_memoria()

        # ── TABELLA QSO ──────────────────────────────────────
        frame_tree = ctk.CTkFrame(self)
        frame_tree.pack(fill="both", expand=True, padx=10, pady=4)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("QSL.Treeview",
                        background="#0D0D0D", foreground="#E2E8F0",
                        rowheight=22, fieldbackground="#0D0D0D",
                        font=("Arial", 9))
        style.configure("QSL.Treeview.Heading",
                        background="#1A365D", foreground="white",
                        font=("Arial", 9, "bold"))
        style.map("QSL.Treeview",
                  background=[("selected", "#2B6CB0")],
                  foreground=[("selected", "white")])

        cols = ("☑", "Data", "UTC", "Callsign", "Banda", "Modo",
                "RST TX", "RST RX", "Country", "QSL_SENT")
        self.tree = ttk.Treeview(frame_tree, columns=cols,
                                  show="headings", style="QSL.Treeview")
        widths = {"☑":30,"Data":80,"UTC":55,"Callsign":90,"Banda":55,
                  "Modo":55,"RST TX":50,"RST RX":50,"Country":160,"QSL_SENT":65}
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=widths.get(col,70), anchor="center")

        self.tree.tag_configure("sel",    background="#1A4A1A", foreground="#90EE90")  # verde = in coda stampa
        self.tree.tag_configure("unsel",  background="#F7F7F7", foreground="#1A202C")  # bianco = da stampare
        self.tree.tag_configure("sent",   background="#A0A0A0", foreground="#404040")  # grigio = già stampato
        self.tree.tag_configure("selY",   background="#2D6A1F", foreground="#FFFFFF")  # verde scuro = in coda+già inviato

        sb_v = ttk.Scrollbar(frame_tree, orient="vertical",   command=self.tree.yview)
        sb_h = ttk.Scrollbar(frame_tree, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb_v.pack(side="right",  fill="y")
        sb_h.pack(side="bottom", fill="x")

        self.tree.bind("<Button-1>", self._toggle_click)
        self.tree.bind("<Shift-Button-1>", self._shift_click)
        self.tree.bind("<Control-Button-1>", self._toggle_click)
        self._last_clicked_idx = None

        self._qso_filtrati = list(self.qsos_tutti)
        self._idx_map = {id(q): i for i, q in enumerate(self.qsos_tutti)}
        self._popola()

        # ── PULSANTI FISSI IN FONDO ──────────────────────────
        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(fill="x", padx=10, pady=6)

        self.entry_msg = ctk.CTkEntry(frame_btn,
                                       placeholder_text=T("etq_msg_ph"),
                                       width=200)
        self.entry_msg.pack(side="left", padx=(0,8))

        # Offset: da quale posizione iniziare sul foglio (1 = prima etichetta)
        ctk.CTkLabel(frame_btn, text=T("etq_da_pos"), font=ctk.CTkFont(size=10),
                     text_color="gray").pack(side="left", padx=(0,2))
        self.var_offset = ctk.StringVar(value="1")
        self.spin_offset = ctk.CTkEntry(frame_btn, textvariable=self.var_offset,
                                         width=38, justify="center",
                                         font=ctk.CTkFont(size=11))
        self.spin_offset.pack(side="left", padx=(0,8))

        ctk.CTkButton(frame_btn, text=T("etq_manager"),
                      command=self._cerca_manager_selezionati,
                      fg_color="#2B6CB0", hover_color="#1A365D",
                      height=36, width=110,
                      font=ctk.CTkFont(size=11)).pack(side="left", padx=(0,6))
        ctk.CTkButton(frame_btn, text=T("etq_genera"),
                      command=self._genera,
                      fg_color="#4A5568", hover_color="#2D3748",
                      height=36, font=ctk.CTkFont(size=12, weight="bold")).pack(
                      side="left", expand=True, padx=(0,6), fill="x")
        ctk.CTkButton(frame_btn, text=T("etq_aggiorna_sent"),
                      command=self._aggiorna_sent,
                      fg_color="#276749", hover_color="#2F855A",
                      height=36).pack(side="left", padx=(0,6))
        ctk.CTkButton(frame_btn, text=T("chiudi"), command=self._chiudi,
                      fg_color="#718096", height=36, width=80).pack(side="right")

    # ── Filtri ────────────────────────────────────────
    def _parse_data(self, testo):
        testo = testo.strip()
        if not testo: return None
        for f in ("%d/%m/%Y", "%Y%m%d"):
            try: return datetime.strptime(testo, f)
            except: pass
        return None

    def _applica_filtri(self):
        da   = self._parse_data(self.entry_da.get())
        a    = self._parse_data(self.entry_a.get())
        call = self.entry_call.get().strip().upper()
        self._qso_filtrati = []
        for q in self.qsos_tutti:
            d_raw = str(q.get('qso_date','')).strip()
            d_qso = datetime.strptime(d_raw,"%Y%m%d") if len(d_raw)==8 else None
            if da and d_qso and d_qso < da: continue
            if a  and d_qso and d_qso > a:  continue
            if call:
                qcall = str(q.get('call','')).upper().strip()
                if not qcall.startswith(call.rstrip('*')): continue
            self._qso_filtrati.append(q)
        self._popola()

    def _reset_filtri(self):
        self._qso_filtrati = list(self.qsos_tutti)
        self._idx_map = {id(q): i for i, q in enumerate(self.qsos_tutti)}
        self._popola()

    # ── Selezione ─────────────────────────────────────
    def _popola(self):
        self.tree.configure(selectmode="none")  # blocca eventi durante insert
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, qso in enumerate(self._qso_filtrati):
            data = str(qso.get("qso_date",""))
            if len(data)==8: data=f"{data[6:8]}/{data[4:6]}/{data[0:4]}"
            utc  = str(qso.get("time_on",""))
            if len(utc)>=4: utc=f"{utc[0:2]}:{utc[2:4]}"
            sent = str(qso.get("qsl_sent","")).upper().strip()
            orig_idx = self._idx_map.get(id(qso), 0)
            sel = orig_idx in self._selected
            if sent=="Y":
                tag = "selY" if sel else "sent"
            else:
                tag = "sel" if sel else "unsel"
            self.tree.insert("", "end", iid=str(orig_idx), values=(
                "☑" if sel else "☐",
                data, utc,
                str(qso.get("call","")).upper(),
                str(qso.get("band","")).upper(),
                str(qso.get("mode","")).upper(),
                str(qso.get("rst_sent","")),
                str(qso.get("rst_rcvd","")),
                str(qso.get("country","")).upper(),
                sent if sent else "-",
            ), tags=(tag,))
        self.tree.configure(selectmode="browse")  # riabilita eventi
        self._aggiorna_count()

    def _toggle_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item: return
        idx = int(item)
        self._last_clicked_idx = idx
        qso  = self.qsos_tutti[idx]
        sent = str(qso.get("qsl_sent","")).upper().strip()

        if idx in self._selected:
            self._selected.discard(idx)
        else:
            if sent == "Y":
                call = str(qso.get("call","")).upper().strip()
                data = str(qso.get("qso_date",""))
                if len(data)==8:
                    data = data[6:8]+"/"+data[4:6]+"/"+data[0:4]
                gia = sum(1 for i in self._selected
                          if str(self.qsos_tutti[i].get("qsl_sent","")).upper().strip()=="Y")
                riga1 = "Attenzione!"
                riga2 = "Il QSO con " + call + " del " + data + " e' gia' stampato (QSL_SENT=Y)."
                riga3 = "Nella selezione corrente ci sono gia' " + str(gia) + " QSL gia' stampate."
                riga4 = "Vuoi aggiungerlo comunque alla coda di stampa?"
                msg = riga1 + "\n\n" + riga2 + "\n" + riga3 + "\n\n" + riga4
                if not messagebox.askyesno("QSL gia stampata", msg):
                    return
            self._selected.add(idx)

        sel = idx in self._selected
        tag = ("selY" if sent=="Y" else "sel") if sel else ("sent" if sent=="Y" else "unsel")
        vals = list(self.tree.item(item, "values"))
        vals[0] = "☑" if sel else "☐"
        self.tree.item(item, values=vals, tags=(tag,))
        self._aggiorna_count()

    def _sel_tutti(self):
        self._selected = set(self.qsos_tutti.index(q) for q in self._qso_filtrati)
        self._popola()

    def _sel_nessuno(self):
        for q in self._qso_filtrati:
            self._selected.discard(self.qsos_tutti.index(q))
        self._popola()

    def _inverti(self):
        for q in self._qso_filtrati:
            i = self.qsos_tutti.index(q)
            if i in self._selected: self._selected.discard(i)
            else: self._selected.add(i)
        self._popola()

    def _reset_qsl_sent(self):
        if not messagebox.askyesno("Reset QSL_SENT",
            "Azzera QSL_SENT=Y in memoria per tutti i QSO?\n\n"
            "Il file su disco NON viene modificato."):
            return
        n = sum(1 for q in self.qsos_tutti
                if str(q.get('qsl_sent','')).upper().strip() == 'Y')
        for q in self.qsos_tutti:
            if str(q.get('qsl_sent','')).upper().strip() == 'Y':
                q['qsl_sent'] = 'N'
        self._modifiche_pendenti = False
        self._aggiorna_lbl_memoria()
        self._aggiorna_count()
        self._popola()
        messagebox.showinfo("Reset", f"QSL_SENT azzerato in memoria per {n} QSO.")

    def _sel_non_sent(self):
        for q in self._qso_filtrati:
            i = self.qsos_tutti.index(q)
            if str(q.get("qsl_sent","")).upper().strip() != "Y":
                self._selected.add(i)
            else:
                self._selected.discard(i)
        self._popola()

    def _shift_click(self, event):
        """Seleziona/deseleziona un range dal last_clicked all'item corrente."""
        item = self.tree.identify_row(event.y)
        if not item: return
        idx_fine = int(item)

        if self._last_clicked_idx is None:
            self._last_clicked_idx = idx_fine
            return

        # Trova posizioni nel filtrato
        filtrati_ids = [self._idx_map.get(id(q), 0) for q in self._qso_filtrati]
        try:
            pos_start = filtrati_ids.index(self._last_clicked_idx)
            pos_fine  = filtrati_ids.index(idx_fine)
        except ValueError:
            return

        if pos_start > pos_fine:
            pos_start, pos_fine = pos_fine, pos_start

        # Determina azione: se l'ultimo cliccato era selezionato -> seleziona range
        # altrimenti deseleziona range
        azione_seleziona = self._last_clicked_idx not in self._selected

        for pos in range(pos_start, pos_fine + 1):
            orig_idx = filtrati_ids[pos]
            qso = self.qsos_tutti[orig_idx]
            sent = str(qso.get("qsl_sent","")).upper().strip()

            if azione_seleziona:
                if sent == "Y":
                    # Per le grigie nel range non chiede conferma, le salta
                    continue
                self._selected.add(orig_idx)
            else:
                self._selected.discard(orig_idx)

            sel = orig_idx in self._selected
            tag = ("selY" if sent=="Y" else "sel") if sel else ("sent" if sent=="Y" else "unsel")
            vals = list(self.tree.item(str(orig_idx), "values"))
            vals[0] = "☑" if sel else "☐"
            self.tree.item(str(orig_idx), values=vals, tags=(tag,))

        self._last_clicked_idx = idx_fine
        self._aggiorna_count()

    def _aggiorna_count(self):
        from collections import Counter
        n_qso = len(self._selected)
        tot   = len(self._qso_filtrati)
        fmt   = self._formato_attivo()
        per_foglio = fmt[2] * fmt[3]

        # Calcola etichette reali considerando il raggruppamento
        if self.var_raggruppa.get() and n_qso > 0:
            call_counts = Counter(
                str(self.qsos_tutti[i].get('call','')).upper().strip()
                for i in self._selected)
            n_etichette = sum(math.ceil(c/3) for c in call_counts.values())
            etich_info = f"{n_qso} QSO = {n_etichette} etichette"
        else:
            n_etichette = n_qso
            etich_info = f"{n_qso} etichette"

        if n_etichette > 0:
            fogli = math.ceil(n_etichette / per_foglio)
            resto = fogli * per_foglio - n_etichette
            if resto == 0:
                foglio_info = f"  |  {fogli} {'foglio' if fogli==1 else 'fogli'} completi"
            else:
                foglio_info = f"  |  {fogli} {'foglio' if fogli==1 else 'fogli'} — mancano {resto}"
        else:
            foglio_info = f"  |  {per_foglio}/foglio"

        if hasattr(self, '_count_after'):
            self.after_cancel(self._count_after)
        self._count_after = self.after(80, lambda t=f"{etich_info} / {tot} vis.{foglio_info}":
            self.lbl_count.configure(text=t) if self.winfo_exists() else None)

    # ── Formato ───────────────────────────────────────
    def _formato_attivo(self):
        return self.FORMATI.get(self.var_formato.get(), list(self.FORMATI.values())[0])

    def _on_formato_cambiato(self, valore):
        if valore == "▶ Formato personalizzato…":
            self._apri_formato_custom()
        else:
            self._reset_margini()

    def _apri_formato_custom(self):
        """Dialog per inserire dimensioni etichetta e layout foglio personalizzati."""
        dlg = ctk.CTkToplevel(self)
        dlg.title(T("etq_format_pers"))
        dlg.geometry("360x460")
        dlg.resizable(False, False)
        dlg.grab_set(); dlg.lift(); dlg.focus_force()

        ctk.CTkLabel(dlg, text=T("etq_format_pers"),
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(16,10), padx=20)

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="x", padx=24)

        def campo(r, lbl, default):
            ctk.CTkLabel(form, text=lbl, anchor="e", width=140,
                         font=ctk.CTkFont(size=11)).grid(row=r, column=0, pady=4, sticky="e")
            e = ctk.CTkEntry(form, width=80, justify="center")
            e.insert(0, default)
            e.grid(row=r, column=1, padx=(8,0), pady=4, sticky="w")
            return e

        # Nome del formato (riga 0 — più larga, sopra i campi numerici)
        ctk.CTkLabel(form, text=T("etq_nome_formato"), anchor="e", width=140,
                     font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, pady=4, sticky="e")
        e_nome = ctk.CTkEntry(form, width=160, placeholder_text=T("etq_nome_ph"))
        e_nome.grid(row=0, column=1, padx=(8,0), pady=4, sticky="w")

        e_lw   = campo(1, "Larghezza (mm):",   "51")
        e_lh   = campo(2, "Altezza (mm):",     "27")
        e_cols = campo(3, "Colonne:",           "4")
        e_rows = campo(4, "Righe:",             "11")
        e_ml   = campo(5, "Margine sin (mm):",  "3.0")
        e_mt   = campo(6, "Margine sup (mm):",  "0.0")
        e_gh   = campo(7, "Gap oriz (mm):",     "0.0")
        e_gv   = campo(8, "Gap vert (mm):",     "0.0")

        lbl_info = ctk.CTkLabel(dlg, text="", font=ctk.CTkFont(size=10),
                                text_color="#48BB78")
        lbl_info.pack(pady=(4,0))

        def _aggiorna_info(*_):
            try:
                lw = float(e_lw.get()); lh = float(e_lh.get())
                cols = int(e_cols.get()); rows = int(e_rows.get())
                n = cols * rows
                lbl_info.configure(text=f"{cols}×{rows} = {n} etichette/foglio  |  {lw}×{lh}mm")
            except Exception:
                lbl_info.configure(text="")
        for e in (e_lw, e_lh, e_cols, e_rows):
            e.bind("<KeyRelease>", _aggiorna_info)
        _aggiorna_info()

        def _applica():
            try:
                lw   = float(e_lw.get())
                lh   = float(e_lh.get())
                cols = int(e_cols.get())
                rows = int(e_rows.get())
                ml   = float(e_ml.get())
                mt   = float(e_mt.get())
                gh   = float(e_gh.get())
                gv   = float(e_gv.get())
                if lw <= 0 or lh <= 0 or cols < 1 or rows < 1:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Attenzione",
                    "Inserisci valori numerici validi per tutti i campi.",
                    parent=dlg)
                return
            nome = e_nome.get().strip()
            if not nome:
                messagebox.showwarning("Attenzione",
                    "Inserisci un nome per il formato.", parent=dlg)
                e_nome.focus_set()
                return
            n = cols * rows
            # Chiave = nome scelto dall'utente (più leggibile nel menu)
            chiave = f"{nome}  ({lw}×{lh}mm — {cols}×{rows} = {n}/A4)"
            self.FORMATI[chiave] = (lw, lh, cols, rows, ml, mt, gh, gv, "A4")
            voci = [k for k in self.FORMATI if k != chiave and k != "▶ Formato personalizzato…"]
            voci = [chiave] + voci + ["▶ Formato personalizzato…"]
            self._menu_formato.configure(values=voci)
            self.var_formato.set(chiave)
            self.var_margin_top.set(str(mt))
            self.var_margin_left.set(str(ml))
            self.var_gap_v.set(str(gv))
            # Salva su disco i formati custom (tutti quelli non presenti nel default)
            formati_default = {
                "Personalizzato  51x27mm  — 4x11 = 44/A4",
                "Personalizzato  70x36mm  — 3x8 = 24/A4",
                "Avery L7159     63.5x33.9mm — 3x8 = 24/A4",
                "Avery L7160     63.5x38.1mm — 3x7 = 21/A4",
                "Avery L7163     99.1x38.1mm — 2x7 = 14/A4",
                "Avery 5160      66.7x25.4mm — 3x10 = 30/Letter",
            }
            formati_custom = {k: v for k, v in self.FORMATI.items() if k not in formati_default}
            if hasattr(self.app_ref, '_salva_formati_qsl'):
                self.app_ref._salva_formati_qsl(formati_custom)
            dlg.destroy()

        frame_btn = ctk.CTkFrame(dlg, fg_color="transparent")
        frame_btn.pack(fill="x", padx=20, pady=(10,16))
        ctk.CTkButton(frame_btn, text="✔ Applica", command=_applica,
                      fg_color="#276749", height=34).pack(side="left", expand=True, fill="x", padx=(0,6))
        ctk.CTkButton(frame_btn, text=T("pref_annulla"), command=dlg.destroy,
                      fg_color="#718096", height=34).pack(side="left", expand=True, fill="x")

    def _reset_margini(self):
        fmt = self._formato_attivo()
        self.var_margin_top.set(str(fmt[5]))
        self.var_margin_left.set(str(fmt[4]))
        self.var_gap_v.set(str(fmt[7]))

    # ── Memoria ───────────────────────────────────────
    @staticmethod
    def _estrai_prefisso(callsign):
        call = str(callsign).upper().strip().split('/')[0]
        p = ''
        for ch in call:
            if ch.isdigit(): break
            p += ch
        return p if p else call[:2]

    def _tutti_i_callsign(self):
        r = set()
        for v in self.memoria_per_prefisso.values(): r.update(v)
        return r

    def _carica_memoria(self):
        try:
            if os.path.exists(self.memoria_path):
                with open(self.memoria_path,'r',encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    r = {}
                    for c in data:
                        p = self._estrai_prefisso(c)
                        r.setdefault(p,[])
                        if c not in r[p]: r[p].append(c)
                    return r
                return {k:list(v) for k,v in data.items()}
        except: pass
        return {}

    def _salva_memoria(self):
        try:
            with open(self.memoria_path,'w',encoding='utf-8') as f:
                json.dump(self.memoria_per_prefisso, f, ensure_ascii=False)
        except: pass

    def _aggiorna_lbl_memoria(self):
        if not self.lbl_memoria: return
        n = sum(1 for q in self.qsos_tutti
                if str(q.get('qsl_sent','')).upper().strip()=='Y')
        tot = len(self.qsos_tutti)
        if n == 0:
            self.lbl_memoria.configure(text=T("etq_memoria_vuota"), text_color="gray")
        else:
            self.lbl_memoria.configure(text=f"QSL_SENT=Y: {n}/{tot}", text_color="#48BB78")

    # ── Genera PDF ────────────────────────────────────
    def _cerca_manager_selezionati(self):
        """Cerca QSL Manager su IK3QAR per i QSO selezionati
        (spuntati nella griglia) privi di QSL_VIA."""
        import threading as _threading
        import tkinter as _tk
        import tkinter.ttk as _ttk

        qsos_sel = [self.qsos_tutti[i] for i in sorted(self._selected)]
        if not qsos_sel:
            messagebox.showwarning(T("attenzione"), T("qsl_sel_nessuno_sel"))
            return

        # Solo quelli senza QSL_VIA già popolato
        qsos_da_cercare = [(i, self.qsos_tutti[i])
                           for i in sorted(self._selected)
                           if not str(self.qsos_tutti[i].get("qsl_via","")).strip()]
        if not qsos_da_cercare:
            messagebox.showinfo("Info",
                "Tutti i QSO selezionati hanno già QSL_VIA compilato.", parent=self)
            return

        # Deduplica per callsign
        call_a_idx = {}
        for idx, qso in qsos_da_cercare:
            call = str(qso.get("call","")).upper().strip()
            if call:
                call_a_idx.setdefault(call, []).append(idx)

        calls_unici = list(call_a_idx.keys())
        n_tot = len(calls_unici)
        if not n_tot:
            return

        # Progress
        prog = ctk.CTkToplevel(self)
        prog.title("Ricerca manager…")
        prog.geometry("440x180")
        prog.resizable(False, False)
        prog.grab_set()
        ctk.CTkLabel(prog, text="🔍 Interrogo IK3QAR…",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(16,4))
        lbl_prog = ctk.CTkLabel(prog, text="", font=ctk.CTkFont(size=10), text_color="gray")
        lbl_prog.pack()
        bar = ctk.CTkProgressBar(prog, width=380); bar.pack(pady=(8,4)); bar.set(0)
        lbl_n = ctk.CTkLabel(prog, text=f"0 / {n_tot}", font=ctk.CTkFont(size=10))
        lbl_n.pack()

        risultati = {}
        _stop = [False]

        def _thread():
            for i, call in enumerate(calls_unici):
                if _stop[0]: break
                trovato = None
                try:
                    url = f"https://www.ik3qar.it/manager/man_result.php?call={urllib.parse.quote(call)}"
                    req = urllib.request.Request(url, headers={"User-Agent":"ADIF-FZR/2.3"})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        html = resp.read().decode("iso-8859-1", errors="replace")
                    righe = re.findall(
                        r'<td[^>]*>\s*(?:<[^>]+>)*([A-Z0-9/]+)(?:</[^>]+>)*\s*</td>'
                        r'\s*<td[^>]*>\s*(?:<[^>]+>)*([A-Z0-9/]+)(?:</[^>]+>)*\s*</td>'
                        r'\s*<td[^>]*>\s*(\d{4})\s*</td>\s*<td[^>]*>\s*(.*?)\s*</td>',
                        html, re.IGNORECASE|re.DOTALL)
                    trovati_ik = [(m,y,re.sub('<[^>]+>','',x).strip())
                                  for c,m,y,x in righe if c.upper()==call]
                    if trovati_ik:
                        m,y,info = trovati_ik[-1]
                        trovato = (m, y, info)
                except Exception:
                    pass
                risultati[call] = trovato
                def _upd(i=i, call=call):
                    if prog.winfo_exists():
                        bar.set((i+1)/n_tot)
                        lbl_n.configure(text=f"{i+1} / {n_tot}")
                        lbl_prog.configure(text=f"{call}…")
                prog.after(0, _upd)
                import time; time.sleep(0.25)

            def _finish():
                if prog.winfo_exists(): prog.destroy()
                self._mostra_risultati_manager_master(risultati, call_a_idx)
            prog.after(0, _finish)

        ctk.CTkButton(prog, text=T("cm_annulla"), height=28, fg_color="#718096",
                      command=lambda: _stop.__setitem__(0,True)).pack(pady=4)
        _threading.Thread(target=_thread, daemon=True).start()

    def _mostra_risultati_manager_master(self, risultati, call_a_idx):
        """Tabella di revisione e aggiornamento QSL_VIA per QSLMasterDialog."""
        import tkinter as _tk
        import tkinter.ttk as _ttk

        trovati = {c: r for c, r in risultati.items() if r}
        if not trovati:
            messagebox.showinfo("Risultato",
                "Nessun manager trovato nel database IK3QAR per i QSO selezionati.", parent=self)
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title(f"IK3QAR — {len(trovati)} manager trovati")
        dlg.geometry("720x440")
        dlg.resizable(True, True)
        dlg.grab_set(); dlg.lift(); dlg.focus_force()

        ctk.CTkLabel(dlg, text=f"🔍 {len(trovati)} manager trovati su {len(risultati)} cercati",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12,4), padx=16)
        ctk.CTkLabel(dlg, text="Applica per aggiornare QSL_VIA nel log e visualizzarlo sull'etichetta.",
                     font=ctk.CTkFont(size=10), text_color="gray").pack(pady=(0,6))

        # Pulsanti IN CIMA così sono sempre visibili
        frame_btn = ctk.CTkFrame(dlg, fg_color="transparent")
        frame_btn.pack(fill="x", padx=12, pady=(0,6))

        vars_sel = {}
        iid_to_call = {}

        def _sel_tutti():
            for iid in vars_sel:
                vars_sel[iid] = True
                v = list(tv.item(iid, "values")); v[0] = "☑"; tv.item(iid, values=v)
        def _sel_nessuno():
            for iid in vars_sel:
                vars_sel[iid] = False
                v = list(tv.item(iid, "values")); v[0] = "☐"; tv.item(iid, values=v)

        ctk.CTkButton(frame_btn, text="☑ Tutti", width=70, height=30,
                      fg_color="#4A5568", command=_sel_tutti).pack(side="left", padx=(0,4))
        ctk.CTkButton(frame_btn, text="☐ Nessuno", width=80, height=30,
                      fg_color="#4A5568", command=_sel_nessuno).pack(side="left", padx=(0,12))

        def _applica():
            n_agg = 0
            for iid, sel in vars_sel.items():
                if not sel: continue
                call, mgr = iid_to_call[iid]
                for idx in call_a_idx.get(call, []):
                    self.qsos_tutti[idx]["qsl_via"] = mgr.upper()
                    n_agg += 1
            try: self.app_ref._aggiorna_tree()
            except Exception: pass
            self._popola()
            dlg.destroy()
            messagebox.showinfo("Aggiornato",
                f"QSL_VIA aggiornato su {n_agg} QSO.\nSalva il file ADIF per rendere permanente.",
                parent=self)

        ctk.CTkButton(frame_btn, text=f"✔ Applica ({len(trovati)} call)",
                      command=_applica, height=30,
                      fg_color="#276749", hover_color="#2F855A",
                      font=ctk.CTkFont(size=11, weight="bold")).pack(
                      side="left", expand=True, fill="x", padx=(0,6))
        ctk.CTkButton(frame_btn, text=T("cm_annulla"), width=80, height=30,
                      fg_color="#718096", command=dlg.destroy).pack(side="left")

        # Treeview
        style = _ttk.Style(); style.theme_use("default")
        style.configure("Mgr2.Treeview", background="#0D0D0D", foreground="#E2E8F0",
            rowheight=24, fieldbackground="#0D0D0D", font=("Arial",9))
        style.configure("Mgr2.Treeview.Heading", background="#1A365D",
            foreground="white", font=("Arial",9,"bold"))

        frame_t = _tk.Frame(dlg, bg="#0D0D0D")
        frame_t.pack(fill="both", expand=True, padx=12, pady=(0,12))

        cols = ("sel", "call", "manager", "anno", "n_qso", "info")
        tv = _ttk.Treeview(frame_t, columns=cols, show="headings", style="Mgr2.Treeview")
        tv.heading("sel",     text="✔")
        tv.heading("call",    text=T("cm_callsign_dx"))
        tv.heading("manager", text=T("cm_qsl_manager"))
        tv.heading("anno",    text=T("cm_anno"))
        tv.heading("n_qso",   text=T("cm_n_qso"))
        tv.heading("info",    text=T("cm_note"))
        tv.column("sel",     width=30,  stretch=False)
        tv.column("call",    width=120, stretch=False)
        tv.column("manager", width=120, stretch=False)
        tv.column("anno",    width=55,  stretch=False)
        tv.column("n_qso",   width=55,  stretch=False)
        tv.column("info",    width=300)

        sb = _ttk.Scrollbar(frame_t, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tv.pack(side="left", fill="both", expand=True)

        for call, risultato in trovati.items():
            manager, anno, info = risultato
            n = len(call_a_idx.get(call, []))
            iid = tv.insert("", "end", values=("☑", call, manager, anno, n, info))
            vars_sel[iid] = True
            iid_to_call[iid] = (call, manager)

        def _toggle(e):
            row = tv.identify_row(e.y)
            if row and tv.identify_column(e.x) == "#1":
                vars_sel[row] = not vars_sel[row]
                v = list(tv.item(row, "values"))
                v[0] = "☑" if vars_sel[row] else "☐"
                tv.item(row, values=v)
        tv.bind("<Button-1>", _toggle)

    def _genera(self):
        qsos_sel = [self.qsos_tutti[i] for i in sorted(self._selected)]
        if not qsos_sel:
            messagebox.showwarning(T("attenzione"), T("qsl_sel_nessuno_sel"))
            return

        nome_def = f"QSL_{self.stazione or 'card'}_etichette.pdf"
        fp = getattr(self.app_ref, 'filepath', None)
        save_path = chiedi_cartella_output(self, nome_def, fp)
        if save_path is None: return
        if save_path == "":
            save_path = filedialog.asksaveasfilename(
                title=T("etq_salva_pdf"), defaultextension=".pdf",
                filetypes=[("PDF files","*.pdf")], initialfile=nome_def)
        if not save_path: return

        try:
            # Raggruppa per callsign se richiesto
            if self.var_raggruppa.get():
                qsos_pdf = self._raggruppa_per_call(qsos_sel)
            else:
                qsos_pdf = qsos_sel
            try:
                offset = max(0, int(self.var_offset.get()) - 1)
            except Exception:
                offset = 0
            self._genera_pdf(save_path, qsos_pdf, offset=offset)
            n = len(qsos_sel)
            fmt = self._formato_attivo()
            fogli = math.ceil(n / (fmt[2]*fmt[3]))
            # Aggiorna QSL_SENT in memoria
            oggi = datetime.today().strftime("%Y%m%d")
            aggiunti = 0
            calls_sel = set(str(q.get('call','')).upper().strip() for q in qsos_sel)
            for q in self.qsos_tutti:
                if str(q.get('call','')).upper().strip() in calls_sel:
                    if str(q.get('qsl_sent','')).upper().strip() != 'Y':
                        q['qsl_sent'] = 'Y'
                        q.setdefault('qslsdate', oggi)
                        aggiunti += 1
            self._modifiche_pendenti = aggiunti > 0
            self._aggiorna_lbl_memoria()
            self._aggiorna_count()
            self._popola()

            msg = f"PDF generato!\n{n} etichette su {fogli} fogli A4."
            if aggiunti: msg += f"\n{aggiunti} QSO aggiornati a QSL_SENT=Y"
            if messagebox.askyesno(T("successo"), msg + "\n\nAprire il file?"):
                os.startfile(os.path.abspath(save_path))
        except Exception as ex:
            messagebox.showerror(T("errore"), f"Errore:\n{ex}")

    def _raggruppa_per_call(self, qsos):
        """Raggruppa QSO per callsign in gruppi da max 3.
        Restituisce lista di 'gruppi': ogni gruppo è una lista di QSO."""
        from collections import OrderedDict
        gruppi = OrderedDict()
        for q in qsos:
            call = str(q.get('call','')).upper().strip()
            if call not in gruppi:
                gruppi[call] = []
            gruppi[call].append(q)
        # Ogni gruppo max 3 QSO → se >3 crea piu gruppi
        result = []
        for call, lista in gruppi.items():
            for i in range(0, len(lista), 3):
                result.append(lista[i:i+3])
        return result

    def _genera_pdf(self, path, qsos, offset=0):
        from reportlab.lib.units import mm
        from reportlab.lib.pagesizes import A4, LETTER
        from reportlab.pdfgen import canvas as cv
        from reportlab.lib.colors import Color

        def rgba(hex_str, alpha=1.0):
            h = hex_str.lstrip("#")
            r,g,b = int(h[0:2],16)/255,int(h[2:4],16)/255,int(h[4:6],16)/255
            return Color(r,g,b,alpha)

        c1  = self.colori_pdf["primario"]
        msg = self.entry_msg.get().strip()
        fmt = self._formato_attivo()
        LW_MM,LH_MM,COLS,ROWS,ML_MM,MT_MM,GH_MM,GV_MM,psize_key = fmt

        try: MT_MM = float(self.var_margin_top.get())
        except: pass
        try: ML_MM = float(self.var_margin_left.get())
        except: pass
        try: GV_MM = float(self.var_gap_v.get())
        except: pass

        page_size = LETTER if psize_key=="LETTER" else A4
        PW, PH = page_size
        LW,LH,ML,MT,GH,GV = LW_MM*mm,LH_MM*mm,ML_MM*mm,MT_MM*mm,GH_MM*mm,GV_MM*mm

        c = cv.Canvas(path, pagesize=page_size)

        def disegna_etichetta(idx, gruppo):
            """Disegna etichetta per un gruppo di 1-3 QSO dello stesso callsign.
            idx è lo slot logico dell'etichetta (0-based), a cui viene sommato
            offset per saltare le posizioni già usate sul foglio parziale."""
            pos = idx + offset          # posizione reale sul foglio
            col = pos % COLS
            row = (pos // COLS) % ROWS
            if pos > 0 and pos % (COLS*ROWS) == 0: c.showPage()
            x0 = ML + col*(LW+GH)
            y0 = PH - MT - (row+1)*(LH+GV)

            qso = gruppo[0]  # primo QSO per callsign e dati fissi
            call_dx = str(qso.get("call","")).upper()
            country = str(qso.get("country","")).upper()
            grid    = str(qso.get("gridsquare","")).upper()

            # Sfondo bianco
            c.setFillColor(colors.white)
            c.rect(x0, y0, LW, LH, fill=1, stroke=0)

            # Intestazione: stazione + dicitura
            header_h = 9*mm
            # Colori condizionali
            usa_colori = self.var_colori_etichetta.get()

            # Callsign stazione
            c.setFillColor(rgba(c1))
            c.setFont("Helvetica-Bold", 8)
            c.drawString(x0+2*mm, y0+LH-5*mm, self.stazione or "STATION")
            col_call    = rgba("#1A365D") if usa_colori else rgba("#000000")
            col_confirm = rgba("#C53030") if usa_colori else rgba("#718096")
            col_data    = rgba("#2D3748")
            col_country = rgba("#4A5568")
            col_grid    = rgba("#718096")

            # Scritta "CONFIRMING QSO" in rosso/grigio
            c.setFont("Helvetica", 4.5)
            c.setFillColor(col_confirm)
            c.drawString(x0+2*mm, y0+LH-header_h+1.5*mm, "CONFERMA QSO CON / CONFIRMING QSO WITH:")

            # Callsign DX grande in blu/nero
            c.setFillColor(col_call)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(x0+2*mm, y0+LH-header_h-5*mm, call_dx)

            # QSL via manager: sulla stessa riga del callsign, subito dopo
            qsl_via = str(qso.get("qsl_via", "")).strip().upper()
            # Se via è vuoto ma il paese ha bureau IARU → mostra "(bureau)"
            _is_usa = country in ("UNITED STATES","USA","UNITED STATES OF AMERICA")
            via_display = qsl_via if qsl_via else ("(bureau)" if _ha_bureau(qso) and not _is_usa else "")
            if via_display:
                call_w = c.stringWidth(call_dx, "Helvetica-Bold", 10)
                if qsl_via:
                    c.setFont("Helvetica-BoldOblique", 6)
                    c.setFillColor(rgba("#C05621"))          # arancio = manager esplicito
                else:
                    c.setFont("Helvetica-Oblique", 5.5)
                    c.setFillColor(rgba("#718096"))          # grigio = bureau generico
                c.drawString(x0+2*mm+call_w+2*mm, y0+LH-header_h-4.5*mm, f"via {via_display}")

            # Country + Locatore — country solo se NON c'è via manager (non per bureau)
            if self.var_country.get():
                if country and not via_display:
                    stato = str(qso.get("state","")).upper().strip()
                    if country in ("UNITED STATES","USA","UNITED STATES OF AMERICA"):
                        country_display = f"USA ({stato})" if stato else "USA"
                    else:
                        country_display = country
                    c.setFont("Helvetica", 5.5)
                    c.setFillColor(col_country)
                    call_w = c.stringWidth(call_dx, "Helvetica-Bold", 10)
                    c.drawString(x0+2*mm+call_w+3*mm, y0+LH-header_h-5*mm, country_display)
                if grid:
                    c.setFont("Helvetica", 5)
                    c.setFillColor(col_grid)
                    c.drawString(x0+2*mm, y0+LH-header_h-9*mm, f"LOC: {grid}")

            # Calcola altezza disponibile per i QSO
            footer_h = 5*mm
            area_top = y0 + LH - header_h - 10*mm
            n_qso = len(gruppo)
            # linea separatore per ogni QSO se piu di 1
            riga_h = (area_top - y0 - footer_h) / max(n_qso, 1)

            for i, q in enumerate(gruppo):
                data = str(q.get("qso_date",""))
                if len(data)==8: data=f"{data[6:8]}/{data[4:6]}/{data[0:4]}"
                utc = str(q.get("time_on",""))
                if len(utc)>=4: utc=f"{utc[0:2]}:{utc[2:4]}"
                banda   = str(q.get("band","")).upper()
                modo    = str(q.get("mode","")).upper()
                submode = str(q.get("submode","")).upper().strip()
                modo_display = f"{modo}/{submode}" if submode and submode != modo else modo
                rst_s    = str(q.get("rst_sent","599"))
                rst_r    = str(q.get("rst_rcvd","599"))
                sat_name = str(q.get("sat_name","")).upper().strip()
                # Banda: se satellite mostra nome tra parentesi
                banda_display = f"{banda} ({sat_name})" if sat_name else banda

                yq = area_top - i * riga_h - riga_h*0.6

                # Linea separatore tra QSO (tranne il primo)
                if i > 0:
                    c.setStrokeColor(rgba("#CBD5E0", 0.5))
                    c.setLineWidth(0.3)
                    c.setDash()
                    c.line(x0+2*mm, area_top - i*riga_h, x0+LW-2*mm, area_top - i*riga_h)

                c.setFont("Helvetica-Bold", 5.5)
                c.setFillColor(rgba("#2D3748"))
                c.drawString(x0+2*mm, yq, f"{data}  {utc}UTC")
                c.setFont("Helvetica", 5.5)
                riga_qso = f"{banda_display}  {modo_display}  RST:{rst_s}/{rst_r}"
                c.drawString(x0+24*mm, yq, riga_qso)

            # LoTW / eQSL del primo QSO
            if self.var_lotw.get():
                lotw = str(qso.get("lotw_qsl_rcvd","")).upper().strip()
                eqsl = str(qso.get("eqsl_qsl_rcvd","")).upper().strip()
                c.setFont("Helvetica", 5)
                c.setFillColor(rgba("#48BB78") if lotw in ("Y","V") else rgba("#A0AEC0"))
                c.drawString(x0+2*mm, y0+1.5*mm, "LoTW✓" if lotw in ("Y","V") else "LoTW-")
                c.setFillColor(rgba("#48BB78") if eqsl=="Y" else rgba("#A0AEC0"))
                c.drawString(x0+9*mm, y0+1.5*mm, "eQSL✓" if eqsl=="Y" else "eQSL-")

            if msg:
                c.setFont("Helvetica-Oblique", 4.5)
                c.setFillColor(rgba("#718096"))
                c.drawRightString(x0+LW-2*mm, y0+1.5*mm, msg)

            if self.var_border.get():
                c.setStrokeColor(rgba("#A0AEC0", 0.6))
                c.setLineWidth(0.4)
                c.setDash(3,3)
                c.rect(x0, y0, LW, LH, fill=0, stroke=1)
                c.setDash()

        # Gestisci sia lista di gruppi che lista di QSO singoli
        for idx, item in enumerate(qsos):
            gruppo = item if isinstance(item, list) else [item]
            disegna_etichetta(idx, gruppo)

        c.save()

    # ── Aggiorna QSL_SENT ─────────────────────────────
    def _aggiorna_sent(self):
        qsos_sel = [self.qsos_tutti[i] for i in sorted(self._selected)]
        if not qsos_sel:
            messagebox.showwarning(T("attenzione"), T("qsl_sel_nessuno_sel"))
            return
        oggi = datetime.today().strftime("%Y%m%d")
        calls_sel = set(str(q.get('call','')).upper().strip() for q in qsos_sel)
        n = 0
        for q in self.qsos_tutti:
            if str(q.get('call','')).upper().strip() in calls_sel:
                q['qsl_sent'] = 'Y'
                q.setdefault('qslsdate', oggi)
                n += 1

        msg_chiedi = ("Vuoi aggiornare il file ADIF originale?"
                      "\n\nSI  = sovrascrive il file originale"
                      "\nNO  = salva una copia _QSL.adif"
                      "\nANNULLA = non salvare")
        risposta = messagebox.askyesnocancel("Salva ADIF aggiornato", msg_chiedi)

        if risposta is None:
            return
        elif risposta:
            save_path = self.app_ref.filepath
        else:
            base = os.path.splitext(os.path.basename(self.app_ref.filepath))[0]
            nome_def = base + "_QSL.adif"
            fp = getattr(self.app_ref, 'filepath', None)
            save_path = chiedi_cartella_output(self, nome_def, fp)
            if save_path is None: return
            if save_path == "":
                save_path = filedialog.asksaveasfilename(
                    title=T("dv_salva_copia"),
                    defaultextension=".adif",
                    filetypes=[("ADIF files","*.adif")],
                    initialfile=nome_def)
            if not save_path:
                return

        self.app_ref._scrivi_adif(save_path, self.app_ref.qsos_caricati)
        self._modifiche_pendenti = False
        self._aggiorna_lbl_memoria()
        self._popola()
        messagebox.showinfo(T("successo"),
            "QSL_SENT aggiornato!\n" + str(n) + " QSO aggiornati.\nFile: " + os.path.basename(save_path))

    # ── Chiusura ──────────────────────────────────────
    def _chiudi(self):
        if self._modifiche_pendenti:
            if messagebox.askyesno("Attenzione",
                "Hai stampato etichette ma non hai salvato il file ADIF aggiornato.\nSalvare ora?"):
                self._aggiorna_sent()
                return
        try:
            _ripristina_tema_ttk()
        except Exception:
            pass
        super().destroy()

    def destroy(self):
        self._chiudi()

class QSLCardDialog(ctk.CTkToplevel):
    # (LABEL_W_MM, LABEL_H_MM, COLS, ROWS, MARGIN_L, MARGIN_T, GAP_H, GAP_V, pagesize)
    FORMATI = {
        "Personalizzato  51x27mm  — 4x11 = 44/A4":   (51.0, 27.0, 4, 11, 3.0,  0.0, 0.0, 0.0, "A4"),
        "Personalizzato  70x36mm  — 3x8 = 24/A4":    (70.0, 36.0, 3, 8,  5.0, 11.0, 0.0, 0.0, "A4"),
        "Avery L7159     63.5x33.9mm — 3x8 = 24/A4": (63.5, 33.9, 3, 8,  7.2, 13.5, 2.5, 0.0, "A4"),
        "Avery L7160     63.5x38.1mm — 3x7 = 21/A4": (63.5, 38.1, 3, 7,  7.2, 15.1, 2.5, 0.0, "A4"),
        "Avery L7163     99.1x38.1mm — 2x7 = 14/A4": (99.1, 38.1, 2, 7,  4.7, 15.1, 2.5, 0.0, "A4"),
        "Avery 5160      66.7x25.4mm — 3x10 = 30/Letter": (66.7, 25.4, 3, 10, 4.8, 12.7, 3.2, 0.0, "LETTER"),
    }
    DEFAULT_FORMATO = "Personalizzato  70x36mm  — 3x8 = 24/A4"

    def __init__(self, parent, qsos, stazione, colori_pdf):
        super().__init__(parent)
        self.title(T("qsl_titolo"))
        self.geometry("640x640")
        self.resizable(False, True)
        self.minsize(640, 500)
        self.grab_set()
        self.qsos        = qsos
        self.stazione    = stazione
        self.colori_pdf  = colori_pdf
        self.app_ref     = parent  # riferimento all'app principale
        self._modifiche_pendenti = False  # True se QSL_SENT aggiornato senza salvare
        self.var_margin_top  = ctk.StringVar(value="11.0")
        self.var_margin_left = ctk.StringVar(value="5.0")
        self.var_gap_v       = ctk.StringVar(value="0.0")
        self.var_solo_nuovi  = ctk.BooleanVar(value=False)
        self.var_formato     = ctk.StringVar(value=self.DEFAULT_FORMATO)
        self.memoria_path = os.path.join(os.path.expanduser("~"), ".adif_qsl_memoria.json")
        self.memoria_per_prefisso = self._carica_memoria()  # dict {prefisso: [callsign,...]}
        self.lbl_memoria     = None  # creato nel frame_mem, inizializzato dopo

        ctk.CTkLabel(self, text=T("qsl_header"),
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=8)

        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(pady=8, fill="x", padx=15)
        ctk.CTkButton(frame_btn, text=T("qsl_genera_btn"),
                      command=self.genera,
                      fg_color="#2B6CB0", hover_color="#3182CE",
                      height=42, font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", expand=True, padx=(0,6), fill="x")
        ctk.CTkButton(frame_btn, text=T("chiudi"), command=self.destroy,
                      fg_color="#718096", height=42).pack(side="right", padx=(6,0))

        # ── Area scorrevole (tutti i controlli tranne i pulsanti) ──
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Selettore formato etichetta ───────────────────────
        frame_fmt = ctk.CTkFrame(self._scroll)
        frame_fmt.pack(fill="x", padx=15, pady=4)
        ctk.CTkLabel(frame_fmt, text=T("qsl_formato"),
                     font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
        ctk.CTkOptionMenu(frame_fmt, variable=self.var_formato,
                          values=list(self.FORMATI.keys()),
                          command=lambda _: (self._reset_margini(), self._aggiorna_info()),
                          width=370).pack(side="left", padx=8, pady=6)

        # ── Memoria etichette (2 righe) ──────────────────────
        frame_mem = ctk.CTkFrame(self._scroll)
        frame_mem.pack(fill="x", padx=15, pady=4)

        # Riga 1: label titolo + checkbox
        frame_mem_r1 = ctk.CTkFrame(frame_mem, fg_color="transparent")
        frame_mem_r1.pack(fill="x", pady=(4,2))
        ctk.CTkLabel(frame_mem_r1, text=T("qsl_memoria"),
                     font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
        ctk.CTkCheckBox(frame_mem_r1, text=T("qsl_solo_non_inviati"),
                        variable=self.var_solo_nuovi,
                        command=self._aggiorna_info).pack(side="left", padx=8)
        self.lbl_memoria = ctk.CTkLabel(frame_mem_r1, text="", text_color="gray",
                                         font=ctk.CTkFont(size=10))
        self.lbl_memoria.pack(side="left", padx=8)

        # Riga 2: pulsanti gestisci e azzera
        frame_mem_r2 = ctk.CTkFrame(frame_mem, fg_color="transparent")
        frame_mem_r2.pack(fill="x", pady=(2,4))
        ctk.CTkButton(frame_mem_r2, text=T("qsl_aggiorna_sent"), width=180, height=28,
                      fg_color="#276749", hover_color="#2F855A",
                      command=self._aggiorna_qsl_sent).pack(side="left", padx=(10,6))
        ctk.CTkButton(frame_mem_r2, text=T("qsl_gestisci"), width=110, height=28,
                      fg_color="#2B6CB0", hover_color="#1A365D",
                      command=self._apri_gestione_memoria).pack(side="left", padx=(0,6))
        ctk.CTkButton(frame_mem_r2, text=T("qsl_reset_mem"), width=110, height=28,
                      fg_color="#718096", hover_color="#4A5568",
                      command=self._azzera_memoria).pack(side="left", padx=0)

        self._aggiorna_lbl_memoria()

        # ── Filtri callsign + date su frame unico a griglia ──
        frame_filtri = ctk.CTkFrame(self._scroll)
        frame_filtri.pack(fill="x", padx=15, pady=4)

        # Riga 0 — Callsign
        ctk.CTkLabel(frame_filtri, text=T("qsl_filtro_call"),
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.var_tutti = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(frame_filtri, text=T("qsl_tutti"),
                        variable=self.var_tutti,
                        command=self._toggle).grid(row=0, column=1, padx=8, sticky="w")
        ctk.CTkLabel(frame_filtri, text=T("qsl_call_spec")).grid(row=0, column=2, padx=(12,4), sticky="e")
        self.entry_call = ctk.CTkEntry(frame_filtri, placeholder_text=T("cm_ph_call"), width=110)
        self.entry_call.grid(row=0, column=3, padx=4, sticky="w")

        # Riga 1 — Date
        date_valide = sorted([str(q.get('qso_date','')).strip() for q in qsos if len(str(q.get('qso_date','')).strip())==8])
        data_min = date_valide[0]  if date_valide else "19000101"
        data_max = date_valide[-1] if date_valide else "29991231"
        def fmt(d): return f"{d[6:8]}/{d[4:6]}/{d[0:4]}" if len(d)==8 else ""

        ctk.CTkLabel(frame_filtri, text=T("qsl_filtro_date"),
                     font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, rowspan=2, padx=10, pady=5, sticky="nw")
        ctk.CTkLabel(frame_filtri, text=T("qsl_da")).grid(row=1, column=1, padx=(8,2), sticky="e")
        self.entry_da = ctk.CTkEntry(frame_filtri, width=110)
        self.entry_da.insert(0, fmt(data_min))
        self.entry_da.grid(row=1, column=2, padx=4, sticky="w")
        ctk.CTkButton(frame_filtri, text="📅", width=26, height=26, fg_color="#2B6CB0",
                      command=lambda: CalendarPopup(self, self.entry_da)).grid(row=1, column=3, padx=(0,4), sticky="w")
        ctk.CTkLabel(frame_filtri, text=T("qsl_a")).grid(row=2, column=1, padx=(8,2), sticky="e")
        self.entry_a = ctk.CTkEntry(frame_filtri, width=110)
        self.entry_a.insert(0, fmt(data_max))
        self.entry_a.grid(row=2, column=2, padx=4, sticky="w")
        ctk.CTkButton(frame_filtri, text="📅", width=26, height=26, fg_color="#2B6CB0",
                      command=lambda: CalendarPopup(self, self.entry_a)).grid(row=2, column=3, padx=(0,4), sticky="w")

        # ── Opzioni + messaggio su frame unico ────────────────
        frame_opt = ctk.CTkFrame(self._scroll)
        frame_opt.pack(fill="x", padx=15, pady=4)

        ctk.CTkLabel(frame_opt, text=T("qsl_opzioni"),
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.var_border = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(frame_opt, text=T("qsl_bordo"),
                        variable=self.var_border).grid(row=0, column=1, padx=8, sticky="w")
        self.var_lotw = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(frame_opt, text=T("qsl_lotw_eqsl"),
                        variable=self.var_lotw).grid(row=0, column=2, padx=8, sticky="w")
        self.var_country = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(frame_opt, text=T("qsl_country_loc"),
                        variable=self.var_country).grid(row=0, column=3, padx=8, sticky="w")

        ctk.CTkLabel(frame_opt, text=T("qsl_messaggio")).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.entry_msg = ctk.CTkEntry(frame_opt,
                                       placeholder_text=T("dv_msg_ph"),
                                       width=400)
        self.entry_msg.grid(row=1, column=1, columnspan=4, padx=5, pady=5, sticky="w")

        # ── Info conteggio ────────────────────────────────────
        self.lbl_info = ctk.CTkLabel(self._scroll, text="", text_color="gray",
                                      font=ctk.CTkFont(size=11))
        self.lbl_info.pack(pady=2)
        self._aggiorna_info()

        # ── Regolazione margini ───────────────────────────────
        frame_margini = ctk.CTkFrame(self._scroll)
        frame_margini.pack(fill="x", padx=15, pady=4)
        ctk.CTkLabel(frame_margini, text=T("qsl_margini"),
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=5, sticky="w")

        ctk.CTkLabel(frame_margini, text=T("qsl_sup")).grid(row=0, column=1, padx=(10,2), sticky="e")
        self.var_margin_top = ctk.StringVar(value="11.0")
        ctk.CTkEntry(frame_margini, textvariable=self.var_margin_top,
                     width=52, height=26, justify="center").grid(row=0, column=2, padx=4)

        ctk.CTkLabel(frame_margini, text=T("qsl_sin")).grid(row=0, column=3, padx=(10,2), sticky="e")
        self.var_margin_left = ctk.StringVar(value="5.0")
        ctk.CTkEntry(frame_margini, textvariable=self.var_margin_left,
                     width=52, height=26, justify="center").grid(row=0, column=4, padx=4)

        ctk.CTkLabel(frame_margini, text=T("qsl_gap_v")).grid(row=0, column=5, padx=(10,2), sticky="e")
        self.var_gap_v = ctk.StringVar(value="0.0")
        ctk.CTkEntry(frame_margini, textvariable=self.var_gap_v,
                     width=52, height=26, justify="center").grid(row=0, column=6, padx=4)

        ctk.CTkButton(frame_margini, text=T("qsl_reset"), width=70, height=26,
                      fg_color="#718096", hover_color="#4A5568",
                      command=self._reset_margini).grid(row=0, column=7, padx=(10,5))

        ctk.CTkLabel(frame_margini,
                     text=T("qsl_margini_note"),
                     font=ctk.CTkFont(size=9), text_color="gray").grid(
                     row=1, column=0, columnspan=8, padx=10, pady=(0,4), sticky="w")

        # ── Pulsanti ──────────────────────────────────────────


    def destroy(self):
        """Intercetta la chiusura e chiede se salvare."""
        try:
            _ripristina_tema_ttk()
        except Exception:
            pass
        if self._modifiche_pendenti:
            self._chiedi_salvataggio()
        else:
            super().destroy()

    def _chiedi_salvataggio(self):
        """Dialogo che chiede come salvare il file ADIF aggiornato."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("ADIF to PDF Converter")
        dlg.geometry("420x200")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.attributes("-topmost", True)

        ctk.CTkLabel(dlg, text=T("qsl_chiudi_avviso"),
                     font=ctk.CTkFont(size=12),
                     justify="center").pack(pady=20, padx=20)

        frame_btn = ctk.CTkFrame(dlg, fg_color="transparent")
        frame_btn.pack(fill="x", padx=15, pady=10)

        def sovrascrivi():
            dlg.destroy()
            try:
                self.app_ref._scrivi_adif(self.app_ref.filepath, self.app_ref.qsos_caricati)
                self._modifiche_pendenti = False
                super(QSLCardDialog, self).destroy()
            except Exception as ex:
                messagebox.showerror(T("errore"), f"{T('qsl_sent_err')}{ex}")

        def salva_nuovo():
            dlg.destroy()
            base = os.path.splitext(os.path.basename(self.app_ref.filepath))[0]
            save_path = filedialog.asksaveasfilename(
                title=T("dv_salva_adif_agg"),
                defaultextension=".adif",
                filetypes=[("ADIF files", "*.adif"), ("All files", "*.*")],
                initialfile=base + "_QSL.adif"
            )
            if save_path:
                try:
                    self.app_ref._scrivi_adif(save_path, self.app_ref.qsos_caricati)
                    self._modifiche_pendenti = False
                except Exception as ex:
                    messagebox.showerror(T("errore"), f"{T('qsl_sent_err')}{ex}")
            super(QSLCardDialog, self).destroy()

        def non_salvare():
            dlg.destroy()
            self._modifiche_pendenti = False
            super(QSLCardDialog, self).destroy()

        ctk.CTkButton(frame_btn, text=T("qsl_salva_sovrascrivi"),
                      fg_color="#C05621", hover_color="#9C4221", height=32,
                      command=sovrascrivi).pack(fill="x", pady=3)
        ctk.CTkButton(frame_btn, text=T("qsl_salva_nuovo"),
                      fg_color="#276749", hover_color="#2F855A", height=32,
                      command=salva_nuovo).pack(fill="x", pady=3)
        ctk.CTkButton(frame_btn, text=T("qsl_non_salvare"),
                      fg_color="#718096", hover_color="#4A5568", height=32,
                      command=non_salvare).pack(fill="x", pady=3)

    def _toggle(self):
        self._aggiorna_info()

    def _parse_data(self, testo):
        testo = testo.strip()
        if not testo:
            return None
        for fmt in ("%d/%m/%Y", "%Y%m%d"):
            try:
                return datetime.strptime(testo, fmt)
            except ValueError:
                continue
        return None

    def _qso_selezionati(self):
        da = self._parse_data(self.entry_da.get())
        a  = self._parse_data(self.entry_a.get())
        call_f = self.entry_call.get().strip().upper()
        solo_nuovi = self.var_solo_nuovi.get()
        risultato = []
        for q in self.qsos:
            call = str(q.get('call','')).upper().strip()
            # filtro callsign specifico
            if not self.var_tutti.get() and call_f:
                if call != call_f:
                    continue
            # filtro QSL_SENT dal log ADIF
            if solo_nuovi and str(q.get('qsl_sent','')).upper().strip() == 'Y':
                continue
                continue
            # filtro date
            d_raw = str(q.get('qso_date','')).strip()
            if len(d_raw)==8:
                try:
                    d_qso = datetime.strptime(d_raw, "%Y%m%d")
                except ValueError:
                    d_qso = None
            else:
                d_qso = None
            if da and d_qso and d_qso < da:
                continue
            if a  and d_qso and d_qso > a:
                continue
            risultato.append(q)
        return risultato

    def _formato_attivo(self):
        return self.FORMATI.get(self.var_formato.get(), list(self.FORMATI.values())[0])

    @staticmethod
    def _estrai_prefisso(callsign):
        call = str(callsign).upper().strip().split('/')[0]
        prefix = ''
        for ch in call:
            if ch.isdigit():
                break
            prefix += ch
        return prefix if prefix else call[:2]

    def _tutti_i_callsign(self):
        result = set()
        for calls in self.memoria_per_prefisso.values():
            result.update(calls)
        return result

    def _carica_memoria(self):
        try:
            if os.path.exists(self.memoria_path):
                with open(self.memoria_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        result = {}
                        for call in data:
                            p = self._estrai_prefisso(call)
                            result.setdefault(p, [])
                            if call not in result[p]:
                                result[p].append(call)
                        return result
                    return {k: list(v) for k, v in data.items()}
        except Exception:
            pass
        return {}

    def _salva_memoria(self):
        try:
            with open(self.memoria_path, 'w', encoding='utf-8') as f:
                json.dump(self.memoria_per_prefisso, f, ensure_ascii=False)
        except Exception:
            pass

    def _azzera_memoria(self):
        self.memoria_per_prefisso = {}
        self._salva_memoria()
        self._aggiorna_lbl_memoria()
        self._aggiorna_info()

    def _aggiorna_lbl_memoria(self):
        if self.lbl_memoria is None:
            return
        n_sent = sum(1 for q in self.qsos
                     if str(q.get('qsl_sent','')).upper().strip() == 'Y')
        n_tot = len(self.qsos)
        if n_sent == 0:
            self.lbl_memoria.configure(text=T("qsl_mem_vuota"), text_color="gray")
        else:
            self.lbl_memoria.configure(
                text=T("qsl_mem_info", n=n_sent) + f" / {n_tot}",
                text_color="#48BB78")

    def _aggiorna_qsl_sent(self):
        """Aggiorna QSL_SENT=Y per i QSO selezionati e salva ADIF."""
        qsos_sel = self._qso_selezionati()
        if not qsos_sel:
            messagebox.showwarning(T("attenzione"), T("qsl_no_match"))
            return
        oggi = datetime.today().strftime("%Y%m%d")
        # Aggiorna i QSO nel log principale (self.qsos)
        calls_sel = set(str(q.get('call','')).upper().strip() for q in qsos_sel)
        n = 0
        for q in self.qsos:
            call = str(q.get('call','')).upper().strip()
            if call in calls_sel:
                q['qsl_sent'] = 'Y'
                q['qslsdate'] = oggi
                n += 1
        # Salva ADIF aggiornato
        if not self.app_ref or not hasattr(self.app_ref, '_scrivi_adif'):
            messagebox.showwarning(T("attenzione"), T("qsl_no_adif"))
            return
        base = os.path.splitext(os.path.basename(self.app_ref.filepath))[0]
        nome_def = base + "_QSL.adif"
        save_path = filedialog.asksaveasfilename(
            title=T("dv_salva_adif_sent"),
            defaultextension=".adif",
            filetypes=[("ADIF files", "*.adif"), ("All files", "*.*")],
            initialfile=nome_def
        )
        if not save_path:
            return
        try:
            self.app_ref._scrivi_adif(save_path, self.app_ref.qsos_caricati)
            self._aggiorna_lbl_memoria()
            self._aggiorna_info()
            self._modifiche_pendenti = False
            messagebox.showinfo(T("successo"),
                T("qsl_sent_ok", n=n, f=os.path.basename(save_path)))
        except Exception as ex:
            messagebox.showerror(T("errore"), f"{T('qsl_sent_err')}{ex}")

    def _apri_gestione_memoria(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title(T("qsl_mem_titolo"))
        dlg.geometry("420x400")
        dlg.resizable(False, True)
        dlg.grab_set()

        ctk.CTkLabel(dlg, text=T("qsl_mem_titolo"),
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)

        frame_lista = ctk.CTkScrollableFrame(dlg, height=260)
        frame_lista.pack(fill="both", expand=True, padx=15, pady=5)

        def ricarica():
            for w in frame_lista.winfo_children():
                w.destroy()
            if not self.memoria_per_prefisso:
                ctk.CTkLabel(frame_lista, text=T("qsl_mem_vuota_msg"),
                             text_color="gray").pack(pady=20)
                return
            fr_head = ctk.CTkFrame(frame_lista, fg_color="#1A365D", corner_radius=4)
            fr_head.pack(fill="x", pady=(0,4))
            ctk.CTkLabel(fr_head, text=T("qsl_mem_prefisso"),
                         font=ctk.CTkFont(weight="bold", size=11),
                         text_color="white", width=80).pack(side="left", padx=10, pady=4)
            ctk.CTkLabel(fr_head, text=T("qsl_mem_quanti"),
                         font=ctk.CTkFont(weight="bold", size=11),
                         text_color="white", width=80).pack(side="left", padx=10)
            for i, (pref, calls) in enumerate(sorted(self.memoria_per_prefisso.items())):
                fr = ctk.CTkFrame(frame_lista,
                                  fg_color="#F7FAFC" if i%2==0 else "transparent",
                                  corner_radius=4)
                fr.pack(fill="x", pady=1)
                ctk.CTkLabel(fr, text=f"  {pref}*", font=ctk.CTkFont(weight="bold"),
                             width=80, anchor="w").pack(side="left", padx=10, pady=5)
                ctk.CTkLabel(fr, text=str(len(calls)),
                             width=80, text_color="#2B6CB0").pack(side="left", padx=10)
                def elimina(p=pref):
                    del self.memoria_per_prefisso[p]
                    self._salva_memoria()
                    self._aggiorna_lbl_memoria()
                    self._aggiorna_info()
                    ricarica()
                ctk.CTkButton(fr, text=T("qsl_mem_elimina"), width=80, height=24,
                              fg_color="#C05621", hover_color="#9C4221",
                              command=elimina).pack(side="right", padx=8, pady=3)
        ricarica()
        ctk.CTkButton(dlg, text=T("chiudi"), command=dlg.destroy,
                      fg_color="#718096", width=100).pack(pady=8)

    def _reset_margini(self):
        """Ripristina i margini ai valori del formato selezionato."""
        fmt = self._formato_attivo()
        self.var_margin_top.set(str(fmt[5]))
        self.var_margin_left.set(str(fmt[4]))
        self.var_gap_v.set(str(fmt[7]))

    def _aggiorna_info(self):
        n = len(self._qso_selezionati())
        fmt = self._formato_attivo()
        cols, rows = fmt[2], fmt[3]
        per_foglio = cols * rows
        fogli = math.ceil(n / per_foglio) if n > 0 else 0
        self.lbl_info.configure(
            text=T("qsl_info", n=n, f=fogli, e=per_foglio))

    def genera(self):
        qsos_sel = self._qso_selezionati()
        if not qsos_sel:
            messagebox.showwarning(T("attenzione"), T("qsl_no_match"))
            return
        nome_def = f"QSL_{self.stazione or 'card'}_etichette.pdf"
        save_path = filedialog.asksaveasfilename(
            title=T("qsl_salva_titolo"),
            defaultextension=".pdf",
            filetypes=[("PDF files","*.pdf")],
            initialfile=nome_def
        )
        if not save_path:
            return
        try:
            # Raggruppa per callsign se richiesto
            if self.var_raggruppa.get():
                qsos_pdf = self._raggruppa_per_call(qsos_sel)
            else:
                qsos_pdf = qsos_sel
            self._genera_pdf(save_path, qsos_pdf)
            n = len(qsos_sel)
            fmt = self._formato_attivo()
            fogli = math.ceil(n / (fmt[2] * fmt[3]))
            # Aggiorna QSL_SENT nel log in memoria
            oggi = datetime.today().strftime("%Y%m%d")
            calls_sel = set(str(q.get('call','')).upper().strip() for q in qsos_sel)
            aggiunti = 0
            for q in self.qsos:
                if str(q.get('call','')).upper().strip() in calls_sel:
                    if str(q.get('qsl_sent','')).upper().strip() != 'Y':
                        q['qsl_sent'] = 'Y'
                        q.setdefault('qslsdate', oggi)
                        aggiunti += 1
            self._aggiorna_lbl_memoria()
            self._aggiorna_info()
            if aggiunti > 0:
                self._modifiche_pendenti = True

            msg = T("qsl_successo", n=n, f=fogli)
            if aggiunti:
                msg += f"\n\n" + T("qsl_stampati_msg", n=aggiunti)
            if messagebox.askyesno(T("successo"), msg):
                os.startfile(os.path.abspath(save_path))
        except Exception as ex:
            messagebox.showerror(T("errore"), f"{T('qsl_errore')}{ex}")

    def _raggruppa_per_call(self, qsos):
        """Raggruppa QSO per callsign in gruppi da max 3.
        Restituisce lista di 'gruppi': ogni gruppo è una lista di QSO."""
        from collections import OrderedDict
        gruppi = OrderedDict()
        for q in qsos:
            call = str(q.get('call','')).upper().strip()
            if call not in gruppi:
                gruppi[call] = []
            gruppi[call].append(q)
        # Ogni gruppo max 3 QSO → se >3 crea piu gruppi
        result = []
        for call, lista in gruppi.items():
            for i in range(0, len(lista), 3):
                result.append(lista[i:i+3])
        return result

    def _genera_pdf(self, path, qsos):
        from reportlab.lib.units import mm
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as cv
        from reportlab.lib.colors import Color

        def rgba(hex_str, alpha=1.0):
            h = hex_str.lstrip("#")
            r,g,b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
            return Color(r,g,b,alpha)

        c1  = self.colori_pdf["primario"]
        c2  = self.colori_pdf["secondario"]
        msg = self.entry_msg.get().strip()

        PW, PH = A4   # portrait A4: 595 x 842 pt

        fmt = self._formato_attivo()
        LW_MM, LH_MM, COLS, ROWS, ML_MM, MT_MM, GH_MM, GV_MM, psize_key = fmt
        page_size = LETTER if psize_key == "LETTER" else A4
        # Usa i margini regolabili dall'utente se presenti
        try:
            MT_MM = float(self.var_margin_top.get())
        except (ValueError, AttributeError):
            pass
        try:
            ML_MM = float(self.var_margin_left.get())
        except (ValueError, AttributeError):
            pass
        try:
            GV_MM = float(self.var_gap_v.get())
        except (ValueError, AttributeError):
            pass
        LW = LW_MM * mm
        LH = LH_MM * mm
        ML = ML_MM * mm
        MT = MT_MM * mm
        GH = GH_MM * mm
        GV = GV_MM * mm

        c = cv.Canvas(path, pagesize=page_size)

        for idx, qso in enumerate(qsos):
            col = idx % COLS
            row = (idx // COLS) % ROWS
            page_pos = idx // (COLS * ROWS)

            # Nuova pagina
            if idx > 0 and idx % (COLS * ROWS) == 0:
                c.showPage()

            # Coordinate angolo inferiore sinistro etichetta
            x0 = ML + col * (LW + GH)
            y0 = PH - MT - (row + 1) * (LH + GV)

            # ── Sfondo etichetta bianco ────────────────────────
            banda_h = 9 * mm
            c.setFillColor(colors.white)
            c.rect(x0, y0, LW, LH, fill=1, stroke=0)

            # ── Callsign stazione ──────────────────────────────
            c.setFillColor(rgba(c1))
            c.setFont("Helvetica-Bold", 9)
            c.drawString(x0 + 2*mm, y0 + LH - 6*mm, self.stazione or "STATION")

            # ── Label "Conferma QSO" ───────────────────────────
            c.setFont("Helvetica", 5)
            c.setFillColor(rgba("#718096"))
            c.drawString(x0 + 2*mm, y0 + LH - banda_h + 1.2*mm, "CONFERMA QSO CON / CONFIRMING QSO WITH:")

            # ── Dati QSO ──────────────────────────────────────
            data = str(qso.get("qso_date",""))
            if len(data)==8: data=f"{data[6:8]}/{data[4:6]}/{data[0:4]}"
            utc = str(qso.get("time_on",""))
            if len(utc)>=4: utc=f"{utc[0:2]}:{utc[2:4]}"
            call_dx  = str(qso.get("call","")).upper()
            banda    = str(qso.get("band","")).upper()
            modo     = str(qso.get("mode","")).upper()
            submode  = str(qso.get("submode","")).upper().strip()
            modo_display = f"{modo}/{submode}" if submode and submode != modo else modo
            rst_s    = str(qso.get("rst_sent","599"))
            rst_r    = str(qso.get("rst_rcvd","599"))
            country  = str(qso.get("country","")).upper()
            grid     = str(qso.get("gridsquare","")).upper()
            sat_name = str(qso.get("sat_name","")).upper().strip()
            stato    = str(qso.get("state","")).upper().strip()
            banda_display = f"{banda} ({sat_name})" if sat_name else banda
            if country in ("UNITED STATES","USA","UNITED STATES OF AMERICA"):
                country_display = f"USA ({stato})" if stato else "USA"
            else:
                country_display = country

            # via manager o bureau
            qsl_via_s = str(qso.get("qsl_via","")).strip().upper()
            _is_usa_s = country in ("UNITED STATES","USA","UNITED STATES OF AMERICA")
            via_display_s = qsl_via_s if qsl_via_s else ("(bureau)" if _ha_bureau(qso) and not _is_usa_s else "")

            # Callsign DX grande
            c.setFillColor(rgba(c1))
            c.setFont("Helvetica-Bold", 11)
            c.drawString(x0 + 2*mm, y0 + LH - banda_h - 5.5*mm, call_dx)

            # via manager/bureau accanto al callsign
            if via_display_s:
                call_w_s = c.stringWidth(call_dx, "Helvetica-Bold", 11)
                if qsl_via_s:
                    c.setFont("Helvetica-BoldOblique", 6)
                    c.setFillColor(rgba("#C05621"))
                else:
                    c.setFont("Helvetica-Oblique", 5.5)
                    c.setFillColor(rgba("#718096"))
                c.drawString(x0+2*mm+call_w_s+2*mm, y0+LH-banda_h-5*mm, f"via {via_display_s}")

            # Riga dati compatta
            c.setFont("Helvetica", 6.5)
            c.setFillColor(rgba("#4A5568"))
            riga1 = f"{data}  {utc}UTC  {banda_display}  {modo_display}"
            c.drawString(x0 + 2*mm, y0 + LH - banda_h - 10*mm, riga1)

            riga2 = f"RST: {rst_s}/{rst_r}"
            if self.var_country.get():
                # Non mostrare country se c'è via manager/bureau
                if country_display and not via_display_s:
                    riga2 += f"   {country_display}"
                if grid:
                    riga2 += f"  [{grid}]"
            c.drawString(x0 + 2*mm, y0 + LH - banda_h - 14.5*mm, riga2)

            # LoTW / eQSL
            if self.var_lotw.get():
                lotw_r = str(qso.get("lotw_qsl_rcvd","")).upper().strip()
                eqsl_r = str(qso.get("eqsl_qsl_rcvd","")).upper().strip()
                c.setFont("Helvetica", 5.5)
                c.setFillColor(rgba("#48BB78") if lotw_r=="Y" else rgba("#A0AEC0"))
                c.drawString(x0 + 2*mm, y0 + 2.5*mm, "LoTW✓" if lotw_r in ("Y","V") else "LoTW-")
                c.setFillColor(rgba("#48BB78") if eqsl_r=="Y" else rgba("#A0AEC0"))
                c.drawString(x0 + 10*mm, y0 + 2.5*mm, "eQSL✓" if eqsl_r=="Y" else "eQSL-")

            # Messaggio personalizzato
            if msg:
                c.setFont("Helvetica-Oblique", 5)
                c.setFillColor(rgba("#718096"))
                c.drawRightString(x0 + LW - 2*mm, y0 + 2.5*mm, msg)

            # ── Bordo tratteggiato ────────────────────────────
            if self.var_border.get():
                c.setStrokeColor(rgba("#A0AEC0", 0.6))
                c.setLineWidth(0.4)
                c.setDash(3, 3)
                c.rect(x0, y0, LW, LH, fill=0, stroke=1)
                c.setDash()

        c.save()

# ─────────────────────────────────────────────
#  Dialogo Grafici Attività per Mese/Anno
# ─────────────────────────────────────────────
