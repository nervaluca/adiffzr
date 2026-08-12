import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import tkinter as tk
import customtkinter as ctk
import theme as TH
import calendar as _cal
from datetime import datetime
from config import T

class _WrapToolbar(ctk.CTkFrame):
    """Toolbar adattiva: una riga che diventa due quando la finestra si stringe."""
    _PX = 4; _PY = 5; _GAP = 4

    def __init__(self, parent, **kw):
        kw.setdefault('corner_radius', 0)
        super().__init__(parent, **kw)
        self._items = []
        self.bind('<Configure>', lambda e: self.after(10, self._relayout))

    def add(self, widget, is_sep=False):
        self._items.append((widget, is_sep))
        widget.pack(side="left", padx=self._GAP//2, pady=self._PY)

    def clear(self):
        for w, _ in self._items:
            try: w.pack_forget(); w.destroy()
            except Exception: pass
        self._items.clear()

    def _relayout(self):
        total_w = self.winfo_width()
        if total_w < 10:
            return
        # Calcola larghezza totale necessaria
        needed = self._PX * 2
        for widget, _ in self._items:
            try: needed += widget.winfo_reqwidth() + self._GAP
            except Exception: pass

        if needed <= total_w:
            # Una riga — usa pack
            for widget, is_sep in self._items:
                widget.place_forget()
                widget.pack(side="left",
                            padx=1 if is_sep else self._GAP//2,
                            pady=self._PY)
            self.configure(height=44)
        else:
            # Due righe — usa place con wrapping
            for widget, _ in self._items:
                widget.pack_forget()
            x = self._PX; y = self._PY; row_h = 0
            for widget, is_sep in self._items:
                try:
                    bw = widget.winfo_reqwidth() + self._GAP
                    bh = widget.winfo_reqheight()
                except Exception:
                    continue
                if not is_sep and x + bw > total_w - self._PX and x > self._PX:
                    x = self._PX; y += row_h + self._GAP; row_h = 0
                widget.place(x=x, y=y)
                x += bw; row_h = max(row_h, bh)
            self.configure(height=y + row_h + self._PY + 2)




class SplashScreen:
    """Splash screen animato con fade in/out.

    Ordine di preferenza per il contenuto:
      1. splash.gif  → animazione (frame riprodotti in loop)
      2. splash.png  → immagine statica
      3. pannello testuale di default
    I file vanno accanto allo script/exe oppure in assets/ o resources/.
    """

    W, H = 520, 300   # dimensioni default (usate se non c'è immagine)

    def __init__(self, root):
        self.root  = root
        self.photo = None
        self._frames = []       # frame GIF (ImageTk.PhotoImage)
        self._durate = []       # durata di ogni frame in ms
        self._frame_idx = 0
        self._anim_after = None

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)          # senza bordo/titolo
        self.win.attributes('-alpha', 0.0)       # inizia invisibile
        self.win.attributes('-topmost', True)

        # Cerca i file splash accanto allo script/exe, in assets/ e resources/
        _gif = self._trova_file(('splash.gif',))
        _png = self._trova_file(('splash.png', 'splash.bmp', 'splash.jpg'))

        w, h = self.W, self.H
        self._label = None

        if _gif:
            # GIF animata
            try:
                w, h = self._carica_gif(_gif)
                self._label = tk.Label(self.win, image=self._frames[0],
                                       borderwidth=0, bg='#0D0D0D')
                self._label.pack()
            except Exception:
                _gif = None  # fallback su png/default

        if not _gif and _png:
            # Immagine statica
            try:
                from PIL import Image, ImageTk
                img = Image.open(_png)
                w, h = img.size
                self.photo = ImageTk.PhotoImage(img)
                tk.Label(self.win, image=self.photo, borderwidth=0,
                         bg='#0D0D0D').pack()
            except Exception:
                _png = None

        if not _gif and not _png:
            # Pannello default
            bg = '#0D0D0D'
            self.win.configure(bg=bg)
            fr = tk.Frame(self.win, bg=bg, width=w, height=h)
            fr.pack(fill='both', expand=True)
            fr.pack_propagate(False)
            tk.Label(fr, text="ADIF FZR", font=('Arial', 38, 'bold'),
                     fg='#90CDF4', bg=bg).place(relx=.5, rely=.35, anchor='center')
            tk.Label(fr, text="Logbook Manager  v2.5",
                     font=('Arial', 14), fg='#CBD5E0', bg=bg
                     ).place(relx=.5, rely=.55, anchor='center')
            tk.Label(fr, text="© IW1FZR  —  iw1fzr.it",
                     font=('Arial', 10), fg='#4A5568', bg=bg
                     ).place(relx=.5, rely=.85, anchor='center')

        # Centra sullo schermo
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        self.win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.win.update()
        if self._frames:
            self._anima()          # avvia il ciclo dei frame GIF
        self._fade(0.0, 1.0)       # fade in

    def _trova_file(self, nomi):
        """Cerca un file tra i nomi dati, accanto allo script e in assets/resources."""
        try:
            base = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            base = os.getcwd()
        basi = [base, os.getcwd()]
        if getattr(sys, "frozen", False):
            basi.insert(0, getattr(sys, "_MEIPASS", base))
        for b in basi:
            for sub in ("", "assets", "resources"):
                for nome in nomi:
                    p = os.path.join(b, sub, nome) if sub else os.path.join(b, nome)
                    if os.path.isfile(p):
                        return p
        return None

    def _carica_gif(self, path):
        """Carica tutti i frame della GIF. Ritorna (larghezza, altezza)."""
        from PIL import Image, ImageTk, ImageSequence
        img = Image.open(path)
        w, h = img.size
        for frame in ImageSequence.Iterator(img):
            fr = frame.convert('RGBA')
            self._frames.append(ImageTk.PhotoImage(fr))
            # durata del frame (ms); default 50ms se non specificata
            self._durate.append(max(20, frame.info.get('duration', 50)))
        return w, h

    def _anima(self):
        """Cicla i frame della GIF in loop."""
        if not self._frames or not self.win.winfo_exists():
            return
        self._label.configure(image=self._frames[self._frame_idx])
        durata = self._durate[self._frame_idx]
        self._frame_idx = (self._frame_idx + 1) % len(self._frames)
        self._anim_after = self.root.after(durata, self._anima)

    def _fade(self, alpha, target, step=0.07):
        alpha = round(alpha + step * (1 if target > alpha else -1), 2)
        alpha = max(0.0, min(1.0, alpha))
        try:
            self.win.attributes('-alpha', alpha)
        except Exception:
            return
        if abs(alpha - target) > 0.01:
            self.root.after(20, lambda: self._fade(alpha, target, step))
        elif target == 0.0:
            if self._anim_after:
                try: self.root.after_cancel(self._anim_after)
                except Exception: pass
            self.win.destroy()

    def close(self):
        """Avvia il fade out e distrugge la finestra."""
        self._fade(1.0, 0.0)


