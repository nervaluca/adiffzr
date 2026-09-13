import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import os
import time
import customtkinter as ctk
from tkinter import messagebox, filedialog
import tkinter.ttk as _ttk
from config import T
import theme as TH
from net.uploaders import (
    CloudlogUploader, ClublogUploader, LotwUploader,
    EqslUploader, QO100Uploader, LotwDownloader, EqslDownloader
)
from net.hamqth import HamQTHClient
from net import lotw_align
import re
import datetime
from gui.widgets import CalendarPopup


# ═══ Funzioni download/merge/SWL — ripristinate dalla 2.4 (perse nello split) ═══
def _normalizza_modo_merge(modo, submode=""):
    """Normalizza il modo per il confronto tra log locali e LoTW/eQSL.
    LoTW spesso usa APP_LOTW_MODEGROUP (DATA, PHONE ecc.) come modo,
    ma nel campo MODE manda già FT8/JT65/SSB ecc. — il problema è quando
    il log locale ha MODE=FT4 e LoTW manda MODE=MFSK+SUBMODE=FT4, oppure
    viceversa. Questa funzione restituisce sempre la forma 'canonica'
    che permette il confronto."""
    m = str(modo).upper().strip()
    s = str(submode).upper().strip()

    # MFSK con submode esplicito (es. LoTW: MODE=MFSK SUBMODE=FT4)
    # → usa il submode come modo canonico
    if m == "MFSK" and s in ("FT4", "FT8", "FT2", "JS8", "VARA"):
        return s

    # Sinonimi SSB
    if m in ("USB", "LSB", "AM", "FM"):
        return "SSB" if m in ("USB", "LSB") else m

    # DATA generico → lascia DATA così i QSO "DATA senza submode" matchano
    # tra loro ma non con FT8/JT65 specifici
    return m


def _normalizza_data_download(valore, formato="lotw"):
    """Accetta YYYYMMDD, YYYY-MM-DD o DD/MM/YYYY e restituisce il formato richiesto."""
    s = str(valore or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{4})[-/](\d{2})[-/](\d{2})$", s)
    if m:
        y, mo, d = m.groups()
    else:
        m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", s)
        if m:
            d, mo, y = m.groups()
        else:
            m = re.match(r"^(\d{4})(\d{2})(\d{2})", s)
            if not m:
                return s
            y, mo, d = m.groups()
    return f"{y}-{mo}-{d}" if formato == "lotw" else f"{y}{mo}{d}"


def _banda_da_freq_merge(freq):
    """Ricava una banda ADIF da FREQ in MHz quando il download non contiene BAND."""
    try:
        f = float(str(freq or "").replace(",", ".").strip())
    except Exception:
        return ""
    ranges = [
        (0.1357, 0.1378, "2190m"), (0.472, 0.479, "630m"),
        (1.8, 2.0, "160m"), (3.5, 4.0, "80m"), (5.0, 5.5, "60m"),
        (7.0, 7.3, "40m"), (10.1, 10.15, "30m"), (14.0, 14.35, "20m"),
        (18.068, 18.168, "17m"), (21.0, 21.45, "15m"),
        (24.89, 24.99, "12m"), (28.0, 29.7, "10m"), (50.0, 54.0, "6m"),
        (70.0, 71.0, "4m"), (144.0, 148.0, "2m"), (222.0, 225.0, "1.25m"),
        (420.0, 450.0, "70cm"), (902.0, 928.0, "33cm"),
        (1240.0, 1300.0, "23cm"), (2300.0, 2450.0, "13cm"),
        (3300.0, 3500.0, "9cm"), (5650.0, 5925.0, "6cm"),
        (10000.0, 10500.0, "3cm"),
    ]
    for low, high, band in ranges:
        if low <= f <= high:
            return band.upper()
    return ""


def _banda_qso_merge(qso):
    band = str(qso.get('band', '') or qso.get('BAND', '')).upper().strip()
    if band:
        return band
    return _banda_da_freq_merge(qso.get('freq', '') or qso.get('FREQ', ''))


def _date_vicine(d1, d2, tolleranza_giorni=1):
    """True se le due date YYYYMMDD differiscono al massimo di tolleranza_giorni."""
    try:
        from datetime import datetime as _dt
        t1 = _dt.strptime(str(d1).strip(), "%Y%m%d")
        t2 = _dt.strptime(str(d2).strip(), "%Y%m%d")
        return abs((t1 - t2).days) <= tolleranza_giorni
    except Exception:
        return d1 == d2


def _merge_download_in_log(app_ref, qsos_scaricati, campo_rcvd, campo_date):
    """Funzione condivisa per LoTW ed eQSL download.
    Confronta qsos_scaricati con il log aperto in app_ref su:
      Callsign + Data (±1 giorno) + Banda + Modo (normalizzato)
    Per ogni match: imposta campo_rcvd='Y' e campo_date=data conferma.
    Ritorna (n_aggiornati, qsos_senza_match)."""

    def _dati_match(qso):
        modo = _normalizza_modo_merge(
            qso.get('mode', '') or qso.get('MODE', ''),
            qso.get('submode', '') or qso.get('SUBMODE', ''))
        return (
            str(qso.get('call', '') or qso.get('CALL', '')).upper().strip(),
            str(qso.get('qso_date', '') or qso.get('QSO_DATE', '')).strip(),
            _banda_qso_merge(qso),
            modo,
        )

    # Indice per callsign; data/banda/modo vengono verificati nel confronto finale.
    indice = {}
    for q in app_ref.qsos_caricati:
        call, data, band, modo = _dati_match(q)
        if call and data:
            indice.setdefault(call, []).append((data, band, modo, q))

    n_aggiornati = 0
    senza_match = []

    for qs in qsos_scaricati:
        call_d, data_d, band_d, modo_d = _dati_match(qs)

        # Cerca tra i QSO del log con lo stesso callsign
        candidati = indice.get(call_d, [])
        corrispondenti = []

        for (data_l, band_l, modo_l, q_log) in candidati:
            # Match esatto su data + banda + modo
            if data_l == data_d and band_l == band_d and modo_l == modo_d:
                corrispondenti.append(q_log)

        if not corrispondenti:
            # Tolleranza ±1 giorno sulla data (QSO vicini mezzanotte UTC)
            for (data_l, band_l, modo_l, q_log) in candidati:
                if (band_l == band_d and modo_l == modo_d
                        and _date_vicine(data_l, data_d, 1)):
                    corrispondenti.append(q_log)

        if corrispondenti:
            data_conf = str(qs.get('qslrdate', '') or
                            qs.get('lotw_qslrdate', '') or
                            qs.get('eqsl_qslrdate', '')).strip()
            for q_log in corrispondenti:
                q_log[campo_rcvd] = 'Y'
                if data_conf and data_conf != '00000000':
                    q_log[campo_date] = data_conf
            n_aggiornati += 1
        else:
            senza_match.append(qs)

    return n_aggiornati, senza_match


def _salva_non_match(app_ref, parent_win, senza_match, prefisso):
    """Chiede dove salvare i QSO senza match e li scrive come ADIF."""
    nome_def = f"{prefisso}_non_confermati.adif"
    save_path = filedialog.asksaveasfilename(
        parent=parent_win,
        title=T("dl_salva_nonmatch"),
        defaultextension=".adif",
        filetypes=[("ADIF files", "*.adif"), ("All files", "*.*")],
        initialfile=nome_def)
    if not save_path:
        return
    try:
        app_ref._scrivi_adif(save_path, senza_match)
        messagebox.showinfo(T("successo"),
            T("dl_nonmatch_salvati", n=len(senza_match), path=os.path.basename(save_path)))
    except Exception as ex:
        messagebox.showerror(T("errore"), str(ex))



def _is_swl_call(call):
    """Ritorna True se il callsign sembra uno SWL.
    Pattern riconosciuti:
      /SWL o -SWL in coda          → IW1FZR/SWL, DL1ABC-SWL
      Termina con SWL               → 00123SWL
      Formato eQSL SWL              → SP-0386-GD, IT-1234-AB, DL-0001-XX
        (PREFISSO 1-3 lettere) - (NUMERO 3-6 cifre) - (SUFFISSO 1-4 lettere)
      Numeri iniziali senza prefisso ITU → 00001, 12345
    """
    c = str(call).upper().strip()
    if not c:
        return False
    # Suffisso /SWL o -SWL
    if '/SWL' in c or c.endswith('-SWL') or c.endswith('SWL'):
        return True
    # Formato eQSL SWL: XX-NNNN-YY  (es. SP-0386-GD, IT-1234-AB)
    if re.match(r'^[A-Z]{1,3}-\d{3,6}-[A-Z]{1,4}$', c):
        return True
    # Numeri iniziali puri (formato SWL numerico)
    if re.match(r'^\d{3,}', c):
        return True
    return False



