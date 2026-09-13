# -*- coding: utf-8 -*-
"""
was_status.py — Add-on WAS (Worked All States) per ADIF FZR.

Mostra lo stato dell'award ARRL WAS incrociando i 50 stati USA con:
  - le bande (viste Mixed / Phone / CW / Digitale, satellite escluso)
  - i satelliti (vista Satellite, WAS Satellite a sé)
e distingue il livello di conferma: LoTW, QSL cartacea, eQSL, solo lavorato.

Nessuna dipendenza esterna oltre a customtkinter (gia' usato dall'app).
Colloca il file in gui/  e aprilo passando la lista dei QSO gia' in memoria.

Integrazione tipica (da un pulsante o voce di menu):

    from gui.was_status import WASStatusWindow
    WASStatusWindow(self, qsos=self.qso_records)   # self = finestra/app principale

Dove `qso_records` e' una lista di dizionari con le chiavi ADIF in minuscolo
(state, dxcc, band, mode, prop_mode, sat_name, lotw_qsl_rcvd, eqsl_qsl_rcvd,
qsl_rcvd). Se la tua struttura interna e' diversa, passa un adattatore:

    WASStatusWindow(self, qsos=self.qso_records, getter=lambda r, k: r.campo(k))

In alternativa, senza QSO in memoria, puoi puntare a un file ADIF:

    WASStatusWindow(self, adif_path=r"C:\\path\\log.adi")
"""

import re

try:
    import tkinter as tk
    import customtkinter as ctk
except Exception:  # pragma: no cover - consente il test della logica senza GUI
    tk = None
    ctk = None

# --------------------------------------------------------------------------- #
#  Dati di riferimento
# --------------------------------------------------------------------------- #
STATE_NAMES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
    'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
    'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
    'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
    'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
    'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
    'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
    'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
    'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
    'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
    'WI': 'Wisconsin', 'WY': 'Wyoming',
}
US_STATES = set(STATE_NAMES)
US_DXCC = {'291', '6', '110'}  # USA contiguo, Alaska, Hawaii
BAND_ORDER = ['160m', '80m', '60m', '40m', '30m', '20m', '17m',
              '15m', '12m', '10m', '6m', '2m', '70cm']
PHONE_MODES = {'SSB', 'USB', 'LSB', 'AM', 'FM', 'PHONE', 'DV', 'C4FM'}
GROUPS = ['mixed', 'phone', 'cw', 'digital', 'sat']
GROUP_LABEL = {'mixed': 'Mixed', 'phone': 'Phone', 'cw': 'CW',
               'digital': 'Digitale', 'sat': 'Satellite'}

# --------------------------------------------------------------------------- #
#  Logica di calcolo (indipendente dalla GUI, testabile a parte)
# --------------------------------------------------------------------------- #
def _default_getter(rec, key):
    """Accesso tollerante a dict con chiavi ADIF minuscole (o maiuscole)."""
    if key in rec:
        return rec[key]
    return rec.get(key.upper(), rec.get(key.lower(), ''))


def _mode_group(mode):
    m = (mode or '').upper()
    if m in PHONE_MODES:
        return 'phone'
    if m == 'CW':
        return 'cw'
    return 'digital'


def _newcell():
    return {'w': 0, 'l': 0, 'e': 0, 'p': 0}


