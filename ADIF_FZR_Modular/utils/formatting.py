import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import os
import customtkinter as ctk
from tkinter import filedialog
from config import T

def chiedi_cartella_output(parent, nome_file, filepath_sorgente=None):
    """Chiede se usare cartella dedicata, restituisce il path completo o "" per dialogo standard."""
    dlg = ctk.CTkToplevel(parent)
    dlg.title(T("cartella_crea"))
    dlg.geometry("420x185")
    dlg.resizable(False, False)
    dlg.grab_set()
    dlg.attributes("-topmost", True)

    ctk.CTkLabel(dlg, text=T("cartella_dedicata"),
                 font=ctk.CTkFont(size=12, weight="bold"),
                 wraplength=380).pack(pady=14, padx=20)

    risultato = [None]

    def usa_adif_output():
        if filepath_sorgente:
            base_dir = os.path.dirname(os.path.abspath(filepath_sorgente))
        else:
            base_dir = os.path.expanduser("~")
        cartella = os.path.join(base_dir, "ADIF_Output")
        os.makedirs(cartella, exist_ok=True)
        risultato[0] = os.path.join(cartella, nome_file)
        dlg.destroy()

    def scegli_cartella():
        dlg.withdraw()
        cartella = filedialog.askdirectory(title=T("dv_scegli_cartella"))
        if cartella:
            risultato[0] = os.path.join(cartella, nome_file)
        else:
            risultato[0] = ""
        dlg.destroy()

    def no_cartella():
        risultato[0] = ""
        dlg.destroy()

    frame_btn = ctk.CTkFrame(dlg, fg_color="transparent")
    frame_btn.pack(fill="x", padx=15, pady=6)
    ctk.CTkButton(frame_btn, text=T("cartella_crea"),
                  fg_color="#2B6CB0", height=30,
                  command=usa_adif_output).pack(fill="x", pady=2)
    ctk.CTkButton(frame_btn, text=T("cartella_scegli"),
                  fg_color="#276749", height=30,
                  command=scegli_cartella).pack(fill="x", pady=2)
    ctk.CTkButton(frame_btn, text=T("cartella_no"),
                  fg_color="#718096", height=30,
                  command=no_cartella).pack(fill="x", pady=2)

    dlg.wait_window()
    return risultato[0]