class CalendarPopup(ctk.CTkToplevel):
    """A simple month-view calendar popup that writes dd/mm/yyyy into a CTkEntry."""

    def __init__(self, parent, entry_widget, initial_date=None):
        super().__init__(parent)
        self.entry_widget = entry_widget
        self.overrideredirect(True)
        self.grab_set()
        self.attributes("-topmost", True)

        today = datetime.today()
        if initial_date:
            self._year, self._month = initial_date.year, initial_date.month
        else:
            self._year, self._month = today.year, today.month

        self._build()
        # Position near the entry widget
        self.update_idletasks()
        x = entry_widget.winfo_rootx()
        y = entry_widget.winfo_rooty() + entry_widget.winfo_height() + 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        for w in self.winfo_children():
            w.destroy()

        frame = ctk.CTkFrame(self, corner_radius=8, border_width=1, border_color="#CBD5E0")
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        # Navigation header
        nav = ctk.CTkFrame(frame, fg_color="transparent")
        nav.pack(fill="x", padx=4, pady=4)
        ctk.CTkButton(nav, text="◀", width=30, height=26, fg_color=TH.PRIMARY,
                      command=self._prev_month).pack(side="left", padx=2)
        nomi_mesi = T("nomi_mesi_it")
        mese_nome = nomi_mesi[self._month - 1] if isinstance(nomi_mesi, list) else str(self._month)
        self._lbl_header = ctk.CTkLabel(nav, text=f"{mese_nome} {self._year}",
                                         font=ctk.CTkFont(size=12, weight="bold"))
        self._lbl_header.pack(side="left", expand=True)
        ctk.CTkButton(nav, text="▶", width=30, height=26, fg_color=TH.PRIMARY,
                      command=self._next_month).pack(side="right", padx=2)

        # Day-of-week headers
        days_frame = ctk.CTkFrame(frame, fg_color="transparent")
        days_frame.pack(fill="x", padx=4)
        day_names = ["Lu","Ma","Me","Gi","Ve","Sa","Do"] if LINGUA == "IT" else ["Mo","Tu","We","Th","Fr","Sa","Su"]
        for i, dn in enumerate(day_names):
            ctk.CTkLabel(days_frame, text=dn, width=32, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#4A5568").grid(row=0, column=i, padx=1)

        # Day grid
        grid_frame = ctk.CTkFrame(frame, fg_color="transparent")
        grid_frame.pack(fill="x", padx=4, pady=(0,4))
        cal_matrix = _cal.monthcalendar(self._year, self._month)
        today = datetime.today()
        for r, week in enumerate(cal_matrix):
            for c, day in enumerate(week):
                if day == 0:
                    ctk.CTkLabel(grid_frame, text="", width=32, height=26).grid(row=r, column=c, padx=1, pady=1)
                else:
                    is_today = (day == today.day and self._month == today.month and self._year == today.year)
                    fg = "#2B6CB0" if is_today else "transparent"
                    tc = "white" if is_today else None
                    btn = ctk.CTkButton(grid_frame, text=str(day), width=32, height=26,
                                        fg_color=fg, hover_color="#BEE3F8",
                                        text_color=tc if tc else ("#1A202C", "#E2E8F0"),
                                        font=ctk.CTkFont(size=10),
                                        command=lambda d=day: self._select(d))
                    btn.grid(row=r, column=c, padx=1, pady=1)

        # Close button
        ctk.CTkButton(frame, text=T("chiudi"), fg_color="#718096", height=24,
                      width=80, font=ctk.CTkFont(size=10),
                      command=self.destroy).pack(pady=(0,4))

    def _prev_month(self):
        if self._month == 1:
            self._month, self._year = 12, self._year - 1
        else:
            self._month -= 1
        self._build()

    def _next_month(self):
        if self._month == 12:
            self._month, self._year = 1, self._year + 1
        else:
            self._month += 1
        self._build()

    def _select(self, day):
        date_str = f"{day:02d}/{self._month:02d}/{self._year}"
        self.entry_widget.delete(0, "end")
        self.entry_widget.insert(0, date_str)
        self.destroy()


# ─────────────────────────────────────────────
#  Dialogo Filtri
# ─────────────────────────────────────────────