def compute_was(qsos, getter=_default_getter):
    """
    Ritorna una struttura pronta per la GUI:
      {
        'bands': [...],                     # bande terrestri presenti
        'sat_names': [...],                 # satelliti presenti (ordinati per uso)
        'data': {grp: {ST: {col: cell}}},   # grp in mixed/phone/cw/digital -> col=banda
        'sat':  {ST: {satname: cell}},      # vista satellite
        'total_terr': int, 'total_sat': int, 'total_log': int,
      }
    cell = {'w': n_qso, 'l': lotw01, 'e': eqsl01, 'p': cartacea01}
    """
    g = getter
    terr = {grp: {s: {b: _newcell() for b in BAND_ORDER}
                  for s in US_STATES} for grp in ('phone', 'cw', 'digital')}
    sat = {s: {} for s in US_STATES}
    sat_count = {}
    terr_bands = set()
    n_terr = n_sat = 0

    for r in qsos:
        st = str(g(r, 'state') or '').upper().strip()
        if st not in US_STATES:
            continue
        if str(g(r, 'dxcc') or '').strip() not in US_DXCC:
            continue
        lotw = str(g(r, 'lotw_qsl_rcvd') or '').upper() in ('V', 'Y')
        eqsl = str(g(r, 'eqsl_qsl_rcvd') or '').upper() == 'Y'
        paper = str(g(r, 'qsl_rcvd') or '').upper() == 'Y'

        if str(g(r, 'prop_mode') or '').upper() == 'SAT':
            sn = (str(g(r, 'sat_name') or '').upper().strip() or '(sconosciuto)')
            cell = sat[st].setdefault(sn, _newcell())
            cell['w'] += 1
            cell['l'] |= lotw; cell['e'] |= eqsl; cell['p'] |= paper
            sat_count[sn] = sat_count.get(sn, 0) + 1
            n_sat += 1
            continue

        band = str(g(r, 'band') or '').lower().strip()
        if band not in BAND_ORDER:
            continue
        terr_bands.add(band)
        grp = _mode_group(g(r, 'mode'))
        c = terr[grp][st][band]
        c['w'] += 1
        c['l'] |= lotw; c['e'] |= eqsl; c['p'] |= paper
        n_terr += 1

    bands = [b for b in BAND_ORDER if b in terr_bands]

    def merge(cells):
        o = _newcell()
        for c in cells:
            o['w'] += c['w']; o['l'] |= c['l']; o['e'] |= c['e']; o['p'] |= c['p']
        return o

    mixed = {s: {b: merge([terr[grp][s][b] for grp in ('phone', 'cw', 'digital')])
                 for b in bands} for s in US_STATES}
    data = {'mixed': mixed}
    for grp in ('phone', 'cw', 'digital'):
        data[grp] = {s: {b: terr[grp][s][b] for b in bands} for s in US_STATES}

    sat_names = sorted(sat_count, key=lambda x: -sat_count[x])
    satfull = {s: {sn: (sat[s].get(sn) or _newcell()) for sn in sat_names}
               for s in US_STATES}

    return {'bands': bands, 'sat_names': sat_names, 'data': data, 'sat': satfull,
            'total_terr': n_terr, 'total_sat': n_sat, 'total_log': len(qsos)}


# --------------------------------------------------------------------------- #
#  Parser ADIF minimale (fallback quando non hai i QSO in memoria)
# --------------------------------------------------------------------------- #
_FIELD_RE = re.compile(r'<([A-Za-z0-9_]+):(\d+)(?::[^>]*)?>', re.I)


def parse_adif(path):
    """Parsing ADIF essenziale -> lista di dict con chiavi minuscole."""
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        text = fh.read()
    low = text.lower()
    i = low.find('<eoh>')
    if i != -1:
        text = text[i + 5:]
    out = []
    for rec in re.split(r'<eor>', text, flags=re.I):
        rec = rec.strip()
        if not rec:
            continue
        f = {}
        for m in _FIELD_RE.finditer(rec):
            f[m.group(1).lower()] = rec[m.end():m.end() + int(m.group(2))]
        if f:
            out.append(f)
    return out


# --------------------------------------------------------------------------- #
#  Helper di stato cella
# --------------------------------------------------------------------------- #
def cell_status(cell, strict):
    """Ritorna 'none'|'work'|'eqsl'|'paper'|'lotw' (best status)."""
    if not cell or not cell['w']:
        return 'none'
    if cell['l']:
        return 'lotw'
    if cell['p']:
        return 'paper'
    if not strict and cell['e']:
        return 'eqsl'
    return 'work'


def arrl_ok(cell):
    return bool(cell and (cell['l'] or cell['p']))


def any_cell(cols_cells):
    o = _newcell()
    for c in cols_cells:
        o['w'] += c['w']; o['l'] |= c['l']; o['e'] |= c['e']; o['p'] |= c['p']
    return o


