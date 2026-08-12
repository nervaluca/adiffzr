import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import os
import re
import adif_io
import customtkinter as ctk
import theme as TH
from tkinter import filedialog, messagebox
import tkinter.ttk as _ttk
from config import T

class UnisciDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title(T("unisci_titolo"))
        self.geometry("640x680")
        self.resizable(False, True)
        self.minsize(640, 580)
        self.grab_set()
        self.files = []
        self.risultato_qsos = None
        self.risultato_nome = None

        ctk.CTkLabel(self, text=T("unisci_header"),
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=10)

        # Pulsanti FISSI in fondo
        frame_ok = ctk.CTkFrame(self, fg_color="transparent")
        frame_ok.pack(side="bottom", pady=8, fill="x", padx=20)
        ctk.CTkButton(frame_ok, text=T("unisci_e_carica"),
                      command=self.unisci,
                      fg_color=TH.SUCCESS_H, hover_color=TH.SUCCESS, height=38
                      ).pack(side="left", expand=True, padx=(0,6), fill="x")
        ctk.CTkButton(frame_ok, text=T("unisci_e_salva"),
                      command=lambda: self.unisci(salva=True),
                      fg_color="#4A5568", hover_color="#2D3748", height=38
                      ).pack(side="left", expand=True, padx=(6,0), fill="x")

        # Nome file output FISSO in fondo
        frame_nome = ctk.CTkFrame(self, fg_color="transparent")
        frame_nome.pack(side="bottom", padx=20, fill="x", pady=4)
        ctk.CTkLabel(frame_nome, text=T("unisci_nome_file")).pack(side="left", padx=(0,8))
        _oggi = datetime.today().strftime("%Y%m%d")
        self.entry_nome = ctk.CTkEntry(frame_nome, placeholder_text="MERGED_" + _oggi, width=220)
        self.entry_nome.pack(side="left")
        ctk.CTkLabel(frame_nome, text=".adif").pack(side="left", padx=4)

        # Lista file
        frame_lista = ctk.CTkFrame(self)
        frame_lista.pack(padx=20, fill="x")
        ctk.CTkLabel(frame_lista, text=T("unisci_file_sel"),
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(8,4))
        self.listbox_frame = ctk.CTkScrollableFrame(frame_lista, height=100)
        self.listbox_frame.pack(fill="both", expand=True, padx=10, pady=4)
        self.labels_file = []
        frame_btn_lista = ctk.CTkFrame(frame_lista, fg_color="transparent")
        frame_btn_lista.pack(fill="x", padx=10, pady=6)
        ctk.CTkButton(frame_btn_lista, text=T("unisci_aggiungi_file"),
                      command=self.aggiungi_file, fg_color=TH.PRIMARY, width=140
                      ).pack(side="left", padx=(0,8))
        ctk.CTkButton(frame_btn_lista, text=T("unisci_aggiungi_cbr"),
                      command=self.aggiungi_cbr, fg_color="#4A5568", width=140
                      ).pack(pady=2, fill="x")
        ctk.CTkButton(frame_btn_lista, text=T("unisci_rimuovi_ultimo"),
                      command=self.rimuovi_ultimo, fg_color="#718096", width=160
                      ).pack(side="left")
        self.lbl_count = ctk.CTkLabel(frame_lista, text="0 file selezionati",
                                       text_color="gray", font=ctk.CTkFont(size=11))
        self.lbl_count.pack(anchor="w", padx=10, pady=(0,6))

        # Opzioni
        frame_opt = ctk.CTkFrame(self)
        frame_opt.pack(padx=20, fill="x", pady=6)
        ctk.CTkLabel(frame_opt, text=T("unisci_opt_titolo"),
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(8,4))
        self.var_dedup_esatto = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(frame_opt,
                        text=T("unisci_dedup_esatto"),
                        variable=self.var_dedup_esatto).pack(anchor="w", padx=10, pady=2)
        self.var_dedup_60s = ctk.BooleanVar(value=True)
        frame_60s = ctk.CTkFrame(frame_opt, fg_color="transparent")
        frame_60s.pack(anchor="w", padx=10, pady=2)
        ctk.CTkCheckBox(frame_60s, text=T("dv_dup_toll"),
                        variable=self.var_dedup_60s).pack(side="left")
        self.entry_tol_sec = ctk.CTkEntry(frame_60s, width=50)
        self.entry_tol_sec.insert(0, "60")
        self.entry_tol_sec.pack(side="left", padx=4)
        ctk.CTkLabel(frame_60s, text="secondi (call + banda + modo + data)",
                     font=ctk.CTkFont(size=10), text_color="gray").pack(side="left")
        self.var_sort = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(frame_opt, text=T("unisci_ordina"),
                        variable=self.var_sort).pack(anchor="w", padx=10, pady=(2,8))

        # Log riepilogo
        frame_log = ctk.CTkFrame(self)
        frame_log.pack(padx=20, fill="both", expand=True, pady=4)
        ctk.CTkLabel(frame_log, text=T("unisci_riepilogo"),
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(6,2))
        self.txt_log = ctk.CTkTextbox(frame_log, height=120, font=ctk.CTkFont(size=10))
        self.txt_log.pack(fill="both", expand=True, padx=10, pady=(0,8))
        self.txt_log.configure(state="disabled")

    def aggiungi_file(self):
        paths = filedialog.askopenfilenames(
            title=T("dv_sel_adif"),
            filetypes=[("ADIF files", "*.adi *.adif"), ("All files", "*.*")])
        for p in paths:
            if p not in self.files:
                self.files.append(p)
        self._aggiorna_lista()

    def aggiungi_cbr(self):
        """Aggiunge file Cabrillo convertendoli in QSO ADIF."""
        paths = filedialog.askopenfilenames(
            title=T("dv_sel_cabrillo"),
            filetypes=[("Cabrillo files", "*.cbr *.log *.txt"), ("All files", "*.*")])
        for p in paths:
            if p not in self.files:
                self.files.append(p)
        self._aggiorna_lista()

    def _leggi_cabrillo(self, path):
        """Converte un file Cabrillo in lista di QSO ADIF."""
        import re as _re
        FREQ_MAP = {
            "1800":"160m","1900":"160m","3500":"80m","3600":"80m","3700":"80m",
            "5357":"60m","7000":"40m","7100":"40m","7200":"40m",
            "10100":"30m","10130":"30m","14000":"20m","14100":"20m","14225":"20m",
            "18068":"17m","18100":"17m","21000":"15m","21200":"15m","21300":"15m",
            "24890":"12m","24940":"12m","28000":"10m","28500":"10m","29000":"10m",
            "50000":"6m","51000":"6m","144000":"2m","144300":"2m",
            "432000":"70cm","432200":"70cm","1296000":"23cm","2320000":"13cm",
        }
        MODE_MAP = {
            "CW":"CW","SSB":"SSB","FM":"FM","AM":"AM","RTTY":"RTTY",
            "DG":"FT8","RY":"RTTY","PH":"SSB","DIG":"FT8",
        }
        qsos = []
        mycall = ""
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if line.upper().startswith("CALLSIGN:"):
                mycall = line.split(":",1)[1].strip().upper()
            if not line.upper().startswith("QSO:"):
                continue
            # Formato Cabrillo: QSO: freq mode date time mycall rst_s exch_s call rst_r exch_r
            parts = line[4:].split()
            if len(parts) < 8:
                continue
            try:
                freq_khz = parts[0].strip()
                modo_cbr = parts[1].strip().upper()
                data_cbr = parts[2].strip()   # YYYY-MM-DD
                ora_cbr  = parts[3].strip()   # HHMM
                call_tx  = parts[4].strip().upper()
                rst_s    = parts[5].strip() if len(parts) > 5 else "59"
                # exch_s potrebbe mancare — call DX è dopo
                # Cerca il callsign DX (non numerico, non rst)
                dx_idx = 7 if len(parts) > 7 else 6
                call_dx  = parts[dx_idx].strip().upper() if len(parts) > dx_idx else ""
                rst_r    = parts[dx_idx+1].strip() if len(parts) > dx_idx+1 else "59"
                # Converti data YYYY-MM-DD → YYYYMMDD
                data_adif = data_cbr.replace("-","")
                # Converti ora HHMM → HHMM (già ok)
                ora_adif = ora_cbr.replace(":","")[:4]
                # Banda da frequenza KHz
                banda = FREQ_MAP.get(freq_khz, "")
                if not banda:
                    # prova arrotondamento a centinaia
                    try:
                        fk = int(freq_khz)
                        for fref, b in FREQ_MAP.items():
                            if abs(fk - int(fref)) < 200:
                                banda = b; break
                    except: pass
                # Frequenza in MHz
                try: freq_mhz = f"{int(freq_khz)/1000:.3f}"
                except: freq_mhz = ""
                # Modo
                modo = MODE_MAP.get(modo_cbr, modo_cbr)
                if not call_dx or len(call_dx) < 3:
                    continue
                qso = {
                    'call':             call_dx,
                    'qso_date':         data_adif,
                    'time_on':          ora_adif,
                    'band':             banda,
                    'freq':             freq_mhz,
                    'mode':             modo,
                    'rst_sent':         rst_s[:3],
                    'rst_rcvd':         rst_r[:3],
                    'station_callsign': mycall or call_tx,
                }
                qsos.append(qso)
            except Exception:
                continue
        return qsos

    def rimuovi_ultimo(self):
        if self.files:
            self.files.pop()
            self._aggiorna_lista()

    def _aggiorna_lista(self):
        for lbl in self.labels_file:
            lbl.destroy()
        self.labels_file = []
        for i, path in enumerate(self.files):
            # Colori adattivi al tema (transparent = usa sfondo del parent)
            col = ("gray85","gray25") if i % 2 == 0 else ("gray75","gray20")
            ext = os.path.splitext(path)[1].lower()
            tipo = "[CBR]" if ext in ('.cbr','.log') else "[ADIF]"
            lbl = ctk.CTkLabel(self.listbox_frame,
                               text=f"  {i+1}. {tipo} {os.path.basename(path)}",
                               anchor="w", fg_color=col, corner_radius=4)
            lbl.pack(fill="x", pady=1)
            self.labels_file.append(lbl)
        self.lbl_count.configure(text=f"{len(self.files)} file selezionati")

    def _log(self, testo):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", testo + chr(10))
        self.txt_log.configure(state="disabled")
        self.txt_log.see("end")

    def _leggi_adif(self, path):
        # Se è un file Cabrillo, usa il parser dedicato
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.cbr', '.log') or (ext == '.txt' and self._is_cabrillo(path)):
            return self._leggi_cabrillo(path)
        return self._leggi_adif_puro(path)

    def _is_cabrillo(self, path):
        """Verifica se un file è in formato Cabrillo."""
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                head = f.read(200).upper()
            return 'START-OF-LOG' in head or 'QSO:' in head
        except: return False

    def _leggi_adif_puro(self, path):
        import re as _re
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            testo = f.read()
        if "<EOH>" not in testo.upper():
            testo = "<EOH>" + chr(10) + testo
        CAMPI_H = {"adif_ver","programid","programversion","created_timestamp"}
        # Prima prova adif_io
        try:
            qsos, _ = adif_io.read_from_string(testo)
            return [{k.lower():v for k,v in q.items() if k.lower() not in CAMPI_H} for q in qsos]
        except Exception:
            pass
        # Fallback parser manuale — ignora campi duplicati
        qsos = []
        eoh = testo.upper().find('<EOH>')
        body = testo[eoh+5:] if eoh >= 0 else testo
        pat = _re.compile(r'<([^:>]+)(?::(\d+)(?::[^>]*)?)?>([^<]*)', _re.IGNORECASE)
        for rec in _re.split(r'<EOR>', body, flags=_re.IGNORECASE):
            rec = rec.strip()
            if not rec:
                continue
            qso = {}
            for m in pat.finditer(rec):
                tag = m.group(1).lower()
                if tag in CAMPI_H or tag in qso:
                    continue
                length = int(m.group(2)) if m.group(2) else None
                value = m.group(3)[:length].strip() if length else m.group(3).strip()
                if value:
                    qso[tag] = value
            if qso.get('call'):
                # Normalizzazione campi LoTW da download LoTW / HRD
                _ha_app_lotw = any(k.startswith('app_lotw') for k in qso)
                if _ha_app_lotw:
                    if not qso.get('lotw_qsl_rcvd') and qso.get('qsl_rcvd', '').upper() == 'Y':
                        qso['lotw_qsl_rcvd'] = 'Y'
                    if not qso.get('lotw_qslrdate') and qso.get('qslrdate', '').strip():
                        qso['lotw_qslrdate'] = qso['qslrdate'].strip()
                # HRD esporta LOTW_QSL_RCVD=V (Verified) invece dello standard Y
                if qso.get('lotw_qsl_rcvd', '').upper() == 'V':
                    qso['lotw_qsl_rcvd'] = 'Y'
                qsos.append(qso)
        return qsos

    def _utc_sec(self, qso):
        data = str(qso.get('qso_date','')).strip()
        ora  = str(qso.get('time_on','')).strip().ljust(6,'0')[:6]
        if len(data) != 8:
            return None
        try:
            from datetime import datetime as _dt
            return int(_dt.strptime(data + ora, "%Y%m%d%H%M%S").timestamp())
        except Exception:
            return None

    def _chiedi_callsign(self, calls_per_file):
        unici = list(dict.fromkeys(c for c in calls_per_file if c and c != "?"))
        if not unici:
            return None
        dlg = ctk.CTkToplevel(self)
        dlg.title(T("call_difformi") + " — Dupe Check")
        dlg.geometry("480x380")
        dlg.resizable(False, True)
        dlg.grab_set()
        dlg.attributes("-topmost", True)

        # Pulsante FISSO in fondo — dichiarato prima degli altri
        risultato = [unici[0]]
        scelta = ctk.StringVar(value=unici[0])
        entry_manual = ctk.CTkEntry(dlg, width=180, justify="center",
                                     placeholder_text=T("dv_ph_iq1cm"))
        def conferma():
            manuale = entry_manual.get().strip().upper()
            risultato[0] = manuale if manuale else scelta.get()
            dlg.destroy()
        ctk.CTkButton(dlg, text=T("conferma_btn"), command=conferma,
                      fg_color=TH.SUCCESS_H, height=38, width=160).pack(
                      side="bottom", pady=12)

        ctk.CTkLabel(dlg, text=T("call_difformi"),
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=TH.WARNING_H).pack(pady=10, padx=20)
        ctk.CTkLabel(dlg, text=T("call_quale"),
                     font=ctk.CTkFont(size=11)).pack(pady=4)

        # Radio button
        frame_r = ctk.CTkFrame(dlg, fg_color="transparent")
        frame_r.pack(pady=4)
        for c in unici:
            ctk.CTkRadioButton(frame_r, text=c, variable=scelta, value=c,
                               font=ctk.CTkFont(size=13, weight="bold")
                               ).pack(side="left", padx=16)

        # Campo manuale
        ctk.CTkLabel(dlg, text=T("dv_oppure_man"),
                     font=ctk.CTkFont(size=10), text_color="gray").pack(pady=(8,2))
        entry_manual.pack()

        # Lista file scrollabile
        ctk.CTkLabel(dlg, text=T("call_dettaglio"),
                     font=ctk.CTkFont(size=10, weight="bold")).pack(pady=(8,2))
        frame_scroll = ctk.CTkScrollableFrame(dlg, height=100)
        frame_scroll.pack(fill="x", padx=15, pady=2)
        for i, c in enumerate(calls_per_file):
            ctk.CTkLabel(frame_scroll,
                         text=f"{os.path.basename(self.files[i])}: {c}",
                         font=ctk.CTkFont(size=9), anchor="w").pack(fill="x")
        dlg.wait_window()
        return risultato[0]

    def unisci(self, salva=False):
        if len(self.files) < 2:
            messagebox.showwarning(T("attenzione"), T("unisci_warn"))
            return
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

        tutti_qso = []
        errori = []
        callsigns_per_file = []

        for path in self.files:
            try:
                qsos = self._leggi_adif(path)
                tutti_qso.extend(qsos)
                calls = list(dict.fromkeys(
                    str(q.get('station_callsign','')).upper().strip()
                    for q in qsos if str(q.get('station_callsign','')).strip()))
                call_st = calls[0] if calls else "?"
                callsigns_per_file.append(call_st)
                self._log(f"OK {os.path.basename(path)}: {len(qsos)} QSO  STATION={call_st}")
            except Exception as ex:
                errori.append(str(ex))
                self._log(f"ERRORE {os.path.basename(path)}: {ex}")

        if errori:
            messagebox.showwarning("Avviso", "File non letti:\n" + "\n".join(errori))

        # Controllo callsign
        calls_unici = list(dict.fromkeys(callsigns_per_file))
        if len(calls_unici) > 1 or "?" in calls_unici:
            self._log(f"ATTENZIONE callsign difformi: {' | '.join(callsigns_per_file)}")
            call_scelto = self._chiedi_callsign(callsigns_per_file)
            if call_scelto:
                self._log(f"  Callsign scelto: {call_scelto}")
                for q in tutti_qso:
                    q['station_callsign'] = call_scelto
        else:
            self._log(f"STATION_CALLSIGN uniforme: {calls_unici[0] if calls_unici else '?'}")

        n_originali = len(tutti_qso)
        self._log(f"QSO totali: {n_originali}")

        # Dedup esatta
        if self.var_dedup_esatto.get():
            visti = set()
            dedup = []
            for q in tutti_qso:
                k = (str(q.get('call','')).upper().strip(),
                     str(q.get('qso_date','')).strip(),
                     str(q.get('band','')).upper().strip(),
                     str(q.get('mode','')).upper().strip())
                if k not in visti:
                    visti.add(k)
                    dedup.append(q)
            n_es = n_originali - len(dedup)
            tutti_qso = dedup
            if n_es:
                self._log(f"Dupe esatti rimossi: {n_es}")

        # Dedup ±N secondi
        if self.var_dedup_60s.get():
            try:
                tol_sec = int(self.entry_tol_sec.get().strip())
            except (ValueError, AttributeError):
                tol_sec = 60
            dedup60 = []
            for q in tutti_qso:
                call  = str(q.get('call','')).upper().strip()
                banda = str(q.get('band','')).upper().strip()
                modo  = str(q.get('mode','')).upper().strip()
                data  = str(q.get('qso_date','')).strip()
                t_q   = self._utc_sec(q)
                is_dup = False
                if t_q is not None:
                    for q2 in dedup60:
                        if (str(q2.get('call','')).upper().strip() == call and
                            str(q2.get('band','')).upper().strip() == banda and
                            str(q2.get('mode','')).upper().strip() == modo and
                            str(q2.get('qso_date','')).strip() == data):
                            t_q2 = self._utc_sec(q2)
                            if t_q2 is not None and abs(t_q - t_q2) <= tol_sec:
                                is_dup = True
                                break
                if not is_dup:
                    dedup60.append(q)
            n_60s = len(tutti_qso) - len(dedup60)
            tutti_qso = dedup60
            if n_60s:
                self._log(f"Dupe ±{tol_sec}s rimossi: {n_60s}")

        n_dedup = n_originali - len(tutti_qso)

        if self.var_sort.get():
            tutti_qso = sorted(tutti_qso,
                key=lambda x: (x.get('qso_date',''), x.get('time_on','')))

        self._log(f"RISULTATO: {len(tutti_qso)} QSO finali (rimossi: {n_dedup})")

        if salva:
            nome_base = self.entry_nome.get().strip() or \
                        "MERGED_" + datetime.today().strftime("%Y%m%d")
            save_path = filedialog.asksaveasfilename(
                title=T("dv_salva_adif_unito"),
                defaultextension=".adif",
                filetypes=[("ADIF files","*.adif")],
                initialfile=nome_base + ".adif")
            if save_path:
                try:
                    CAMPI_H = {"adif_ver","programid","programversion","created_timestamp"}
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write("<ADIF_VER:5>3.1.4" + chr(10))
                        f.write("<PROGRAMID:17>ADIF_FZR_2.3_BETA" + chr(10))
                        f.write("<EOH>" + chr(10) + chr(10))
                        for qso in tutti_qso:
                            for k, v in qso.items():
                                if k.lower() in CAMPI_H or not str(v).strip():
                                    continue
                                f.write(f"<{k.upper()}:{len(str(v))}>{v} ")
                            f.write("<EOR>" + chr(10))
                    self._log(f"Salvato: {os.path.basename(save_path)}")
                    messagebox.showinfo("Salvato",
                        f"File ADIF salvato:\n{os.path.basename(save_path)}"
                        f"\n{len(tutti_qso)} QSO")
                except Exception as ex:
                    messagebox.showerror("Errore", f"Impossibile salvare:\n{ex}")
                    return

        self.risultato_qsos = tutti_qso
        self.risultato_nome = self.entry_nome.get().strip() or \
                              "MERGED_" + datetime.today().strftime("%Y%m%d")

        if not salva:
            messagebox.showinfo("Successo",
                f"Unione completata!\n\n"
                f"File uniti: {len(self.files)}\n"
                f"QSO originali: {n_originali}\n"
                f"Duplicati rimossi: {n_dedup}\n"
                f"QSO nel log finale: {len(tutti_qso)}")
            self.destroy()


# ─────────────────────────────────────────────
#  Dialogo Ricerca Duplicati
# ─────────────────────────────────────────────