class CloudlogUploadDialog(ctk.CTkToplevel):
    """Finestra per il caricamento dei QSO verso Cloudlog via API ufficiale."""

    def __init__(self, parent, qsos_visibili, qsos_coda, cl_url, cl_key, cl_station):
        super().__init__(parent)
        self.title(T("cl_titolo"))
        self.geometry("520x480")
        self.resizable(False, True)
        self.grab_set(); self.lift(); self.focus_force()
        self.app_ref = parent
        self.qsos_visibili = qsos_visibili
        self.qsos_coda = qsos_coda
        self.uploader = CloudlogUploader(cl_url, cl_key, cl_station)
        self._annulla = False

        ctk.CTkLabel(self, text="📡 " + T("cl_titolo"),
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(16, 4), padx=20)
        ctk.CTkLabel(self, text=cl_url, font=ctk.CTkFont(size=10),
                     text_color="gray").pack(pady=(0, 10))

        frame_test = ctk.CTkFrame(self, fg_color="transparent")
        frame_test.pack(fill="x", padx=20, pady=4)
        self.lbl_test = ctk.CTkLabel(frame_test, text="", font=ctk.CTkFont(size=11))
        self.lbl_test.pack(side="left")
        ctk.CTkButton(frame_test, text=T("cl_test"), command=self._test,
                      width=170, height=30, fg_color="#4A5568",
                      hover_color="#2D3748").pack(side="right")

        # Scelta scope
        frame_scope = ctk.CTkFrame(self)
        frame_scope.pack(fill="x", padx=20, pady=10)
        self.var_scope = ctk.StringVar(value="tutti")
        ctk.CTkRadioButton(frame_scope, text=T("cl_scope_tutti", n=len(qsos_visibili)),
                           variable=self.var_scope, value="tutti").pack(anchor="w", padx=10, pady=6)
        rb_coda = ctk.CTkRadioButton(frame_scope, text=T("cl_scope_coda", n=len(qsos_coda)),
                           variable=self.var_scope, value="coda")
        rb_coda.pack(anchor="w", padx=10, pady=(0, 6))
        if not qsos_coda:
            rb_coda.configure(state="disabled")

        # Progress + log
        self.progress = ctk.CTkProgressBar(self, width=460, height=16)
        self.progress.pack(padx=20, pady=(10, 4))
        self.progress.set(0)
        self.lbl_progress = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11))
        self.lbl_progress.pack()

        self.txt_log = ctk.CTkTextbox(self, height=140, font=ctk.CTkFont(size=10))
        self.txt_log.pack(fill="both", expand=True, padx=20, pady=10)
        self.txt_log.configure(state="disabled")

        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(fill="x", padx=20, pady=(0, 16))
        self.btn_carica = ctk.CTkButton(frame_btn, text=T("cl_carica_btn"),
                      command=self._avvia_upload, height=38,
                      fg_color=TH.SUCCESS_H, hover_color=TH.SUCCESS,
                      font=ctk.CTkFont(size=13, weight="bold"))
        self.btn_carica.pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(frame_btn, text=T("cl_annulla"), command=self._chiudi,
                      height=38, width=100, fg_color="#718096").pack(side="left")

    def _log(self, testo):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", testo + chr(10))
        self.txt_log.configure(state="disabled")
        self.txt_log.see("end")

    def _test(self):
        self.lbl_test.configure(text="…", text_color="gray")
        self.update()
        ok, msg = self.uploader.test_connection()
        if ok:
            self.lbl_test.configure(text=T("cl_test_ok"), text_color=TH.OK_TEXT)
        else:
            self.lbl_test.configure(text=f"{T('cl_test_ko')}{msg}", text_color=TH.DANGER)

    def _chiudi(self):
        self._annulla = True
        self.destroy()

    def _avvia_upload(self):
        qsos = self.qsos_visibili if self.var_scope.get() == "tutti" else self.qsos_coda
        if not qsos:
            messagebox.showwarning(T("attenzione"), "Nessun QSO da caricare.")
            return
        self.btn_carica.configure(state="disabled")
        self._annulla = False
        tot = len(qsos)
        ok_count = dup_count = err_count = 0
        errori = []

        for i, qso in enumerate(qsos):
            if self._annulla:
                break
            self.progress.set((i + 1) / tot)
            self.lbl_progress.configure(text=T("cl_in_corso", n=i + 1, tot=tot))
            self.update()

            risultato = self.uploader.upload_qso(qso)
            call = str(qso.get('call', '')).upper()
            if risultato["ok"] and risultato["dup"]:
                dup_count += 1
                self._log(f"⊘ {call} — duplicato, scartato da Cloudlog")
            elif risultato["ok"]:
                ok_count += 1
                self._log(f"✓ {call} — caricato")
            else:
                err_count += 1
                errori.append(f"{call}: {risultato['msg']}")
                self._log(f"✗ {call} — ERRORE: {risultato['msg']}")

        self.btn_carica.configure(state="normal")
        msg = T("cl_riepilogo", ok=ok_count, dup=dup_count, err=err_count)
        if errori:
            msg += "\n\n" + T("cl_dettaglio_errori") + "\n" + "\n".join(errori[:10])
        messagebox.showinfo(T("successo"), msg)


# ─────────────────────────────────────────────
#  Clublog — upload via realtime.php / putlogs.php
# ─────────────────────────────────────────────
import urllib.parse




class ClublogUploadDialog(ctk.CTkToplevel):
    """Finestra per il caricamento dei QSO verso Clublog."""

    def __init__(self, parent, qsos_visibili, qsos_coda, cb_email, cb_password, cb_callsign, cb_api):
        super().__init__(parent)
        self.title(T("cb_titolo"))
        self.geometry("520x460")
        self.resizable(False, True)
        self.grab_set(); self.lift(); self.focus_force()
        self.app_ref = parent
        self.qsos_visibili = qsos_visibili
        self.qsos_coda = qsos_coda
        self.uploader = ClublogUploader(cb_email, cb_password, cb_callsign, cb_api)
        self._annulla = False

        ctk.CTkLabel(self, text="📋 " + T("cb_titolo"),
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(16, 4), padx=20)
        ctk.CTkLabel(self, text=f"{cb_callsign}  ·  {cb_email}", font=ctk.CTkFont(size=10),
                     text_color="gray").pack(pady=(0, 10))

        frame_scope = ctk.CTkFrame(self)
        frame_scope.pack(fill="x", padx=20, pady=10)
        self.var_scope = ctk.StringVar(value="tutti")
        ctk.CTkRadioButton(frame_scope, text=T("cb_scope_tutti", n=len(qsos_visibili)),
                           variable=self.var_scope, value="tutti").pack(anchor="w", padx=10, pady=6)
        rb_coda = ctk.CTkRadioButton(frame_scope, text=T("cb_scope_coda", n=len(qsos_coda)),
                           variable=self.var_scope, value="coda")
        rb_coda.pack(anchor="w", padx=10, pady=(0, 6))
        if not qsos_coda:
            rb_coda.configure(state="disabled")

        self.progress = ctk.CTkProgressBar(self, width=460, height=16)
        self.progress.pack(padx=20, pady=(10, 4))
        self.progress.set(0)
        self.lbl_progress = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11))
        self.lbl_progress.pack()

        self.txt_log = ctk.CTkTextbox(self, height=160, font=ctk.CTkFont(size=10))
        self.txt_log.pack(fill="both", expand=True, padx=20, pady=10)
        self.txt_log.configure(state="disabled")

        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(fill="x", padx=20, pady=(0, 16))
        self.btn_carica = ctk.CTkButton(frame_btn, text=T("cb_carica_btn"),
                      command=self._avvia_upload, height=38,
                      fg_color=TH.SUCCESS_H, hover_color=TH.SUCCESS,
                      font=ctk.CTkFont(size=13, weight="bold"))
        self.btn_carica.pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(frame_btn, text=T("cl_annulla"), command=self._chiudi,
                      height=38, width=100, fg_color="#718096").pack(side="left")

    def _log(self, testo):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", testo + chr(10))
        self.txt_log.configure(state="disabled")
        self.txt_log.see("end")

    def _chiudi(self):
        self._annulla = True
        self.destroy()

    def _avvia_upload(self):
        self.btn_carica.configure(state="disabled")
        self._annulla = False

        if self.var_scope.get() == "tutti":
            # Bulk upload: un'unica chiamata putlogs.php con l'intero ADIF
            self.lbl_progress.configure(text=T("cb_in_corso_bulk"))
            self.progress.configure(mode="indeterminate")
            self.progress.start()
            self.update()

            CAMPI_H = {"adif_ver", "programid", "programversion", "created_timestamp"}
            righe = ["<ADIF_VER:5>3.1.4", "<PROGRAMID:17>ADIF_FZR_2.3_BETA", "<EOH>", ""]
            for qso in self.qsos_visibili:
                campi = []
                for k, v in qso.items():
                    if k.lower() in CAMPI_H or not str(v).strip():
                        continue
                    campi.append(f"<{k.upper()}:{len(str(v))}>{v}")
                campi.append("<EOR>")
                righe.append(" ".join(campi))
            adif_text = chr(10).join(righe)

            ok, msg = self.uploader.upload_bulk_adif(adif_text)
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.set(1.0 if ok else 0.0)
            self.lbl_progress.configure(text="")
            self._log(("✓ " if ok else "✗ ") + msg)
            self.btn_carica.configure(state="normal")
            messagebox.showinfo(T("successo") if ok else T("errore"),
                                 T("cb_riepilogo_bulk", msg=msg))
        else:
            # Real-time: un QSO alla volta verso realtime.php
            qsos = self.qsos_coda
            tot = len(qsos)
            ok_count = dup_count = err_count = 0
            for i, qso in enumerate(qsos):
                if self._annulla:
                    break
                self.progress.set((i + 1) / tot)
                self.lbl_progress.configure(text=T("cl_in_corso", n=i + 1, tot=tot))
                self.update()
                risultato = self.uploader.upload_qso_realtime(qso)
                call = str(qso.get('call', '')).upper()
                if risultato["ok"] and risultato["dup"]:
                    dup_count += 1
                    self._log(f"⊘ {call} — duplicato")
                elif risultato["ok"]:
                    ok_count += 1
                    self._log(f"✓ {call} — caricato")
                else:
                    err_count += 1
                    self._log(f"✗ {call} — ERRORE: {risultato['msg']}")
                time.sleep(0.3)  # cortesia verso il server, evita di sembrare un attacco
            self.btn_carica.configure(state="normal")
            messagebox.showinfo(T("successo"),
                T("cb_riepilogo_rt", ok=ok_count, dup=dup_count, err=err_count))


# ─────────────────────────────────────────────
#  LoTW — firma e upload via TQSL (riga di comando)
# ─────────────────────────────────────────────
import subprocess
import tempfile

