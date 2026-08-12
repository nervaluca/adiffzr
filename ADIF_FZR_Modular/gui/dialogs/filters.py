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
from config import T

class FiltriDialog(ctk.CTkToplevel):
    # Satelliti noti — usati nel filtro rapido
    SAT_NOTI = [
        "QO-100", "RS-44", "AO-91", "AO-92", "AO-7", "AO-73",
        "SO-50", "FO-29", "JO-97", "IO-117", "CAS-4A", "CAS-4B",
        "XW-2A", "XW-2B", "XW-2C", "XW-2D", "XW-2F",
        "PO-101", "DIWATA-2", "TEVEL-1", "ISS",
    ]

    def __init__(self, parent, qsos_tutti):
        super().__init__(parent)
        self.title(T("filtri_titolo"))
        self.geometry("480x520")
        self.resizable(False, False)
        self.grab_set()
        self.qsos_tutti = qsos_tutti
        self.risultato = None

        bande_disponibili = sorted(set(str(q.get('band', '')).upper().strip() for q in qsos_tutti if q.get('band', '')))
        modi_disponibili  = sorted(set(str(q.get('mode', '')).upper().strip() for q in qsos_tutti if q.get('mode', '')))
        # Satelliti presenti nel log + noti
        sat_nel_log = sorted(set(
            str(q.get('sat_name','')).upper().strip()
            for q in qsos_tutti
            if q.get('sat_name','') and str(q.get('prop_mode','')).upper() == 'SAT'
        ))
        sat_options = [T("filtri_tutti")] + sorted(set(self.SAT_NOTI) | set(sat_nel_log))

        date_valide = [str(q.get('qso_date','')).strip() for q in qsos_tutti if len(str(q.get('qso_date','')).strip()) == 8]
        data_min = min(date_valide) if date_valide else "19000101"
        data_max = max(date_valide) if date_valide else "29991231"

        def fmt(d):
            return f"{d[6:8]}/{d[4:6]}/{d[0:4]}" if len(d) == 8 else d

        ctk.CTkLabel(self, text=T("filtri_header"), font=ctk.CTkFont(size=16, weight="bold")).pack(pady=12)

        frame = ctk.CTkFrame(self)
        frame.pack(padx=20, fill="both", expand=True)

        # Intervallo date
        ctk.CTkLabel(frame, text=T("filtri_date"), font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10,2))
        ctk.CTkLabel(frame, text=T("filtri_da")).grid(row=1, column=0, sticky="e", padx=10)
        self.entry_da = ctk.CTkEntry(frame, width=130)
        self.entry_da.insert(0, fmt(data_min))
        self.entry_da.grid(row=1, column=1, sticky="w", padx=10, pady=4)
        ctk.CTkLabel(frame, text=T("filtri_a")).grid(row=2, column=0, sticky="e", padx=10)
        self.entry_a = ctk.CTkEntry(frame, width=130)
        self.entry_a.insert(0, fmt(data_max))
        self.entry_a.grid(row=2, column=1, sticky="w", padx=10, pady=4)

        # Banda
        ctk.CTkLabel(frame, text=T("filtri_banda"), font=ctk.CTkFont(weight="bold")).grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(10,2))
        self.var_banda = ctk.StringVar(value=T("filtri_tutte"))
        ctk.CTkOptionMenu(frame, variable=self.var_banda,
                          values=[T("filtri_tutte")] + bande_disponibili,
                          width=200).grid(row=4, column=0, columnspan=2, padx=10, pady=4, sticky="w")

        # Modo
        ctk.CTkLabel(frame, text=T("filtri_modo_op"), font=ctk.CTkFont(weight="bold")).grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=(10,2))
        self.var_modo = ctk.StringVar(value=T("filtri_tutti"))
        ctk.CTkOptionMenu(frame, variable=self.var_modo,
                          values=[T("filtri_tutti")] + modi_disponibili,
                          width=200).grid(row=6, column=0, columnspan=2, padx=10, pady=4, sticky="w")

        # Satellite
        ctk.CTkLabel(frame, text="🛰 Satellite", font=ctk.CTkFont(weight="bold")).grid(row=7, column=0, columnspan=2, sticky="w", padx=10, pady=(10,2))
        frame_sat = ctk.CTkFrame(frame, fg_color="transparent")
        frame_sat.grid(row=8, column=0, columnspan=2, padx=10, pady=4, sticky="w")
        self.var_sat = ctk.StringVar(value=T("filtri_tutti"))
        self._opt_sat = ctk.CTkOptionMenu(frame_sat, variable=self.var_sat,
                          values=sat_options, width=180)
        self._opt_sat.pack(side="left", padx=(0,8))
        # Campo libero per satelliti non in lista
        self.entry_sat = ctk.CTkEntry(frame_sat, width=100,
                                       placeholder_text=T("dv_o_scrivi"))
        self.entry_sat.pack(side="left")

        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(pady=12, fill="x", padx=20)
        ctk.CTkButton(frame_btn, text=T("filtri_applica"), command=self.applica,
                      fg_color=TH.PRIMARY).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(frame_btn, text=T("filtri_nessuno"), command=self.nessun_filtro,
                      fg_color="#718096").pack(side="left", expand=True, padx=5)

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

    def applica(self):
        da    = self._parse_data(self.entry_da.get())
        a     = self._parse_data(self.entry_a.get())
        banda = self.var_banda.get()
        modo  = self.var_modo.get()
        # Satellite: priorità al campo libero, poi al dropdown
        sat_libero = self.entry_sat.get().strip().upper() if hasattr(self,'entry_sat') else ""
        sat_drop   = self.var_sat.get() if hasattr(self,'var_sat') else T("filtri_tutti")
        sat_filtro = sat_libero or (sat_drop if sat_drop != T("filtri_tutti") else "")

        filtrati = []
        for q in self.qsos_tutti:
            d_raw = str(q.get('qso_date', '')).strip()
            if len(d_raw) == 8:
                try:
                    d_qso = datetime.strptime(d_raw, "%Y%m%d")
                except ValueError:
                    d_qso = None
            else:
                d_qso = None

            if da and d_qso and d_qso < da:
                continue
            if a and d_qso and d_qso > a:
                continue
            if banda != T("filtri_tutte") and str(q.get('band','...')).upper().strip() != banda:
                continue
            if modo != T("filtri_tutti") and str(q.get('mode','...')).upper().strip() != modo:
                continue
            if sat_filtro:
                sat_q = str(q.get('sat_name','')).upper().strip()
                if sat_filtro not in sat_q:
                    continue
            filtrati.append(q)

        self.risultato = filtrati
        self.destroy()

    def nessun_filtro(self):
        self.risultato = self.qsos_tutti
        self.destroy()


# ─────────────────────────────────────────────
#  Dialogo colori PDF
# ─────────────────────────────────────────────
