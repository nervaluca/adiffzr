import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import tkinter as tk

class _Tooltip:
    """Tooltip semplice per CustomTkinter."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text   = text
        self.tw     = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tw:
            return
        import tkinter as _tk
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() - 28
        self.tw = tw = _tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        lbl = _tk.Label(tw, text=self.text,
                        background="#1A365D", foreground="white",
                        font=("Arial", 9), relief="solid", borderwidth=1,
                        padx=6, pady=3, wraplength=260, justify="left")
        lbl.pack()

    def hide(self, event=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None

def _tip(widget, text):
    _Tooltip(widget, text)

# ─────────────────────────────────────────────
#  Canvas con footer
# ─────────────────────────────────────────────