# Mappa codici di uscita di tqsl (documentazione ufficiale ARRL/TrustedQSL)
_TQSL_EXIT_CODES_IT = {
    0:  "Successo: tutti i QSO sono stati firmati e caricati.",
    1:  "Operazione annullata dall'utente.",
    2:  "Il log è stato rifiutato dal server LoTW.",
    3:  "Risposta inattesa dal server LoTW.",
    4:  "Si è verificato un errore in tqsl.",
    5:  "Errore in tqsllib (nome file o formato non valido).",
    6:  "Impossibile aprire il file di input.",
    7:  "Impossibile aprire il file di output.",
    8:  "Nessun QSO processato: erano tutti duplicati o fuori intervallo date.",
    9:  "Alcuni QSO sono stati processati, altri ignorati perché duplicati o fuori intervallo date.",
    10: "Errore di sintassi nel comando.",
    11: "Connessione di rete a LoTW fallita.",
    12: "Errore sconosciuto.",
    13: "Il database dei duplicati di TQSL è bloccato (un'altra istanza di tqsl è in esecuzione?).",
}




class LotwUploadDialog(ctk.CTkToplevel):
    """Finestra per il caricamento dei QSO verso LoTW via TQSL."""

    def __init__(self, parent, qsos_visibili, qsos_coda, tqsl_path, station_location):
        super().__init__(parent)
        self.title(T("lw_titolo"))
        self.geometry("520x460")
        self.resizable(False, True)
        self.grab_set(); self.lift(); self.focus_force()
        self.app_ref = parent
        self.qsos_visibili = qsos_visibili
        self.qsos_coda = qsos_coda
        self.tqsl_path = tqsl_path
        self.station_location = station_location

        ctk.CTkLabel(self, text="📡 " + T("lw_titolo"),
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(16, 4), padx=20)
        ctk.CTkLabel(self, text=f"{station_location}  ·  {os.path.basename(tqsl_path)}",
                     font=ctk.CTkFont(size=10), text_color="gray").pack(pady=(0, 10))

        if not os.path.isfile(tqsl_path):
            ctk.CTkLabel(self, text=T("lw_tqsl_non_trovato", path=tqsl_path),
                         font=ctk.CTkFont(size=11), text_color=TH.DANGER,
                         wraplength=460, justify="left").pack(padx=20, pady=10)

        frame_scope = ctk.CTkFrame(self)
        frame_scope.pack(fill="x", padx=20, pady=10)
        self.var_scope = ctk.StringVar(value="tutti")
        ctk.CTkRadioButton(frame_scope, text=T("lw_scope_tutti", n=len(qsos_visibili)),
                           variable=self.var_scope, value="tutti").pack(anchor="w", padx=10, pady=6)
        rb_coda = ctk.CTkRadioButton(frame_scope, text=T("lw_scope_coda", n=len(qsos_coda)),
                           variable=self.var_scope, value="coda")
        rb_coda.pack(anchor="w", padx=10, pady=(0, 6))
        if not qsos_coda:
            rb_coda.configure(state="disabled")

        frame_pw = ctk.CTkFrame(self, fg_color="transparent")
        frame_pw.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(frame_pw, text=T("lw_password_opt"), font=ctk.CTkFont(size=10),
                     text_color="gray", wraplength=460, justify="left").pack(anchor="w")
        self.entry_pw = ctk.CTkEntry(frame_pw, show="*", width=200)
        self.entry_pw.pack(anchor="w", pady=(2, 0))

        self.txt_log = ctk.CTkTextbox(self, height=120, font=ctk.CTkFont(size=10))
        self.txt_log.pack(fill="both", expand=True, padx=20, pady=10)
        self.txt_log.configure(state="disabled")

        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(fill="x", padx=20, pady=(0, 16))
        self.btn_carica = ctk.CTkButton(frame_btn, text=T("lw_carica_btn"),
                      command=self._avvia_upload, height=38,
                      fg_color=TH.SUCCESS_H, hover_color=TH.SUCCESS,
                      font=ctk.CTkFont(size=13, weight="bold"))
        self.btn_carica.pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(frame_btn, text=T("cl_annulla"), command=self.destroy,
                      height=38, width=100, fg_color="#718096").pack(side="left")

    def _log(self, testo):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", testo + chr(10))
        self.txt_log.configure(state="disabled")
        self.txt_log.see("end")

    def _avvia_upload(self):
        if not os.path.isfile(self.tqsl_path):
            messagebox.showerror(T("errore"), T("lw_tqsl_non_trovato", path=self.tqsl_path))
            return
        qsos = self.qsos_visibili if self.var_scope.get() == "tutti" else self.qsos_coda
        if not qsos:
            messagebox.showwarning(T("attenzione"), "Nessun QSO da caricare.")
            return
        self.btn_carica.configure(state="disabled")
        self._log(T("lw_in_corso"))
        self.update()

        uploader = LotwUploader(self.tqsl_path, self.station_location, self.entry_pw.get())
        try:
            exit_code, msg, stderr_full = uploader.upload(qsos)
        except subprocess.TimeoutExpired:
            exit_code, msg, stderr_full = -1, "Timeout: tqsl non ha risposto entro 3 minuti.", ""
        except Exception as ex:
            exit_code, msg, stderr_full = -1, str(ex), ""

        self.btn_carica.configure(state="normal")
        self._log(f"[exit code {exit_code}] {msg}")
        if stderr_full:
            for riga in stderr_full.strip().split(chr(10))[-6:]:
                self._log("  " + riga)

        if exit_code == 0:
            messagebox.showinfo(T("successo"), msg)
        elif exit_code == 9:
            messagebox.showwarning(T("lw_esito"), msg)
        else:
            messagebox.showerror(T("lw_esito"), msg)


# ─────────────────────────────────────────────
#  eQSL.cc — upload via ImportADIF.cfm
# ─────────────────────────────────────────────


class EqslUploadDialog(ctk.CTkToplevel):
    """Finestra per il caricamento dei QSO verso eQSL.cc."""

    def __init__(self, parent, qsos_visibili, qsos_coda, eq_user, eq_pass, eq_qth):
        super().__init__(parent)
        self.title(T("eq_titolo"))
        self.geometry("520x440")
        self.resizable(False, True)
        self.grab_set(); self.lift(); self.focus_force()
        self.app_ref = parent
        self.qsos_visibili = qsos_visibili
        self.qsos_coda = qsos_coda
        self.uploader = EqslUploader(eq_user, eq_pass, eq_qth)

        ctk.CTkLabel(self, text="📨 " + T("eq_titolo"),
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(16, 4), padx=20)
        ctk.CTkLabel(self, text=eq_user, font=ctk.CTkFont(size=10),
                     text_color="gray").pack(pady=(0, 10))

        frame_scope = ctk.CTkFrame(self)
        frame_scope.pack(fill="x", padx=20, pady=10)
        self.var_scope = ctk.StringVar(value="tutti")
        ctk.CTkRadioButton(frame_scope, text=T("eq_scope_tutti", n=len(qsos_visibili)),
                           variable=self.var_scope, value="tutti").pack(anchor="w", padx=10, pady=6)
        rb_coda = ctk.CTkRadioButton(frame_scope, text=T("eq_scope_coda", n=len(qsos_coda)),
                           variable=self.var_scope, value="coda")
        rb_coda.pack(anchor="w", padx=10, pady=(0, 6))
        if not qsos_coda:
            rb_coda.configure(state="disabled")

        self.progress = ctk.CTkProgressBar(self, width=460, height=16)
        self.progress.pack(padx=20, pady=(10, 4))
        self.progress.set(0)
        self.lbl_progress = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11))
        self.lbl_progress.pack()

        self.txt_log = ctk.CTkTextbox(self, height=140, font=ctk.CTkFont(size=10))
        self.txt_log.pack(fill="both", expand=True, padx=20, pady=10)
        self.txt_log.configure(state="disabled")

        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(fill="x", padx=20, pady=(0, 16))
        self.btn_carica = ctk.CTkButton(frame_btn, text=T("eq_carica_btn"),
                      command=self._avvia_upload, height=38,
                      fg_color=TH.SUCCESS_H, hover_color=TH.SUCCESS,
                      font=ctk.CTkFont(size=13, weight="bold"))
        self.btn_carica.pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(frame_btn, text=T("cl_annulla"), command=self.destroy,
                      height=38, width=100, fg_color="#718096").pack(side="left")

    def _log(self, testo):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", testo + chr(10))
        self.txt_log.configure(state="disabled")
        self.txt_log.see("end")

    def _avvia_upload(self):
        qsos = self.qsos_visibili if self.var_scope.get() == "tutti" else self.qsos_coda
        if not qsos:
            messagebox.showwarning(T("attenzione"), "Nessun QSO da caricare.")
            return
        self.btn_carica.configure(state="disabled")
        self.lbl_progress.configure(text=T("eq_in_corso"))
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.update()

        CAMPI_H = {"adif_ver", "programid", "programversion", "created_timestamp"}
        righe = ["<ADIF_VER:5>3.1.4", "<PROGRAMID:17>ADIF_FZR_2.3_BETA", "<EOH>", ""]
        for qso in qsos:
            campi = []
            for k, v in qso.items():
                if k.lower() in CAMPI_H or not str(v).strip():
                    continue
                campi.append(f"<{k.upper()}:{len(str(v))}>{v}")
            campi.append("<EOR>")
            righe.append(" ".join(campi))
        adif_text = chr(10).join(righe)

        ok, msg, added, total = self.uploader.upload_adif(adif_text)

        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(1.0 if ok else 0.0)
        self.lbl_progress.configure(text="")
        self.btn_carica.configure(state="normal")
        self._log(("✓ " if ok else "✗ ") + msg)
        messagebox.showinfo(T("successo") if ok else T("errore"), T("eq_riepilogo", msg=msg))


# ─────────────────────────────────────────────
#  QO-100 DX Club — upload QSO via API
# ─────────────────────────────────────────────