# --------------------------------------------------------------------------- #
#  Finestra CustomTkinter
# --------------------------------------------------------------------------- #
if ctk is not None:

    # palette (dark)
    COL = {
        'lotw': '#178a4e', 'paper': '#0f8f86', 'eqsl': '#2f6fed',
        'work': '#e39321', 'none': '#2a2f37',
        'grid': '#3a414b', 'panel': '#171b21', 'panel2': '#1f242c',
        'txt': '#e6ebf0', 'muted': '#8a97a5', 'lcd': '#ffc861',
        'celltxt': '#ffffff',
    }
    LETTER = {'none': '', 'work': '\u00b7', 'eqsl': 'E', 'paper': 'C', 'lotw': 'L'}

    # geometria matrice
    ST_W = 158     # colonna stato
    COL_W = 46     # colonna dato
    ANY_W = 54
    ROW_H = 22
    HDR_H = 26

    class WASStatusWindow(ctk.CTkToplevel):
        def __init__(self, master=None, qsos=None, adif_path=None,
                     getter=_default_getter, title="WAS · Worked All States"):
            super().__init__(master)
            self.title(title)
            self.geometry("900x760")
            self.minsize(720, 560)

            # Resta in primo piano rispetto all'app principale.
            try:
                self.transient(master)
            except Exception:
                pass
            try:
                self.attributes("-topmost", True)
            except Exception:
                pass
            # CTk inizializza la finestra in modo asincrono: rialzala e
            # riporta il topmost poco dopo, così non finisce dietro l'app.
            self.after(200, self.lift)
            self.after(250, lambda: self.attributes("-topmost", True))

            if qsos is None:
                if adif_path:
                    try:
                        qsos = parse_adif(adif_path)
                    except Exception as ex:
                        qsos = []
                        self._fatal(f"Impossibile leggere l'ADIF:\n{ex}")
                        return
                else:
                    qsos = []
            self.model = compute_was(qsos, getter)
            self.group = 'mixed'
            self.strict = tk.BooleanVar(value=False)
            self.col_filter = None
            self._tip = None

            self._build()
            self._render()

        # ---- costruzione layout ---- #
        def _build(self):
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(3, weight=1)

            # pannello riepilogo
            top = ctk.CTkFrame(self, fg_color=COL['panel'], corner_radius=12)
            top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
            top.grid_columnconfigure(1, weight=1)
            self.big = ctk.CTkLabel(top, text="--/50",
                                    font=ctk.CTkFont(size=40, weight="bold"),
                                    text_color=COL['lcd'])
            self.big.grid(row=0, column=0, rowspan=2, padx=(18, 14), pady=14)
            self.big_lbl = ctk.CTkLabel(top, text="stati validi ARRL",
                                        font=ctk.CTkFont(size=13),
                                        text_color=COL['muted'], anchor="w")
            self.big_lbl.grid(row=0, column=1, sticky="sw", pady=(16, 0))
            self.meta = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=12),
                                     text_color=COL['muted'], anchor="w",
                                     justify="left")
            self.meta.grid(row=1, column=1, sticky="nw", pady=(0, 14))

            # controlli: tab modi + switch
            ctrl = ctk.CTkFrame(self, fg_color="transparent")
            ctrl.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
            self.tabs = ctk.CTkSegmentedButton(
                ctrl, values=[GROUP_LABEL[g] for g in GROUPS],
                command=self._on_tab)
            self.tabs.set(GROUP_LABEL[self.group])
            self.tabs.pack(side="left")
            ctk.CTkSwitch(ctrl, text="Regola ARRL: solo LoTW e cartacea",
                          variable=self.strict, command=self._render,
                          onvalue=True, offvalue=False).pack(side="left", padx=16)

            # striscia colonne (endorsement per banda / satellite)
            self.strip = ctk.CTkScrollableFrame(self, height=58,
                                                fg_color="transparent",
                                                orientation="horizontal")
            self.strip.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 4))

            # matrice: header fisso + canvas scrollabile
            matwrap = ctk.CTkFrame(self, fg_color=COL['panel2'], corner_radius=12)
            matwrap.grid(row=3, column=0, sticky="nsew", padx=12, pady=(2, 6))
            matwrap.grid_columnconfigure(0, weight=1)
            matwrap.grid_rowconfigure(1, weight=1)
            self.hdr = tk.Canvas(matwrap, height=HDR_H, bg=COL['panel'],
                                 highlightthickness=0)
            self.hdr.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
            self.body = tk.Canvas(matwrap, bg=COL['panel2'], highlightthickness=0)
            self.body.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
            sb = ctk.CTkScrollbar(matwrap, command=self.body.yview)
            sb.grid(row=1, column=1, sticky="ns", pady=(0, 6))
            self.body.configure(yscrollcommand=sb.set)
            self.body.bind("<Motion>", self._hover)
            self.body.bind("<Leave>", lambda e: self._hide_tip())
            self.body.bind("<MouseWheel>",
                           lambda e: self.body.yview_scroll(int(-e.delta / 120), "units"))

            # legenda
            leg = ctk.CTkFrame(self, fg_color="transparent")
            leg.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))
            for key, txt in [('lotw', 'LoTW · valido ARRL'),
                             ('paper', 'Cartacea · valido ARRL'),
                             ('eqsl', 'eQSL · non valido award'),
                             ('work', 'Lavorato'),
                             ('none', 'Non lavorato')]:
                item = ctk.CTkFrame(leg, fg_color="transparent")
                item.pack(side="left", padx=(0, 14))
                sw = tk.Canvas(item, width=14, height=14, highlightthickness=0,
                               bg=COL[key])
                sw.pack(side="left", padx=(0, 5))
                ctk.CTkLabel(item, text=txt, font=ctk.CTkFont(size=11),
                             text_color=COL['muted']).pack(side="left")

        def _fatal(self, msg):
            ctk.CTkLabel(self, text=msg, text_color="#e06a6a").pack(padx=20, pady=20)

        # ---- colonne correnti ---- #
        def _cols(self):
            return self.model['sat_names'] if self.group == 'sat' else self.model['bands']

        def _cell(self, st, col):
            if self.group == 'sat':
                return self.model['sat'][st][col]
            return self.model['data'][self.group][st][col]

        def _any(self, st):
            return any_cell([self._cell(st, c) for c in self._cols()])

        # ---- eventi ---- #
        def _on_tab(self, label):
            for g, lab in GROUP_LABEL.items():
                if lab == label:
                    self.group = g
                    break
            self.col_filter = None
            self._render()

        def _toggle_filter(self, col):
            self.col_filter = None if self.col_filter == col else col
            self._render()

        # ---- rendering ---- #
        def _render(self):
            strict = self.strict.get()
            cols = self._cols()

            # hero
            valid = sum(1 for s in self.model_states() if arrl_ok(self._any(s)))
            self.big.configure(text=f"{valid}/50")
            self.big_lbl.configure(
                text=("stati validi ARRL — WAS Satellite" if self.group == 'sat'
                      else f"stati validi ARRL — vista {GROUP_LABEL[self.group]}"))
            self.meta.configure(
                text=(f"Log: {self.model['total_terr']} QSO terrestri + "
                      f"{self.model['total_sat']} sat  ·  "
                      f"{self.model['total_log']} totali"))

            # striscia colonne
            for w in self.strip.winfo_children():
                w.destroy()
            for col in cols:
                ok = sum(1 for s in self.model_states() if arrl_ok(self._cell(s, col)))
                border = COL['lotw'] if ok == 50 else COL['grid']
                fg = "#12321f" if ok == 50 else COL['panel']
                sel = (self.col_filter == col)
                chip = ctk.CTkButton(
                    self.strip, width=76, height=44,
                    fg_color=fg, hover_color=COL['panel2'],
                    border_width=2 if not sel else 2,
                    border_color=("#c8452e" if sel else border),
                    corner_radius=8, command=lambda c=col: self._toggle_filter(c),
                    text=f"{col}\n{ok}/50",
                    font=ctk.CTkFont(family="JetBrains Mono", size=11,
                                     weight="bold"),
                    text_color=COL['lotw'] if ok == 50 else COL['txt'])
                chip.pack(side="left", padx=3, pady=4)

            self._draw_header(cols)
            self._draw_body(cols, strict)

        def model_states(self):
            return sorted(US_STATES)

        def _draw_header(self, cols):
            c = self.hdr
            c.delete("all")
            x = ST_W
            c.create_text(12, HDR_H / 2, text="Stato", anchor="w",
                          fill=COL['muted'],
                          font=("JetBrains Mono", 10, "bold"))
            for col in cols:
                dim = self.col_filter and self.col_filter != col
                c.create_text(x + COL_W / 2, HDR_H / 2, text=col,
                              fill=(COL['grid'] if dim else COL['muted']),
                              font=("JetBrains Mono", 9, "bold"))
                x += COL_W
            any_hdr = "SAT" if self.group == 'sat' else "ALL"
            c.create_rectangle(x, 0, x + ANY_W, HDR_H, fill="#20272f", outline="")
            c.create_text(x + ANY_W / 2, HDR_H / 2, text=any_hdr,
                          fill=COL['muted'], font=("JetBrains Mono", 9, "bold"))
            total_w = ST_W + len(cols) * COL_W + ANY_W
            c.configure(scrollregion=(0, 0, total_w, HDR_H))

        def _draw_body(self, cols, strict):
            c = self.body
            c.delete("all")
            self._cellmap = {}  # (col_index,row_index) -> (st,col,cell)
            states = self.model_states()
            total_w = ST_W + len(cols) * COL_W + ANY_W
            total_h = len(states) * ROW_H

            for ri, st in enumerate(states):
                y = ri * ROW_H
                # etichetta stato
                c.create_text(12, y + ROW_H / 2,
                              text=st, anchor="w", fill=COL['txt'],
                              font=("JetBrains Mono", 10, "bold"))
                c.create_text(40, y + ROW_H / 2,
                              text=STATE_NAMES[st], anchor="w",
                              fill=COL['muted'], font=("Segoe UI", 9))
                x = ST_W
                for col in cols:
                    cell = self._cell(st, col)
                    stat = cell_status(cell, strict)
                    dim = self.col_filter and self.col_filter != col
                    fill = COL[stat]
                    if dim:
                        fill = COL['none']
                    c.create_rectangle(x, y, x + COL_W, y + ROW_H,
                                       fill=fill, outline=COL['panel2'], width=1)
                    if LETTER[stat] and not dim:
                        c.create_text(x + COL_W / 2, y + ROW_H / 2,
                                      text=LETTER[stat], fill=COL['celltxt'],
                                      font=("JetBrains Mono", 9, "bold"))
                    self._cellmap[(x, y)] = (st, col, cell)
                    x += COL_W
                # colonna ANY
                acell = self._any(st)
                astat = cell_status(acell, strict)
                c.create_rectangle(x, y, x + ANY_W, y + ROW_H,
                                   fill=COL[astat], outline=COL['panel'], width=1)
                if LETTER[astat]:
                    c.create_text(x + ANY_W / 2, y + ROW_H / 2, text=LETTER[astat],
                                  fill=COL['celltxt'],
                                  font=("JetBrains Mono", 9, "bold"))
                anylabel = "qualsiasi sat" if self.group == 'sat' else "tutte le bande"
                self._cellmap[(x, y)] = (st, anylabel, acell)

            c.configure(scrollregion=(0, 0, total_w, total_h))
            self._cols_x = [ST_W + i * COL_W for i in range(len(cols))] + \
                           [ST_W + len(cols) * COL_W]

        # ---- tooltip ---- #
        def _hover(self, e):
            x = self.body.canvasx(e.x)
            y = self.body.canvasy(e.y)
            if x < ST_W:
                self._hide_tip(); return
            ri = int(y // ROW_H)
            # trova la colonna
            col_x = None
            for cx in getattr(self, '_cols_x', []):
                w = ANY_W if cx == self._cols_x[-1] else COL_W
                if cx <= x < cx + w:
                    col_x = cx; break
            if col_x is None:
                self._hide_tip(); return
            key = (col_x, ri * ROW_H)
            info = self._cellmap.get(key)
            if not info or not info[2]['w']:
                self._hide_tip(); return
            st, col, cell = info
            txt = (f"{st} · {STATE_NAMES[st]} · {col}\n"
                   f"QSO: {cell['w']}    "
                   f"LoTW: {'si' if cell['l'] else '—'}   "
                   f"Cart: {'si' if cell['p'] else '—'}   "
                   f"eQSL: {'si' if cell['e'] else '—'}")
            self._show_tip(e.x_root, e.y_root, txt)

        def _show_tip(self, xr, yr, txt):
            if self._tip is None:
                self._tip = tk.Toplevel(self)
                self._tip.wm_overrideredirect(True)
                self._tip.attributes("-topmost", True)
                self._tiplbl = tk.Label(self._tip, justify="left",
                                        bg=COL['panel'], fg=COL['txt'],
                                        font=("JetBrains Mono", 9),
                                        padx=8, pady=5, bd=1, relief="solid")
                self._tiplbl.pack()
            self._tiplbl.configure(text=txt)
            self._tip.wm_geometry(f"+{xr + 14}+{yr + 14}")
            self._tip.deiconify()

        def _hide_tip(self):
            if self._tip is not None:
                self._tip.withdraw()


# --------------------------------------------------------------------------- #
#  Avvio autonomo per test:  python was_status.py  path\log.adi
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if ctk is None:
        raise SystemExit("customtkinter non installato.")
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.withdraw()
    WASStatusWindow(root, adif_path=path)
    root.mainloop()