class QO100UploadDialog(ctk.CTkToplevel):
    """Finestra per il caricamento QSO su QO-100 DX Club."""

    def __init__(self, parent, qsos_visibili, api_key, station_callsign, my_grid):
        super().__init__(parent)
        self.title(T("qo100_titolo"))
        self.geometry("520x460")
        self.resizable(False, True)
        self.grab_set(); self.lift(); self.focus_force()

        self.uploader = QO100Uploader(api_key, station_callsign, my_grid)
        self.qsos_qo100 = QO100Uploader._filtra_qo100(qsos_visibili)
        self._annulla = False

        ctk.CTkLabel(self, text="🛰 " + T("qo100_titolo"),
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(16,4), padx=20)
        ctk.CTkLabel(self, text=f"{station_callsign}  ·  {len(self.qsos_qo100)} QSO via QO-100 trovati",
                     font=ctk.CTkFont(size=10), text_color="gray").pack(pady=(0,10))

        if not self.qsos_qo100:
            ctk.CTkLabel(self, text=T("qo100_no_qso"),
                         font=ctk.CTkFont(size=11), text_color=TH.WARN_TEXT,
                         wraplength=460, justify="left").pack(padx=20, pady=10)
            ctk.CTkButton(self, text=T("cm_chiudi"), fg_color="#718096",
                          command=self.destroy, height=32).pack(pady=10)
            return

        self.progress = ctk.CTkProgressBar(self, width=460, height=16)
        self.progress.pack(padx=20, pady=(0,4))
        self.progress.set(0)
        self.lbl_progress = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11))
        self.lbl_progress.pack()

        self.txt_log = ctk.CTkTextbox(self, height=200, font=ctk.CTkFont(size=10))
        self.txt_log.pack(fill="both", expand=True, padx=20, pady=10)
        self.txt_log.configure(state="disabled")

        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(fill="x", padx=20, pady=(0,16))
        self.btn_carica = ctk.CTkButton(frame_btn,
                      text=f"🛰 Carica {len(self.qsos_qo100)} QSO su QO-100 DX Club",
                      command=self._avvia_upload, height=38,
                      fg_color=TH.SUCCESS_H, hover_color=TH.SUCCESS,
                      font=ctk.CTkFont(size=12, weight="bold"))
        self.btn_carica.pack(side="left", expand=True, fill="x", padx=(0,6))
        ctk.CTkButton(frame_btn, text=T("cm_annulla"), command=self._chiudi,
                      height=38, width=100, fg_color="#718096").pack(side="left")

    def _log(self, testo):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", testo + chr(10))
        self.txt_log.configure(state="disabled")
        self.txt_log.see("end")

    def _chiudi(self):
        self._annulla = True
        self.destroy()

    def _avvia_upload(self):
        self.btn_carica.configure(state="disabled")
        self._annulla = False
        tot = len(self.qsos_qo100)
        ok_count = err_count = 0

        for i, qso in enumerate(self.qsos_qo100):
            if self._annulla:
                break
            self.progress.set((i+1)/tot)
            call = str(qso.get("call","")).upper()
            self.lbl_progress.configure(text=f"{i+1}/{tot}  {call}")
            self.update()

            ok, msg = self.uploader.upload_qso(qso)
            if ok:
                ok_count += 1
                self._log(f"✓ {call} — {msg}")
            else:
                err_count += 1
                self._log(f"✗ {call} — ERRORE: {msg}")

            import time; time.sleep(0.2)

        self.btn_carica.configure(state="normal")
        self.lbl_progress.configure(text="")
        messagebox.showinfo("Completato",
            f"Upload QO-100 DX Club completato.\n\nOK: {ok_count}\nErrori: {err_count}",
            parent=self)


# ─────────────────────────────────────────────
#  HamQTH — callsign lookup
# ─────────────────────────────────────────────


class HamQTHDialog(ctk.CTkToplevel):
    """Finestra risultati lookup HamQTH con opzione di applicare campi al QSO."""

    def __init__(self, parent, info, callsign, qso_idx=None):
        super().__init__(parent)
        self.title(T("hqth_titolo"))
        self.geometry("480x420")
        self.resizable(False, True)
        self.grab_set(); self.lift(); self.focus_force()
        self.app_ref = parent
        self.info = info
        self.qso_idx = qso_idx

        # Header
        ctk.CTkLabel(self, text=f"📡 {info['callsign']}",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(14,2))
        if info.get('nick'):
            ctk.CTkLabel(self, text=info['nick'],
                         font=ctk.CTkFont(size=12), text_color="gray").pack()

        # Grid info
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=10)

        def riga(lbl, val, col="#E2E8F0"):
            if not val: return
            r = ctk.CTkFrame(frame, fg_color="transparent")
            r.pack(fill="x", pady=1)
            ctk.CTkLabel(r, text=lbl, width=120, anchor="e",
                         font=ctk.CTkFont(size=10), text_color="gray").pack(side="left")
            ctk.CTkLabel(r, text=val, anchor="w",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=col).pack(side="left", padx=(8,0))

        riga("QTH:",        info.get("qth",""))
        riga("Paese:",      info.get("country",""))
        riga("Continente:", info.get("continent",""))
        riga("Zona CQ:",    info.get("cq",""))
        riga("Zona ITU:",   info.get("itu",""))
        riga("Locator:",    info.get("grid",""), "#48BB78")
        riga("QSL via:",    info.get("qsl_via",""), "#F6AD55")

        # Badge LoTW / eQSL
        frame_b = ctk.CTkFrame(self, fg_color="transparent")
        frame_b.pack(pady=4)
        if info.get("lotw","") == "Y":
            ctk.CTkLabel(frame_b, text="LoTW ✓", fg_color=TH.SUCCESS_H,
                         corner_radius=6, width=70, height=24,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="white").pack(side="left", padx=4)
        if info.get("eqsl","") == "Y":
            ctk.CTkLabel(frame_b, text="eQSL ✓", fg_color=TH.PRIMARY,
                         corner_radius=6, width=70, height=24,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="white").pack(side="left", padx=4)

        if info.get("birth_year"):
            ctk.CTkLabel(self, text=f"Anno licenza: {info['birth_year']}",
                         font=ctk.CTkFont(size=9), text_color="gray").pack()

        # Pulsanti applica
        if qso_idx is not None:
            frame_btn = ctk.CTkFrame(self, fg_color="transparent")
            frame_btn.pack(fill="x", padx=20, pady=(10,4))
            ctk.CTkLabel(frame_btn, text=T("dv_applica_qso_sel"),
                         font=ctk.CTkFont(size=10), text_color="gray").pack(anchor="w")
            frame_azioni = ctk.CTkFrame(frame_btn, fg_color="transparent")
            frame_azioni.pack(fill="x", pady=(4,0))

            def _applica(campo, valore, etichetta):
                if not valore: return
                try:
                    qso = self.app_ref._qsos_attivi()[qso_idx]
                    qso[campo] = valore
                    self.app_ref._aggiorna_tree()
                    messagebox.showinfo("Applicato",
                        f"{etichetta} → {valore}", parent=self)
                except Exception as ex:
                    messagebox.showerror(T("dxc_errore"), str(ex), parent=self)

            azioni = [
                ("name",       info.get("nick",""),     "Nome op."),
                ("gridsquare", info.get("grid",""),     "Locator"),
                ("qsl_via",    info.get("qsl_via",""),  "QSL via"),
                ("country",    info.get("country",""),  "Country"),
            ]
            for campo, val, lbl in azioni:
                if val:
                    ctk.CTkButton(frame_azioni, text=f"← {lbl}",
                                  width=90, height=26,
                                  font=ctk.CTkFont(size=9),
                                  fg_color=TH.PRIMARY,
                                  command=lambda c=campo, v=val, l=lbl: _applica(c, v, l)
                                  ).pack(side="left", padx=(0,4))

        ctk.CTkButton(self, text=T("cm_chiudi"), fg_color="#718096",
                      height=30, command=self.destroy).pack(pady=(6,14))


# ─────────────────────────────────────────────
#  LoTW — download ADIF confermati
# ─────────────────────────────────────────────


class LotwDownloadDialog(ctk.CTkToplevel):
    """Finestra per il download dell'ADIF confermato da LoTW."""


    def __init__(self, parent, lw_user, lw_pass, default_call=""):
        super().__init__(parent)
        self.title(T("lwd_titolo"))
        self.geometry("480x380")
        self.resizable(False, False)
        self.grab_set(); self.lift(); self.focus_force()
        self.app_ref = parent
        self.downloader = LotwDownloader(lw_user, lw_pass)
        self.default_call = default_call

        ctk.CTkLabel(self, text="📡 " + T("lwd_titolo"),
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(16, 4), padx=20)
        ctk.CTkLabel(self, text=lw_user, font=ctk.CTkFont(size=10),
                     text_color="gray").pack(pady=(0, 12))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=24)

        ctk.CTkLabel(form, text=T("lwd_dal"), anchor="w",
                     font=ctk.CTkFont(size=11)).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0,2))
        self.entry_dal = ctk.CTkEntry(form, width=160, placeholder_text=T("dv_ph_2024_data"))
        self.entry_dal.grid(row=1, column=0, sticky="w", pady=(0, 10))
        ctk.CTkButton(form, text="📅", width=30, height=26, fg_color=TH.PRIMARY,
                      command=lambda: CalendarPopup(self, self.entry_dal)
                      ).grid(row=1, column=1, padx=(6,0), sticky="w", pady=(0,10))

        ctk.CTkLabel(form, text=T("lwd_call"), anchor="w",
                     font=ctk.CTkFont(size=11)).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0,2))
        self.entry_call = ctk.CTkEntry(form, width=160, placeholder_text=default_call or "es. IW1FZR")
        if default_call:
            self.entry_call.insert(0, default_call)
        self.entry_call.grid(row=3, column=0, sticky="w", pady=(0, 14))

        self.lbl_stato = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11))
        self.lbl_stato.pack(pady=4)

        self.progress = ctk.CTkProgressBar(self, width=420, height=14)
        self.progress.pack(padx=24, pady=(0, 10))
        self.progress.set(0)

        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(fill="x", padx=24, pady=(0, 16))
        self.btn_dl = ctk.CTkButton(frame_btn, text=T("lwd_scarica_btn"),
                      command=self._scarica, height=38,
                      fg_color=TH.SUCCESS_H, hover_color=TH.SUCCESS,
                      font=ctk.CTkFont(size=13, weight="bold"))
        self.btn_dl.pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(frame_btn, text=T("cl_annulla"), command=self.destroy,
                      height=38, width=100, fg_color="#718096").pack(side="left")

    def _scarica(self):
        if not self.app_ref.qsos_caricati:
            messagebox.showwarning(T("attenzione"), T("dl_nessun_log"))
            return
        self.btn_dl.configure(state="disabled")
        self.lbl_stato.configure(text=T("lwd_in_corso"), text_color="gray")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.update()

        # Converte dd/mm/yyyy (CalendarPopup) → yyyy-mm-dd (formato LoTW)
        # Accetta anche yyyy-mm-dd e yyyymmdd direttamente
        dal_raw = self.entry_dal.get().strip()
        dal_conv = _normalizza_data_download(dal_raw, formato="lotw")

        ok, adif_text, msg = self.downloader.download(
            qsl_since=dal_conv,
            owncall=self.entry_call.get().strip())

        # La finestra potrebbe essere stata chiusa durante il download (GUI
        # bloccata): in tal caso non toccare più i suoi widget.
        if not self.winfo_exists():
            return

        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.btn_dl.configure(state="normal")

        if not ok:
            self.lbl_stato.configure(text=T("st_errore"), text_color=TH.DANGER)
            messagebox.showerror(T("errore"), T("lwd_err", msg=msg))
            return

        n = adif_text.upper().count("<EOR>")
        if n == 0:
            self.lbl_stato.configure(text="⚠ 0 QSO", text_color=TH.WARN_TEXT)
            messagebox.showwarning(T("attenzione"), T("lwd_vuoto"))
            return

        self.progress.set(1.0)
        self.lbl_stato.configure(text=f"✓ {n} QSO scaricati", text_color=TH.OK_TEXT)

        try:
            qsos_scaricati = self.app_ref._leggi_adif_sicuro(adif_text)
            n_ok, senza_match = _merge_download_in_log(
                self.app_ref, qsos_scaricati,
                campo_rcvd='lotw_qsl_rcvd',
                campo_date='lotw_qslrdate')
            self.app_ref._aggiorna_tree()
            # Chiudo il dialogo PRIMA di aprire messagebox/file-dialog, così
            # nessuno resta agganciato a una finestra in via di distruzione.
            self.destroy()

            if senza_match:
                risposta = messagebox.askyesno(
                    T("dl_merge_titolo"),
                    T("dl_merge_riepilogo", ok=n_ok, no=len(senza_match)))
                if risposta:
                    _salva_non_match(self.app_ref, self.app_ref, senza_match, "lotw")
            else:
                messagebox.showinfo(T("dl_merge_titolo"),
                    T("dl_merge_tutti_ok", ok=n_ok))
        except Exception as ex:
            messagebox.showerror(T("errore"), str(ex))


# ─────────────────────────────────────────────
#  eQSL — download ADIF inbox (QSL ricevute)
# ─────────────────────────────────────────────


class AllineaLotwDialog(ctk.CTkToplevel):
    """Finestra 'Allinea log a LoTW': scarica le QSL con dettaglio location
    (qso_qsldetail=yes) e allinea i campi del log (DXCC, zone, locator,
    stato/contea, IOTA...) sui QSO confermati. Campi e politica di scrittura
    personalizzabili. Flusso: Anteprima (diff) -> Applica (con undo)."""

    def __init__(self, parent, lw_user, lw_pass, default_call="", profilo_nome=None):
        super().__init__(parent)
        self.title(T("ttl_allinea"))
        self.geometry("640x620")
        self.resizable(False, True)
        self.grab_set(); self.lift(); self.focus_force()
        self.app_ref = parent
        self.downloader = LotwDownloader(lw_user, lw_pass)
        self.default_call = default_call
        self.profilo_nome = profilo_nome
        self._diff = []
        self._scaricati = []

        # Preset (campi + politiche + last_qsl) dal profilo, se presente.
        campi_sel, politiche, last_qsl = self._carica_preset()

        ctk.CTkLabel(self, text=T("menu_allinea_lotw"),
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(14, 2), padx=20)
        ctk.CTkLabel(self, text=lw_user, font=ctk.CTkFont(size=10),
                     text_color="gray").pack(pady=(0, 8))

        # Riga: Anno (per allineare un anno alla volta) / callsign owncall
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=24)
        ctk.CTkLabel(form, text=T("lbl_anno_qso"), anchor="w",
                     font=ctk.CTkFont(size=11)).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(form, text=T("lbl_callsign_all"), anchor="w",
                     font=ctk.CTkFont(size=11)).grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.var_anno = ctk.StringVar(value=T("opt_tutte"))
        ctk.CTkOptionMenu(form, variable=self.var_anno, values=self._anni_log(),
                          width=150, height=28).grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.entry_call = ctk.CTkEntry(form, width=150,
                                       placeholder_text=default_call or "vuoto = tutti")
        if default_call:
            self.entry_call.insert(0, default_call)
        self.entry_call.grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(0, 6))

        # Selettore campi + politica
        ctk.CTkLabel(self, text=T("lbl_campi_pol"),
                     anchor="w", font=ctk.CTkFont(size=11, weight="bold")
                     ).pack(fill="x", padx=24, pady=(6, 2))
        scroll = ctk.CTkScrollableFrame(self, height=210, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 4))

        _POL_LABEL = {'overwrite': T("pol_overwrite"), 'fill': T("pol_fill"), 'skip': T("pol_skip")}
        self._chk = {}
        self._pol = {}
        for campo, etichetta, _def in lotw_align.CAMPI_LOTW:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            var = ctk.BooleanVar(value=(campo in campi_sel))
            ctk.CTkCheckBox(row, text=f"{etichetta}  ({campo})", variable=var,
                            font=ctk.CTkFont(size=11), width=260,
                            ).pack(side="left", padx=(4, 8))
            self._chk[campo] = var
            pol_var = ctk.StringVar(value=_POL_LABEL[politiche.get(campo, 'overwrite')])
            ctk.CTkOptionMenu(row, values=list(_POL_LABEL.values()),
                              variable=pol_var, width=150, height=26,
                              font=ctk.CTkFont(size=10)).pack(side="right", padx=4)
            self._pol[campo] = pol_var
        self._pol_label_inv = {v: k for k, v in _POL_LABEL.items()}

        self.lbl_stato = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11))
        self.lbl_stato.pack(pady=2)
        self.txt_diff = ctk.CTkTextbox(self, height=120, font=ctk.CTkFont(size=10))
        self.txt_diff.pack(fill="both", expand=False, padx=20, pady=(0, 6))

        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(fill="x", padx=24, pady=(0, 14))
        self.btn_prev = ctk.CTkButton(frame_btn, text=T("btn_anteprima"), command=self._anteprima,
                      height=36, fg_color=TH.PRIMARY,
                      font=ctk.CTkFont(size=12, weight="bold"))
        self.btn_prev.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.btn_appl = ctk.CTkButton(frame_btn, text=T("btn_applica"), command=self._applica,
                      height=36, fg_color=TH.SUCCESS_H, hover_color=TH.SUCCESS,
                      state="disabled", font=ctk.CTkFont(size=12, weight="bold"))
        self.btn_appl.pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(frame_btn, text=T("btn_chiudi"), command=self.destroy,
                      height=36, width=90, fg_color="#718096").pack(side="left")

    # -- helpers preset ---------------------------------------------------
    def _preset_dati(self):
        campi = [c for c, v in self._chk.items() if v.get()]
        politiche = {c: self._pol_label_inv[self._pol[c].get()] for c in self._pol}
        return campi, politiche

    def _carica_preset(self):
        try:
            profili = self.app_ref._carica_profili()
            d = profili.get(self.profilo_nome, {}) if self.profilo_nome else {}
            campi = d.get('lotw_align_campi') or lotw_align.campi_default()
            pol = lotw_align.politiche_default()
            pol.update(d.get('lotw_align_politiche', {}))
            last = d.get('last_qsl', "")
            return campi, pol, last
        except Exception:
            return lotw_align.campi_default(), lotw_align.politiche_default(), ""

    def _salva_preset(self, last_qsl=None):
        if not self.profilo_nome:
            return
        try:
            profili = self.app_ref._carica_profili()
            if self.profilo_nome not in profili:
                return
            campi, politiche = self._preset_dati()
            profili[self.profilo_nome]['lotw_align_campi'] = campi
            profili[self.profilo_nome]['lotw_align_politiche'] = politiche
            if last_qsl:
                profili[self.profilo_nome]['last_qsl'] = last_qsl
            self.app_ref._salva_profili(profili)
        except Exception:
            pass

    def _anni_log(self):
        """Lista anni per il selettore: 'Tutti' + anni presenti nel log (desc)."""
        anni = set()
        for q in (self.app_ref.qsos_caricati or []):
            d = str(q.get('qso_date', '') or q.get('QSO_DATE', '')).strip()
            if len(d) >= 4 and d[:4].isdigit():
                anni.add(d[:4])
        return [T("opt_tutte")] + sorted(anni, reverse=True)

    # -- flusso -----------------------------------------------------------
    def _scarica(self):
        if not self.app_ref.qsos_caricati:
            messagebox.showwarning(T("attenzione"), T("dl_nessun_log"))
            return False
        anno = self.var_anno.get().strip()
        startdate = enddate = ""
        if anno and anno != T("opt_tutte") and anno.isdigit():
            startdate = f"{anno}-01-01"
            enddate = f"{anno}-12-31"
            self.lbl_stato.configure(text=T("st_scarico_anno", anno=anno),
                                     text_color="gray")
        else:
            self.lbl_stato.configure(text=T("st_scarico_tutto"),
                                     text_color="gray")
        self.update()
        ok, adif_text, msg = self.downloader.download(
            owncall=self.entry_call.get().strip(), qsl_detail=True,
            startdate=startdate, enddate=enddate)
        if not self.winfo_exists():
            return False
        if not ok:
            self.lbl_stato.configure(text="✗ Errore", text_color=TH.DANGER)
            messagebox.showerror(T("errore"), T("lwd_err", msg=msg))
            return False
        self._scaricati = lotw_align.parse_lotw_adif(adif_text)
        if not self._scaricati:
            self.lbl_stato.configure(text=T("st_zero_conf"),
                                     text_color=TH.WARN_TEXT)
            return False
        return True

    def _anteprima(self):
        self.btn_prev.configure(state="disabled")
        try:
            if not self._scarica():
                return
            campi, politiche = self._preset_dati()
            if not campi:
                messagebox.showinfo(T("hdr_nessun_campo"), T("msg_nessun_campo"))
                return
            self._diff, stats = lotw_align.calcola_allineamento(
                self.app_ref.qsos_caricati, self._scaricati, campi, politiche)
            self.txt_diff.delete("1.0", "end")
            if not self._diff:
                self.txt_diff.insert("end", T("msg_gia_allineato", sc=len(self._scaricati), m=stats['match']))
                self.lbl_stato.configure(text=T("st_gia_allineato"), text_color=TH.OK_TEXT)
                self.btn_appl.configure(state="disabled")
                self.btn_prev.configure(state="normal")
                return
            riepilogo = "  ".join(f"{c}:{n}" for c, n in stats['per_campo'].items())
            self.lbl_stato.configure(
                text=T("st_modifiche", mod=stats['modifiche'], m=stats['match'], rk=riepilogo),
                text_color=TH.PRIMARY)
            righe = []
            for d in self._diff[:400]:
                righe.append(f"{d['call']:9s} {d['banda']:4s} {d['campo']:10s} "
                             f"'{d['old']}' → '{d['new']}'")
            extra = "" if len(self._diff) <= 400 else T("msg_altre_mod", n=len(self._diff)-400)
            self.txt_diff.delete("1.0", "end")
            self.txt_diff.insert("end", "\n".join(righe) + extra)
            self.btn_appl.configure(state="normal")
        finally:
            if self.winfo_exists():
                self.btn_prev.configure(state="normal")

    def _applica(self):
        if not self._diff:
            return
        if not messagebox.askyesno(T("hdr_conferma"), T("msg_applicare", n=len(self._diff))):
            return
        self.app_ref._push_undo()
        n = lotw_align.applica_allineamento(self._diff)
        self.app_ref._aggiorna_tree()
        if hasattr(self.app_ref, "_log_modificato"):
            self.app_ref._log_modificato = True
        self._salva_preset(last_qsl=self.downloader.last_qsl)
        self.lbl_stato.configure(text=T("st_applicate", n=n), text_color=TH.OK_TEXT)
        self.btn_appl.configure(state="disabled")
        self._diff = []
        messagebox.showinfo(T("hdr_all_completato"), T("msg_all_completato", n=n))


class EqslDownloadDialog(ctk.CTkToplevel):
    """Finestra per il download dell'ADIF inbox da eQSL.cc.
    Modalità:
      - Scarica e mergia: scarica tutto, mergia nel log, mostra unmatched
      - Solo unconfirmed: scarica tutto, filtra solo orange, mostra EqslUnconfirmedDialog"""

    def __init__(self, parent, eq_user, eq_pass, eq_qth=""):
        super().__init__(parent)
        self.title(T("eqd_titolo"))
        self.geometry("500x400")
        self.resizable(False, False)
        self.grab_set(); self.lift(); self.focus_force()
        self.app_ref = parent
        self.downloader = EqslDownloader(eq_user, eq_pass, eq_qth)

        ctk.CTkLabel(self, text="📨 " + T("eqd_titolo"),
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(16,4), padx=20)
        ctk.CTkLabel(self, text=eq_user, font=ctk.CTkFont(size=10),
                     text_color="gray").pack(pady=(0,10))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=24)

        # ── Data dal ──
        ctk.CTkLabel(form, text=T("eqd_dal"), anchor="w",
                     font=ctk.CTkFont(size=11)).grid(row=0, column=0,
                     columnspan=3, sticky="w", pady=(0,2))
        self.entry_dal = ctk.CTkEntry(form, width=160,
                                       placeholder_text=T("dv_ph_20240101"))
        self.entry_dal.grid(row=1, column=0, sticky="w", pady=(0,6))
        ctk.CTkButton(form, text="📅", width=30, height=26, fg_color=TH.PRIMARY,
                      command=lambda: CalendarPopup(self, self.entry_dal)
                      ).grid(row=1, column=1, padx=(6,0), sticky="w", pady=(0,6))

        # Carica ultima data scaricamento dal profilo
        self._carica_ultima_data()

        ctk.CTkLabel(form, text=self._lbl_ultima_data(),
                     font=ctk.CTkFont(size=9), text_color=TH.LINK
                     ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(0,10))

        # ── Modalità ──
        ctk.CTkLabel(form, text=T("cm_modalita"), anchor="w",
                     font=ctk.CTkFont(size=11)).grid(row=3, column=0,
                     columnspan=3, sticky="w", pady=(0,4))
        self.var_modo = ctk.StringVar(value="mergia")
        ctk.CTkRadioButton(form, text=T("dv_scarica_merge"),
                           variable=self.var_modo, value="mergia",
                           font=ctk.CTkFont(size=10)).grid(row=4, column=0,
                           columnspan=3, sticky="w", pady=2)
        ctk.CTkRadioButton(form, text=T("dv_solo_unconf"),
                           variable=self.var_modo, value="unconf",
                           font=ctk.CTkFont(size=10)).grid(row=5, column=0,
                           columnspan=3, sticky="w", pady=2)

        self.lbl_stato = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11))
        self.lbl_stato.pack(pady=(10,4))

        self.progress = ctk.CTkProgressBar(self, width=440, height=14)
        self.progress.pack(padx=24, pady=(0,10))
        self.progress.set(0)

        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(fill="x", padx=24, pady=(0,16))
        self.btn_dl = ctk.CTkButton(frame_btn, text=T("eqd_scarica_btn"),
                      command=self._scarica, height=38,
                      fg_color=TH.SUCCESS_H, hover_color=TH.SUCCESS,
                      font=ctk.CTkFont(size=13, weight="bold"))
        self.btn_dl.pack(side="left", expand=True, fill="x", padx=(0,6))
        ctk.CTkButton(frame_btn, text=T("cl_annulla"), command=self.destroy,
                      height=38, width=100, fg_color="#718096").pack(side="left")

    def _carica_ultima_data(self):
        """Carica l'ultima data di scaricamento dal profilo e pre-compila il campo."""
        try:
            profili = self.app_ref._carica_profili()
            dati = profili.get(self.app_ref.profilo_attivo, {}) if self.app_ref.profilo_attivo else {}
            self._ultima_data = dati.get('eqsl_last_download', '')
            if self._ultima_data:
                self.entry_dal.delete(0, "end")
                self.entry_dal.insert(0, self._ultima_data)
        except Exception:
            self._ultima_data = ''

    def _lbl_ultima_data(self):
        if self._ultima_data:
            return f"Ultimo scaricamento: {self._ultima_data}"
        return "Nessuno scaricamento precedente registrato"

    def _salva_ultima_data(self, data_str):
        """Salva la data di scaricamento nel profilo."""
        try:
            profili = self.app_ref._carica_profili()
            if self.app_ref.profilo_attivo and self.app_ref.profilo_attivo in profili:
                profili[self.app_ref.profilo_attivo]['eqsl_last_download'] = data_str
                import json as _json
                prof_path = os.path.join(os.path.expanduser("~"), ".adif_fzr_profili.json")
                with open(prof_path, 'w', encoding='utf-8') as f:
                    _json.dump(profili, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _scarica(self):
        if self.var_modo.get() == "mergia" and not self.app_ref.qsos_caricati:
            messagebox.showwarning(T("attenzione"), T("dl_nessun_log"), parent=self)
            return

        self.btn_dl.configure(state="disabled")
        self.lbl_stato.configure(text=T("eqd_in_corso"), text_color="gray")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.update()

        dal_raw  = self.entry_dal.get().strip()
        dal_conv = _normalizza_data_download(dal_raw, formato="adif")

        ok, adif_text, msg = self.downloader.download(rcvd_since=dal_conv)

        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.btn_dl.configure(state="normal")

        if not ok:
            self.lbl_stato.configure(text="✗ Errore", text_color=TH.DANGER)
            messagebox.showerror(T("errore"), T("eqd_err", msg=msg), parent=self)
            return

        if adif_text in ("NO_QSO", "") or adif_text.upper().count("<EOR>") == 0:
            self.lbl_stato.configure(text="⚠ 0 QSO", text_color=TH.WARN_TEXT)
            messagebox.showwarning(T("attenzione"), T("eqd_vuoto"), parent=self)
            return

        n = adif_text.upper().count("<EOR>")
        self.progress.set(1.0)
        self.lbl_stato.configure(text=f"✓ {n} QSO scaricati", text_color=TH.OK_TEXT)
        self._salva_ultima_data(_normalizza_data_download(self.entry_dal.get().strip(), "adif")
                                or datetime.date.today().strftime("%Y%m%d"))

        profili = self.app_ref._carica_profili()
        dati    = profili.get(self.app_ref.profilo_attivo, {}) if self.app_ref.profilo_attivo else {}
        eq_user  = dati.get('eqsl_username','').strip()
        eq_pass  = dati.get('eqsl_password','').strip()
        stazione = dati.get('callsign','').strip() or self.app_ref.entry_owner.get().strip()
        modo     = self.var_modo.get()

        try:
            qsos = self.app_ref._leggi_adif_sicuro(adif_text)
            if not qsos:
                messagebox.showwarning(T("attenzione"), T("eqd_vuoto"), parent=self)
                self.destroy(); return

            qsos = [{k.lower(): v for k, v in q.items()} for q in qsos]

            if modo == "unconf":
                lista_raw = [q for q in qsos
                             if str(q.get('qsl_rcvd','')).upper().strip() != 'Y']
                # Deduplica per call+date+time+band+mode
                _visti = set()
                lista = []
                for q in lista_raw:
                    k = (str(q.get('call','')).upper().strip(),
                         str(q.get('qso_date','')).strip(),
                         str(q.get('time_on','')).strip(),
                         str(q.get('band','')).upper().strip(),
                         str(q.get('mode','')).upper().strip())
                    if k[0] and k not in _visti:
                        _visti.add(k); lista.append(q)
                self.destroy()
                if not lista:
                    messagebox.showinfo("Nessun unconfirmed",
                        f"Tutti i {n} QSO risultano già confermati.",
                        parent=self.app_ref)
                else:
                    EqslUnconfirmedDialog(self.app_ref, lista, eq_user, eq_pass, stazione)
            else:
                n_ok, senza_match = _merge_download_in_log(
                    self.app_ref, qsos,
                    campo_rcvd='eqsl_qsl_rcvd',
                    campo_date='eqsl_qslrdate')
                self.app_ref._aggiorna_tree()
                self.destroy()
                if not senza_match:
                    messagebox.showinfo(T("dl_merge_titolo"),
                        T("dl_merge_tutti_ok", ok=n_ok), parent=self.app_ref)
                else:
                    # Deduplica senza_match
                    _vs = set(); sm_unici = []
                    for q in senza_match:
                        k = (str(q.get('call','')).upper().strip(),
                             str(q.get('qso_date','')).strip(),
                             str(q.get('time_on','')).strip(),
                             str(q.get('band','')).upper().strip(),
                             str(q.get('mode','')).upper().strip())
                        if k[0] and k not in _vs:
                            _vs.add(k); sm_unici.append(q)
                    messagebox.showinfo(T("dl_merge_titolo"),
                        T("dl_merge_riepilogo", ok=n_ok, no=len(sm_unici)),
                        parent=self.app_ref)
                    EqslUnconfirmedDialog(self.app_ref, sm_unici,
                                          eq_user, eq_pass, stazione)
        except Exception as ex:
            messagebox.showerror(T("errore"), str(ex), parent=self.app_ref)
            self.destroy()



# ─────────────────────────────────────────────
#  SWL — rilevamento e gestione report ascolto
# ─────────────────────────────────────────────



class EqslUnconfirmedDialog(ctk.CTkToplevel):
    """Dialog per gestire le eQSL non abbinate al merge:
    - SWL (non possono mai combaciare con un QSO)
    - QSO con data/banda/modo non corrispondente nel log
    L'utente può: marcare come SWL, salvare ADIF, inviare conferma eQSL."""

    def __init__(self, parent, qsos_unconf, eq_user, eq_pass, stazione):
        super().__init__(parent)
        self.title("📥 eQSL non abbinate — revisione")
        self.geometry("900x560")
        self.resizable(True, True)
        self.grab_set(); self.lift(); self.focus_force()

        self.app_ref    = parent
        # Deduplica la lista in ingresso per call+date+band+mode
        # (eQSL può inviare lo stesso record più volte)
        _seen = set()
        _dedup = []
        for q in qsos_unconf:
            k = (str(q.get('call','')).upper().strip(),
                 str(q.get('qso_date','')).strip(),
                 str(q.get('band','')).upper().strip(),
                 str(q.get('mode','')).upper().strip()[:4])
            if k[0] and k not in _seen:
                _seen.add(k); _dedup.append(q)
        self.qsos       = _dedup
        self.eq_user    = eq_user
        self.eq_pass    = eq_pass
        self.stazione   = stazione
        self._vars_swl  = {}   # iid → bool (True = marcato come SWL)
        self._iid_idx   = {}   # iid → indice in self.qsos

        # Percorso swl_log.adi
        if hasattr(parent, 'filepath') and parent.filepath:
            self._swl_path = os.path.join(os.path.dirname(parent.filepath), "swl_log.adi")
        else:
            self._swl_path = os.path.join(os.path.expanduser("~"), "swl_log.adi")

        # SWL già noti dal log storico — legge SOLO record con APP_EQSL_SWL=Y
        # (evita il ciclo vizioso dove QSO normali salvati per errore
        #  vengono ri-riconosciuti come SWL alla sessione successiva)
        swl_noti = set()
        if os.path.exists(self._swl_path):
            try:
                with open(self._swl_path, 'r', encoding='utf-8', errors='replace') as f:
                    txt = f.read()
                for rec in re.split(r'<EOR>', txt, flags=re.IGNORECASE):
                    m_swl = re.search(r'<APP_EQSL_SWL:\d+>([^<]+)', rec, re.IGNORECASE)
                    if m_swl and m_swl.group(1).strip().upper() == 'Y':
                        m_call = re.search(r'<CALL:\d+>([^<\s]+)', rec, re.IGNORECASE)
                        if m_call:
                            swl_noti.add(m_call.group(1).strip().upper())
                    else:
                        # Fallback: callsign che matchano pattern SWL noti
                        m_call = re.search(r'<CALL:\d+>([^<\s]+)', rec, re.IGNORECASE)
                        if m_call:
                            c = m_call.group(1).strip().upper()
                            if _is_swl_call(c):
                                swl_noti.add(c)
            except Exception:
                pass

        ctk.CTkLabel(self, text=f"📥 {len(self.qsos)} eQSL non abbinate al tuo log",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12,2), padx=16)
        ctk.CTkLabel(self,
                     text="☑ = SWL (pre-rilevato).  Clicca colonna SWL per modificare. "
                          "I QSO SWL vanno in swl_log.adi, gli altri puoi salvarli separatamente.",
                     font=ctk.CTkFont(size=10), text_color="gray",
                     wraplength=860).pack(padx=16, pady=(0,6))

        import tkinter as _tk
        import tkinter.ttk as _ttk
        frame_t = _tk.Frame(self, bg="#0D0D0D")
        frame_t.pack(fill="both", expand=True, padx=14, pady=(0,6))

        style = _ttk.Style(); style.theme_use("default")
        style.configure("UNC.Treeview", background="#0D0D0D", foreground="#E2E8F0",
            rowheight=22, fieldbackground="#0D0D0D", font=("Arial",9))
        style.configure("UNC.Treeview.Heading", background="#1A365D",
            foreground="white", font=("Arial",9,"bold"))

        cols = ("swl","call","data","utc","banda","modo","tipo")
        tv = _ttk.Treeview(frame_t, columns=cols, show="headings", style="UNC.Treeview")
        for col, lbl, w in [
            ("swl","SWL",45),("call","Callsign",140),("data","Data",75),
            ("utc","UTC",50),("banda","Banda",55),("modo","Modo",60),
            ("tipo","Tipo rilevamento",300)]:
            tv.heading(col, text=lbl); tv.column(col, width=w, stretch=(col=="tipo"))
        sb = _ttk.Scrollbar(frame_t, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); tv.pack(side="left", fill="both", expand=True)

        # Costruisce indice rapido del log principale per verifica
        # SWL: check se esiste un QSO con stessa data+banda+modo nel log
        _log_index = set()
        if hasattr(parent, 'qsos_caricati'):
            for q in parent.qsos_caricati:
                data  = str(q.get('qso_date','')).strip()
                banda = str(q.get('band','')).upper().strip()
                modo  = str(q.get('mode','')).upper().strip()[:4]
                if data and banda:
                    _log_index.add((data, banda, modo))

        for idx, q in enumerate(self.qsos):
            call = str(q.get('call','')).upper()
            # Criterio primario: eQSL marca le card SWL con APP_EQSL_SWL=Y
            app_swl = str(q.get('app_eqsl_swl','')).upper().strip()
            is_swl  = (app_swl == 'Y' or
                       _is_swl_call(call) or
                       call in swl_noti)
            data = str(q.get('qso_date',''))
            if len(data)==8: data_fmt=f"{data[6:8]}/{data[4:6]}/{data[0:4]}"
            else: data_fmt = data
            utc = str(q.get('time_on',''))[:4]
            if len(utc)==4: utc=f"{utc[:2]}:{utc[2:]}"

            # Verifica corrispondenza con log principale
            banda_raw = str(q.get('band','')).upper().strip()
            modo_raw  = str(q.get('mode','')).upper().strip()[:4]
            in_log = (data, banda_raw, modo_raw) in _log_index

            if is_swl:
                if in_log:
                    tipo = "📻 SWL — ✓ QSO nel log"
                    tag  = "swl_ok"
                else:
                    tipo = "📻 SWL — ⚠ nessun QSO nel log"
                    tag  = "swl_warn"
            else:
                tipo = "❓ QSO — data/banda non combacia"
                tag  = "qso"

            iid = tv.insert("","end",
                values=("☑" if is_swl else "☐",
                        call, data_fmt, utc,
                        banda_raw,
                        str(q.get('mode','')).upper(),
                        tipo),
                tags=(tag,))
            self._vars_swl[iid] = is_swl
            self._iid_idx[iid]  = idx

        tv.tag_configure("swl_ok",   foreground="#48BB78")  # verde = ok
        tv.tag_configure("swl_warn", foreground="#F6AD55")  # arancio = attenzione
        tv.tag_configure("qso",      foreground="#90CDF4")  # blu = QSO

        def _toggle(e):
            row = tv.identify_row(e.y)
            if row and tv.identify_column(e.x) == "#1":
                self._vars_swl[row] = not self._vars_swl[row]
                v = list(tv.item(row,"values"))
                v[0] = "☑" if self._vars_swl[row] else "☐"
                tv.item(row, values=v)
        tv.bind("<Button-1>", _toggle)

        # ── Legenda ──
        frame_leg = ctk.CTkFrame(self, fg_color="transparent")
        frame_leg.pack(fill="x", padx=14, pady=(0,2))
        ctk.CTkLabel(frame_leg, text="🟢 SWL con QSO nel log (OK)",
                     font=ctk.CTkFont(size=9), text_color=TH.OK_TEXT).pack(side="left", padx=(0,12))
        ctk.CTkLabel(frame_leg, text="🟡 SWL senza QSO corrispondente (verificare)",
                     font=ctk.CTkFont(size=9), text_color=TH.WARN_TEXT).pack(side="left", padx=(0,12))
        ctk.CTkLabel(frame_leg, text="🔵 QSO non abbinato",
                     font=ctk.CTkFont(size=9), text_color=TH.LINK).pack(side="left")

        # ── Barra pulsanti ──
        frame_path = ctk.CTkFrame(self, fg_color="transparent")
        frame_path.pack(fill="x", padx=14, pady=(0,2))
        ctk.CTkLabel(frame_path, text="swl_log.adi:",
                     font=ctk.CTkFont(size=9), text_color="gray").pack(side="left", padx=(0,4))
        self.var_path = ctk.StringVar(value=self._swl_path)
        ctk.CTkEntry(frame_path, textvariable=self.var_path,
                     font=ctk.CTkFont(size=9), height=24).pack(
                     side="left", expand=True, fill="x", padx=(0,4))
        ctk.CTkButton(frame_path, text="…", width=28, height=24,
                      command=lambda: self.var_path.set(
                          filedialog.asksaveasfilename(
                              defaultextension=".adi",
                              filetypes=[("ADIF","*.adi *.adif")],
                              initialfile="swl_log.adi") or self.var_path.get())
                      ).pack(side="left")

        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(fill="x", padx=14, pady=(0,14))

        n_swl = sum(1 for v in self._vars_swl.values() if v)
        n_qso = len(qsos_unconf) - n_swl
        ctk.CTkLabel(frame_btn,
                     text=f"☑ {n_swl} SWL (arancio)  ·  ❓ {n_qso} QSO non abbinati (blu)",
                     font=ctk.CTkFont(size=9), text_color="gray").pack(side="left", padx=(0,12))

        ctk.CTkButton(frame_btn, text="💾 Salva SWL in swl_log.adi",
                      command=self._salva_swl, height=32,
                      fg_color=TH.PRIMARY, hover_color=TH.PRIMARY_H,
                      font=ctk.CTkFont(size=10, weight="bold")).pack(side="left", padx=(0,4))
        ctk.CTkButton(frame_btn, text="📤 Carica swl_log.adi su eQSL",
                      command=self._upload_swl_log_eqsl, height=32,
                      fg_color=TH.SUCCESS_H, hover_color=TH.SUCCESS,
                      font=ctk.CTkFont(size=10, weight="bold")).pack(side="left", padx=(0,4))
        ctk.CTkButton(frame_btn, text="💾 Salva altri come ADIF",
                      command=self._salva_non_swl, height=32,
                      fg_color="#4A5568",
                      font=ctk.CTkFont(size=10)).pack(side="left", padx=(0,4))
        ctk.CTkButton(frame_btn, text=T("cm_chiudi"), width=80, height=32,
                      fg_color="#718096", command=self.destroy).pack(side="right")

    def _swl_selezionati(self):
        return [self.qsos[self._iid_idx[iid]]
                for iid, swl in self._vars_swl.items() if swl]

    def _altri_selezionati(self):
        return [self.qsos[self._iid_idx[iid]]
                for iid, swl in self._vars_swl.items() if not swl]

    def destroy(self):
        try:
            _ripristina_tema_ttk()
        except Exception:
            pass
        super().destroy()

    def _salva_swl(self):
        qsos = self._swl_selezionati()
        if not qsos:
            messagebox.showwarning("Attenzione", "Nessun SWL selezionato (☑).", parent=self)
            return

        # Avvisa se ci sono SWL senza QSO corrispondente nel log
        _log_index = set()
        if hasattr(self.app_ref, 'qsos_caricati'):
            for q in self.app_ref.qsos_caricati:
                _log_index.add((
                    str(q.get('qso_date','')).strip(),
                    str(q.get('band','')).upper().strip(),
                    str(q.get('mode','')).upper().strip()[:4]))
        senza_qso = [str(q.get('call','')).upper() for q in qsos
                     if (str(q.get('qso_date','')).strip(),
                         str(q.get('band','')).upper().strip(),
                         str(q.get('mode','')).upper().strip()[:4])
                     not in _log_index]
        if senza_qso:
            risposta = messagebox.askyesno("Attenzione — SWL senza QSO",
                f"{len(senza_qso)} SWL selezionati NON hanno un QSO corrispondente nel log:\n\n"
                f"{', '.join(senza_qso[:10])}\n\n"
                "Salvare comunque?", parent=self)
            if not risposta:
                return
        path = self.var_path.get().strip()
        try:
            esistenti = set()
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    txt = f.read()
                for rec in re.split(r'<EOR>', txt, flags=re.IGNORECASE):
                    def _g(t, r=rec):
                        m2 = re.search(rf'<{t}:\d+>([^<]+)', r, re.IGNORECASE)
                        return m2.group(1).strip().upper() if m2 else ''
                    c = _g('CALL')
                    if c:
                        esistenti.add((c, _g('QSO_DATE'), _g('BAND'), _g('MODE')[:4]))
            file_vuoto = not os.path.exists(path) or os.path.getsize(path) == 0
            with open(path, 'a', encoding='utf-8') as f:
                if file_vuoto:
                    f.write("<ADIF_VER:5>3.1.4 <PROGRAMID:8>ADIF_FZR <PROGRAMVERSION:3>2.4 <EOH>\n")
                n = 0
                for q in qsos:
                    chiave = (
                        str(q.get('call','')).upper().strip(),
                        str(q.get('qso_date','')).strip(),
                        str(q.get('band','')).upper().strip(),
                        str(q.get('mode','')).upper().strip()[:4],
                    )
                    if chiave in esistenti or not chiave[0]:
                        continue
                    esistenti.add(chiave)
                    for k, v in q.items():
                        v = str(v).strip()
                        if v:
                            f.write(f"<{k.upper()}:{len(v)}>{v} ")
                    f.write("<EOR>\n"); n += 1
            messagebox.showinfo("Salvato", f"{n} SWL salvati in:\n{path}", parent=self)
        except Exception as ex:
            messagebox.showerror(T("dxc_errore"), str(ex), parent=self)

    def _salva_non_swl(self):
        qsos = self._altri_selezionati()
        if not qsos:
            messagebox.showinfo("Info", "Nessun QSO non-SWL da salvare.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            title=T("dv_salva_non_abb"),
            defaultextension=".adi",
            filetypes=[("ADIF","*.adi *.adif")],
            initialfile="eqsl_non_abbinati.adi", parent=self)
        if not path: return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write("<ADIF_VER:5>3.1.4 <PROGRAMID:8>ADIF_FZR <PROGRAMVERSION:3>2.4 <EOH>\n")
                for q in qsos:
                    for k, v in q.items():
                        v = str(v).strip()
                        if v: f.write(f"<{k.upper()}:{len(v)}>{v} ")
                    f.write("<EOR>\n")
            messagebox.showinfo("Salvato", f"{len(qsos)} QSO salvati in:\n{path}", parent=self)
        except Exception as ex:
            messagebox.showerror(T("dxc_errore"), str(ex), parent=self)

    def _upload_swl_log_eqsl(self):
        """Carica swl_log.adi su eQSL via ImportADIF.cfm —
        esattamente come il caricamento manuale che l'utente ha verificato funzionare."""
        import threading as _threading

        if not self.eq_user or not self.eq_pass:
            messagebox.showwarning("Attenzione",
                "Credenziali eQSL non configurate nel profilo operatore.", parent=self)
            return

        swl_path = self.var_path.get().strip()
        if not os.path.exists(swl_path):
            messagebox.showwarning("Attenzione",
                f"File non trovato:\n{swl_path}\n\n"
                "Prima salva gli SWL con '💾 Salva SWL in swl_log.adi'.", parent=self)
            return

        if not messagebox.askyesno("Conferma upload",
            f"Caricare '{os.path.basename(swl_path)}' su eQSL?\n\n"
            f"Le conferme SWL saranno visibili nell'inbox eQSL degli SWL.",
            parent=self):
            return

        try:
            with open(swl_path, 'r', encoding='utf-8', errors='replace') as f:
                adif_body = f.read()
        except Exception as ex:
            messagebox.showerror("Errore lettura file", str(ex), parent=self)
            return

        prog = ctk.CTkToplevel(self)
        prog.title("Upload swl_log.adi su eQSL…")
        prog.geometry("420x160")
        prog.resizable(False, False); prog.grab_set()
        ctk.CTkLabel(prog, text="📤 Caricamento swl_log.adi su eQSL…",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(16,4))
        lbl_p = ctk.CTkLabel(prog, text="", font=ctk.CTkFont(size=10), text_color="gray")
        lbl_p.pack()
        bar = ctk.CTkProgressBar(prog, width=380); bar.pack(pady=8); bar.set(0.3)

        def _thread():
            try:
                data = urllib.parse.urlencode({
                    'Callsign': self.eq_user,
                    'Password': self.eq_pass,
                    'ADIFData': adif_body,
                    'Compete':  'Y',
                }).encode('utf-8')
                req = urllib.request.Request(
                    "https://www.eqsl.cc/qslcard/ImportADIF.cfm",
                    data=data,
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'User-Agent':   'ADIF-FZR/2.4',
                    })
                with urllib.request.urlopen(req, timeout=30) as r:
                    resp = r.read().decode('utf-8', errors='replace')

                # Estrai il testo visibile dalla risposta
                testo = re.sub(r'<[^>]+>', ' ', resp)
                testo = ' '.join(testo.split())

                def _done():
                    if prog.winfo_exists(): prog.destroy()
                    messagebox.showinfo("Upload completato",
                        f"📤 swl_log.adi caricato su eQSL.\n\n"
                        f"Risposta eQSL:\n{testo[:300]}",
                        parent=self)
                prog.after(0, _done)

            except Exception as ex:
                _err_msg = str(ex)
                def _err():
                    if prog.winfo_exists(): prog.destroy()
                    messagebox.showerror("Errore upload", _err_msg, parent=self)
                prog.after(0, _err)

        _threading.Thread(target=_thread, daemon=True).start()
