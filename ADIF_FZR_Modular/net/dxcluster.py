import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import socket
import threading
import time
import re
import tkinter as tk
import tkinter.ttk as _ttk
from tkinter import messagebox
import customtkinter as ctk
from config import T
from utils.dxcc import dxcc_da_nominativo
from utils.maidenhead import distanza_bearing, locator_to_latlon, bearing_to_compass

class DXClusterWindow(ctk.CTkToplevel):
    """Finestra DX Cluster: connessione telnet, spot in tempo reale,
    filtri banda/modo, evidenzia DXCC nuovi, doppio click → Aggiungi QSO."""

    SERVERS = {
        # ── Italia ──
        "IK5PWJ-6 (Montecarlo LU)":  ("ik5pwj-6.dyndns.org", 8000),
        "IZ3MEZ (Italia)":           ("cluster.iz3mez.it", 8000),
        "IZ1CQN (Torino)":           ("dx.iz1cqn.it", 8000),
        "IZ0FKE Noantri (Roma)":     ("spider.noantri.org", 7000),
        "IW9FRA (Trapani)":          ("dxspider.iw9fra.com", 7300),
        "IZ0TWS (Ciampino)":         ("dxcluster.iz0tws.com", 7300),
        "IR4X (Bologna)":            ("ir4x.i4data.net", 7300),
        # ── Europa ──
        "GB7DJK (DXSpider UK)":      ("gb7djk.dxcluster.net", 7300),
        "G6NHU-2 (DXSpider UK)":     ("dxspider.co.uk", 7300),
        "OM0RX-1 (Slovacchia)":      ("cluster.om0rx.com", 7300),
        "EA7JXH (CC Cluster ES)":    ("dx.ea7jxh.eu", 7373),
        "ED1ZAC-5 (Spagna)":         ("dx.ed1zac.net", 8000),
        "OH2AQ (DXSummit FI)":       ("oh2aq.kolumbus.fi", 8000),
        "SK3W (Svezia)":             ("sk3w.shacknet.nu", 8000),
        "DB0SPC (Germania)":         ("db0spc.dyndns.org", 8000),
        # ── Nord America ──
        "VE7CC (CC Cluster)":        ("dxc.ve7cc.net", 7373),
        "NC7J (AR-Cluster UT)":      ("dxc.nc7j.com", 7373),
        "W3LPL (Glenwood MD)":       ("dxc.w3lpl.net", 7373),
        "K0WL (AR-Cluster IA)":      ("k0wl.ddns.net", 7373),
        "N1URO (DXSpider CT)":       ("dx.n1uro.com", 9001),
        "WA9PIE-2 (HamRadioDeluxe)": ("hrd.wa9pie.net", 8000),
        # ── Asia / Oceania ──
        "9M2PJU-2 (Malesia)":        ("9m2pju.hamradio.my", 7300),
        "JA2YYF (Giappone)":         ("ja2yyf.dxcluster.jp", 7300),
    }

    _BANDE_FILTRO = ["160M","80M","60M","40M","30M","20M","17M","15M","12M","10M","6M","2M","70CM","23CM"]

    def __init__(self, parent, app_ref):
        super().__init__(parent)
        self.title(T("dxc_titolo"))
        self.geometry("980x620")
        self.minsize(760, 420)
        self.app_ref = app_ref
        # Porta in primo piano (evita che finisca dietro la finestra principale)
        self.transient(parent)
        self.lift()
        self.focus_force()
        self.after(200, lambda: (self.lift(), self.focus_force()))
        self._sock = None
        self._thread = None
        self._running = False
        self._spot_queue = []
        self._paused = False
        self._dxcc_nel_log = set()
        self._evidenzia_nuovi = ctk.BooleanVar(value=False)
        self._filtri_banda = {}
        self._filtro_modo = ctk.StringVar(value="Tutti")
        self._filtro_call = ctk.StringVar(value="")
        # Auto-riconnessione
        self._auto_riconnetti = ctk.BooleanVar(value=True)
        self._disconnessione_voluta = False
        self._reconnect_after = None
        self._tentativi_reconnect = 0
        # Notifiche DXCC nuovi
        self._notifica_dxcc = ctk.BooleanVar(value=True)
        self._qsy_al_doppioclick = ctk.BooleanVar(value=False)
        self._dig_come_usbd = ctk.BooleanVar(value=True)
        self._usa_bandplan = ctk.BooleanVar(value=True)
        self._suono_dxcc = ctk.BooleanVar(value=True)
        self._dxcc_gia_notificati = set()

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10,4))

        ctk.CTkLabel(top, text=T("dxc_server"), font=ctk.CTkFont(size=11)).pack(side="left")
        # Unisce i server predefiniti con quelli custom salvati nel profilo
        self._server_custom = self._carica_server_custom()
        self._carica_opzioni()
        self._tutti_server = {**self.SERVERS, **self._server_custom}
        self.var_server = ctk.StringVar(value=list(self._tutti_server.keys())[0])
        self.opt_server = ctk.CTkOptionMenu(top, variable=self.var_server,
                          values=list(self._tutti_server.keys()),
                          width=210, height=28,
                          font=ctk.CTkFont(size=11))
        self.opt_server.pack(side="left", padx=6)
        ctk.CTkButton(top, text=T("dxc_add_server"), width=80, height=28,
                      command=self._aggiungi_server,
                      fg_color="#4A5568", font=ctk.CTkFont(size=11)).pack(side="left", padx=(4,0))

        self.btn_conn = ctk.CTkButton(top, text=T("dxc_connetti"), width=110, height=28,
                                       command=self._toggle_connessione,
                                       fg_color="#276749", hover_color="#2F855A",
                                       font=ctk.CTkFont(size=11))
        self.btn_conn.pack(side="left", padx=4)

        self.lbl_stato = ctk.CTkLabel(top, text=T("dxc_disconnesso"),
                                       font=ctk.CTkFont(size=11), text_color="gray")
        self.lbl_stato.pack(side="left", padx=8)

        ctk.CTkButton(top, text=T("dxc_opzioni"), width=100, height=28,
                      command=self._apri_menu_opzioni,
                      fg_color="#4A5568", font=ctk.CTkFont(size=11)).pack(side="right")
        ctk.CTkButton(top, text=T("dxc_invia_spot"), width=110, height=28,
                      command=self._apri_invia_spot,
                      fg_color="#2B6CB0", hover_color="#1A4480",
                      font=ctk.CTkFont(size=11)).pack(side="right", padx=4)
        self.btn_pause = ctk.CTkButton(top, text=T("dxc_pausa"), width=80, height=28,
                      command=self._toggle_pausa,
                      fg_color="#4A5568", font=ctk.CTkFont(size=11))
        self.btn_pause.pack(side="right", padx=4)
        ctk.CTkButton(top, text=T("dxc_pulisci"), width=80, height=28,
                      command=self._pulisci,
                      fg_color="#4A5568", font=ctk.CTkFont(size=11)).pack(side="right", padx=4)

        import tkinter.ttk as _ttk
        frame_tree = ctk.CTkFrame(self)
        frame_tree.pack(fill="both", expand=True, padx=10, pady=4)

        style = _ttk.Style()
        style.theme_use("default")
        style.configure("DXC.Treeview", background="#101825", foreground="#E2E8F0",
                        rowheight=22, fieldbackground="#101825", font=("Consolas", 10))
        style.configure("DXC.Treeview.Heading", background="#1A365D",
                        foreground="white", font=("Arial", 10, "bold"), relief="flat")
        style.map("DXC.Treeview", background=[("selected","#2B6CB0")])

        cols = ("utc","dx","freq","banda","modo","spotter","commento")
        self.tree = _ttk.Treeview(frame_tree, columns=cols, show="headings",
                                   style="DXC.Treeview")
        headers = {"utc":T("dxc_col_utc"),"dx":T("dxc_col_dx"),"freq":T("dxc_col_freq"),"banda":T("dxc_col_banda"),
                   "modo":T("dxc_col_modo"),"spotter":T("dxc_col_spotter"),"commento":T("dxc_col_commento")}
        widths  = {"utc":55,"dx":110,"freq":85,"banda":60,"modo":60,
                   "spotter":100,"commento":330}
        for c in cols:
            self.tree.heading(c, text=headers[c])
            self.tree.column(c, width=widths[c],
                             anchor="w" if c in ("dx","spotter","commento") else "center")

        vsb = _ttk.Scrollbar(frame_tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        colori_banda = {
            "160M":"#9F7AEA","80M":"#B794F4","60M":"#805AD5","40M":"#4299E1",
            "30M":"#63B3ED","20M":"#48BB78","17M":"#68D391","15M":"#F6AD55",
            "12M":"#ED8936","10M":"#FC8181","6M":"#F56565","2M":"#E53E3E",
            "70CM":"#C53030","23CM":"#9B2C2C",
        }
        for banda, col in colori_banda.items():
            self.tree.tag_configure(f"b_{banda}", foreground=col)
        self.tree.tag_configure("nuovo_dxcc", background="#2D3A1F", foreground="#9AE6B4")

        self.tree.bind("<Button-3>", self._menu_contestuale)
        self.tree.bind("<Double-1>", lambda e: self._aggiungi_qso_da_spot())

        cmd_frame = ctk.CTkFrame(self, fg_color="transparent")
        cmd_frame.pack(fill="x", padx=10, pady=(2,10))
        ctk.CTkLabel(cmd_frame, text=T("dxc_comando"), font=ctk.CTkFont(size=11)).pack(side="left")
        self.entry_cmd = ctk.CTkEntry(cmd_frame, placeholder_text=T("dxc_cmd_ph"),
                                       font=ctk.CTkFont(size=11), height=28)
        self.entry_cmd.pack(side="left", expand=True, fill="x", padx=6)
        self.entry_cmd.bind("<Return>", lambda e: self._invia_comando())
        ctk.CTkButton(cmd_frame, text=T("dxc_invia"), width=70, height=28,
                      command=self._invia_comando,
                      fg_color="#2B6CB0", font=ctk.CTkFont(size=11)).pack(side="left")

        self.lbl_count = ctk.CTkLabel(cmd_frame, text=T("dxc_spot_count", n=0),
                                       font=ctk.CTkFont(size=10), text_color="gray")
        self.lbl_count.pack(side="right", padx=6)

        self._n_spot = 0
        self._carica_dxcc_log()
        self.protocol("WM_DELETE_WINDOW", self._chiudi)
        self.after(400, self._processa_coda)

    def _carica_server_custom(self):
        """Carica i server DX cluster personalizzati dal profilo."""
        try:
            profili = self.app_ref._carica_profili()
            dati = profili.get(self.app_ref.profilo_attivo, {}) if self.app_ref.profilo_attivo else {}
            custom = dati.get('dxc_server_custom', {})
            # Converte {nome: [host, port]} in {nome: (host, port)}
            return {k: (v[0], int(v[1])) for k, v in custom.items()
                    if isinstance(v, (list, tuple)) and len(v) == 2}
        except Exception:
            return {}

    def _salva_server_custom(self):
        """Salva i server custom nel profilo."""
        try:
            profili = self.app_ref._carica_profili()
            nome_prof = self.app_ref.profilo_attivo
            if nome_prof and nome_prof in profili:
                profili[nome_prof]['dxc_server_custom'] = {
                    k: [v[0], v[1]] for k, v in self._server_custom.items()}
                with open(self.app_ref.profili_path, 'w', encoding='utf-8') as f:
                    json.dump(profili, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _carica_opzioni(self):
        """Carica le opzioni del DX Cluster dal profilo attivo."""
        try:
            profili = self.app_ref._carica_profili()
            dati = profili.get(self.app_ref.profilo_attivo, {}) if self.app_ref.profilo_attivo else {}
            opz = dati.get('dxc_opzioni', {})
            if not isinstance(opz, dict):
                return
            mappa = {
                'evidenzia_nuovi': self._evidenzia_nuovi,
                'notifica_dxcc':   self._notifica_dxcc,
                'suono_dxcc':      self._suono_dxcc,
                'auto_riconnetti': self._auto_riconnetti,
                'qsy_dblclick':    self._qsy_al_doppioclick,
                'dig_come_usbd':   self._dig_come_usbd,
                'usa_bandplan':    self._usa_bandplan,
            }
            for chiave, var in mappa.items():
                if chiave in opz:
                    try: var.set(bool(opz[chiave]))
                    except Exception: pass
            # Filtro modo e callsign (stringhe)
            if 'filtro_modo' in opz:
                try: self._filtro_modo.set(str(opz['filtro_modo']))
                except Exception: pass
            if 'filtro_call' in opz:
                try: self._filtro_call.set(str(opz['filtro_call']))
                except Exception: pass
            # Filtri banda: ricrea le BooleanVar per le bande salvate
            bande_on = opz.get('filtri_banda', [])
            if isinstance(bande_on, list):
                for banda in bande_on:
                    self._filtri_banda[banda] = ctk.BooleanVar(value=True)
        except Exception:
            pass

    def _salva_opzioni(self):
        """Salva le opzioni del DX Cluster nel profilo attivo."""
        try:
            profili = self.app_ref._carica_profili()
            nome_prof = self.app_ref.profilo_attivo
            if nome_prof and nome_prof in profili:
                profili[nome_prof]['dxc_opzioni'] = {
                    'evidenzia_nuovi': bool(self._evidenzia_nuovi.get()),
                    'notifica_dxcc':   bool(self._notifica_dxcc.get()),
                    'suono_dxcc':      bool(self._suono_dxcc.get()),
                    'auto_riconnetti': bool(self._auto_riconnetti.get()),
                    'qsy_dblclick':    bool(self._qsy_al_doppioclick.get()),
                    'dig_come_usbd':   bool(self._dig_come_usbd.get()),
                    'usa_bandplan':    bool(self._usa_bandplan.get()),
                    'filtro_modo':     self._filtro_modo.get(),
                    'filtro_call':     self._filtro_call.get(),
                    'filtri_banda':    [b for b, v in self._filtri_banda.items()
                                        if v.get()],
                }
                with open(self.app_ref.profili_path, 'w', encoding='utf-8') as f:
                    json.dump(profili, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _aggiungi_server(self):
        """Dialog per aggiungere un server DX cluster personalizzato."""
        dlg = ctk.CTkToplevel(self)
        dlg.title(T("dxc_add_srv_titolo"))
        dlg.geometry("380x300")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set(); dlg.lift(); dlg.focus_force()
        dlg.after(200, lambda: (dlg.lift(), dlg.focus_force()))

        ctk.CTkLabel(dlg, text=T("dxc_add_srv_head"),
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(14,10))

        frame = ctk.CTkFrame(dlg, fg_color="transparent")
        frame.pack(fill="x", padx=24)

        ctk.CTkLabel(frame, text=T("dxc_srv_nome"), anchor="w",
                     font=ctk.CTkFont(size=11)).pack(fill="x", pady=(4,0))
        e_nome = ctk.CTkEntry(frame, placeholder_text=T("dxc_srv_nome_ph"), height=30)
        e_nome.pack(fill="x", pady=(0,6))

        ctk.CTkLabel(frame, text=T("dxc_srv_host"), anchor="w",
                     font=ctk.CTkFont(size=11)).pack(fill="x", pady=(4,0))
        e_host = ctk.CTkEntry(frame, placeholder_text=T("dxc_srv_host_ph"), height=30)
        e_host.pack(fill="x", pady=(0,6))

        ctk.CTkLabel(frame, text=T("dxc_srv_porta"), anchor="w",
                     font=ctk.CTkFont(size=11)).pack(fill="x", pady=(4,0))
        e_port = ctk.CTkEntry(frame, placeholder_text=T("dxc_srv_porta_ph"), height=30)
        e_port.pack(fill="x", pady=(0,4))

        def _salva():
            nome = e_nome.get().strip()
            host = e_host.get().strip()
            port = e_port.get().strip()
            if not nome or not host or not port:
                messagebox.showwarning(T("dxc_dati_mancanti"),
                    T("dxc_compila_tutto"), parent=dlg)
                return
            try:
                port_i = int(port)
            except ValueError:
                messagebox.showwarning(T("dxc_porta_invalida"),
                    T("dxc_porta_num"), parent=dlg)
                return
            self._server_custom[nome] = (host, port_i)
            self._tutti_server = {**self.SERVERS, **self._server_custom}
            self.opt_server.configure(values=list(self._tutti_server.keys()))
            self.var_server.set(nome)
            self._salva_server_custom()
            dlg.destroy()

        fr = ctk.CTkFrame(dlg, fg_color="transparent")
        fr.pack(fill="x", padx=24, pady=14)
        ctk.CTkButton(fr, text=T("dxc_salva"), command=_salva, height=34,
                      fg_color="#276749", hover_color="#2F855A"
                      ).pack(side="left", expand=True, fill="x", padx=(0,6))
        ctk.CTkButton(fr, text=T("dxc_annulla"), command=dlg.destroy,
                      height=34, width=90, fg_color="#718096").pack(side="left")

    def _toggle_connessione(self):
        if self._running:
            self._disconnetti()
        else:
            self._connetti()

    def _connetti(self):
        import socket, threading
        nome = self.var_server.get()
        host, port = self._tutti_server[nome]
        mycall = ""
        try:
            profili = self.app_ref._carica_profili()
            dati = profili.get(self.app_ref.profilo_attivo, {}) if self.app_ref.profilo_attivo else {}
            mycall = dati.get('callsign','').strip().upper()
        except Exception:
            pass
        if not mycall:
            mycall = self.app_ref.entry_owner.get().strip().upper()
        if not mycall:
            messagebox.showwarning(T("dxc_callsign_mancante"),
                T("dxc_imposta_call"),
                parent=self)
            return

        self.lbl_stato.configure(text=T("dxc_connessione"), text_color="#F6AD55")
        self.btn_conn.configure(state="disabled")
        self._disconnessione_voluta = False

        def _run():
            try:
                self._sock = socket.create_connection((host, port), timeout=15)
                self._sock.settimeout(1.0)
                self._running = True
                self._tentativi_reconnect = 0
                self._ui_stato(T("dxc_connesso", host=host), "#48BB78",
                               T("dxc_disconnetti"), "#9C4221", "#7B3618")
                buf = b""
                login_inviato = False
                import time as _time
                t_conn = _time.time()
                while self._running:
                    try:
                        data = self._sock.recv(4096)
                        if not data:
                            break
                        buf += data
                    except TimeoutError:
                        # Nessun dato: se non ho ancora fatto login dopo 3s, invialo comunque
                        if not login_inviato and (_time.time() - t_conn) > 3:
                            try:
                                self._sock.sendall((mycall + "\r\n").encode())
                                login_inviato = True
                            except OSError:
                                break
                        continue
                    except OSError:
                        break

                    # Rileva prompt di login SOLO su righe che finiscono senza newline
                    # (i prompt non hanno \n finale) e contengono parole chiave precise
                    if not login_inviato:
                        coda = buf.decode('utf-8', errors='replace')
                        # Prendi l'ultima riga parziale (dopo l'ultimo \n)
                        ultima = coda.rsplit('\n', 1)[-1].lower()
                        if any(k in ultima for k in
                               ('login:', 'call:', 'callsign:', 'please enter',
                                'your call', 'enter your')):
                            try:
                                self._sock.sendall((mycall + "\r\n").encode())
                                login_inviato = True
                            except OSError:
                                break

                    # Processa TUTTE le righe complete disponibili (login o no)
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        riga = line.decode('utf-8', errors='replace').strip()
                        # Se non ho ancora loggato e la riga chiede il call, rispondi
                        if not login_inviato:
                            low = riga.lower()
                            if any(k in low for k in
                                   ('login', 'callsign', 'enter your call', 'your call')):
                                try:
                                    self._sock.sendall((mycall + "\r\n").encode())
                                    login_inviato = True
                                except OSError:
                                    break
                                continue
                        self._parse_riga(riga)
            except Exception as ex:
                self._ui_stato(f"✗ {ex}", "#FC8181",
                               "🔌 Connetti", "#276749", "#2F855A")
                self._pianifica_riconnessione()
                return
            self._running = False
            self._ui_stato(T("dxc_disconnesso"), "gray",
                           T("dxc_connetti"), "#276749", "#2F855A")
            self._pianifica_riconnessione()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def _ui_stato(self, testo, colore_txt, btn_txt, btn_fc, btn_hc):
        """Aggiorna label stato e pulsante dal thread, in modo sicuro.
        Se la finestra è già stata chiusa, non fa nulla."""
        def _apply():
            try:
                if not self.winfo_exists():
                    return
                self.lbl_stato.configure(text=testo, text_color=colore_txt)
                self.btn_conn.configure(text=btn_txt, state="normal",
                                        fg_color=btn_fc, hover_color=btn_hc)
            except Exception:
                pass
        try:
            if self.winfo_exists():
                self.after(0, _apply)
        except Exception:
            pass

    def _disconnetti(self):
        self._disconnessione_voluta = True
        self._running = False
        if self._reconnect_after:
            try: self.after_cancel(self._reconnect_after)
            except Exception: pass
            self._reconnect_after = None
        self._tentativi_reconnect = 0
        try:
            if self._sock: self._sock.close()
        except Exception:
            pass
        self._sock = None

    def _pianifica_riconnessione(self):
        """Se la caduta non è voluta e l'auto-riconnessione è attiva,
        riprova dopo un ritardo crescente (5s, 10s, 20s, max 30s)."""
        try:
            if self._disconnessione_voluta or not self._auto_riconnetti.get():
                return
            if not self.winfo_exists():
                return
        except Exception:
            return
        self._tentativi_reconnect += 1
        ritardo = min(30, 5 * (2 ** min(self._tentativi_reconnect - 1, 3)))  # 5,10,20,30…

        def _mostra_countdown(rimasti):
            try:
                if not self.winfo_exists() or self._disconnessione_voluta:
                    return
                if rimasti <= 0:
                    self.lbl_stato.configure(text=T("dxc_riconnetto"), text_color="#F6AD55")
                    self._connetti()
                    return
                self.lbl_stato.configure(
                    text=T("dxc_riconnetto_tra", s=rimasti, n=self._tentativi_reconnect),
                    text_color="#F6AD55")
                self._reconnect_after = self.after(1000, lambda: _mostra_countdown(rimasti - 1))
            except Exception:
                pass

        def _avvia():
            try:
                if self.winfo_exists() and not self._disconnessione_voluta:
                    _mostra_countdown(ritardo)
            except Exception:
                pass
        try:
            self.after(0, _avvia)
        except Exception:
            pass

    def _chiudi(self):
        self._disconnetti()
        self.destroy()

    def _parse_riga(self, riga):
        if 'DX de' not in riga:
            return
        # Isola la parte dopo "DX de"
        idx = riga.find('DX de')
        corpo = riga[idx+5:].strip()

        # Formati possibili:
        #   SPOTTER:  FREQ  DXCALL  COMMENTO...  HHMMZ
        #   SPOTTER   FREQ  DXCALL  COMMENTO...  HHMM
        # Spotter fino ai ":" o primo spazio
        m = re.match(r'^([\w/\-#]+)[:\s]+([\d.]+)\s+([\w/\-]+)\s+(.*)$', corpo)
        if not m:
            return
        spotter, freq, dxcall, resto = m.groups()

        try:
            f_khz = float(freq)
        except ValueError:
            return

        # Estrai UTC dalla fine (4 cifre, opz. Z) se presente
        utc = ""
        mu = re.search(r'(\d{4})Z?\s*$', resto)
        if mu:
            utc = mu.group(1)
            commento = resto[:mu.start()].strip()
        else:
            commento = resto.strip()
            import datetime as _dt
            utc = _dt.datetime.utcnow().strftime("%H%M")

        banda = self._freq_to_banda(f_khz)
        modo  = self._deduci_modo(f_khz, commento)
        self._spot_queue.append({
            'utc': f"{utc[:2]}:{utc[2:]}",
            'dx': dxcall.upper(),
            'freq': freq,
            'banda': banda,
            'modo': modo,
            'spotter': spotter.rstrip(':').upper(),
            'commento': commento.strip(),
        })

    @staticmethod
    def _freq_to_banda(khz):
        tab = [(1800,2000,"160M"),(3500,4000,"80M"),(5250,5450,"60M"),
               (7000,7300,"40M"),(10100,10150,"30M"),(14000,14350,"20M"),
               (18068,18168,"17M"),(21000,21450,"15M"),(24890,24990,"12M"),
               (28000,29700,"10M"),(50000,54000,"6M"),(144000,148000,"2M"),
               (420000,450000,"70CM"),(1240000,1300000,"23CM")]
        for lo, hi, b in tab:
            if lo <= khz <= hi:
                return b
        return "?"

    @staticmethod
    def _deduci_modo(khz, commento):
        c = commento.upper()
        for m in ("FT8","FT4","CW","SSB","RTTY","PSK","JT65","MSK144","SSTV","AM","FM"):
            if m in c:
                return m
        return ""

    def _processa_coda(self):
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        if not self._paused:
            while self._spot_queue:
                try:
                    self._mostra_spot(self._spot_queue.pop(0))
                except Exception:
                    break
        self.after(400, self._processa_coda)

    def _mostra_spot(self, spot):
        if self._filtri_banda:
            attive = [b for b,v in self._filtri_banda.items() if v.get()]
            if attive and spot['banda'] not in attive:
                return
        fm = self._filtro_modo.get()
        if fm != "Tutti" and spot['modo'] != fm:
            return
        # Filtro callsign (wildcard * e ?, oppure prefisso, oppure call esatto)
        fc = self._filtro_call.get().strip().upper()
        if fc and not self._match_call(spot['dx'], fc):
            return

        tags = [f"b_{spot['banda']}"]
        if self._evidenzia_nuovi.get():
            pfx = self._prefisso(spot['dx'])
            if pfx and pfx not in self._dxcc_nel_log:
                tags.append("nuovo_dxcc")
                # Notifica (una volta per prefisso+banda per non ripetere)
                chiave = f"{pfx}_{spot['banda']}"
                if chiave not in self._dxcc_gia_notificati:
                    self._dxcc_gia_notificati.add(chiave)
                    self._notifica_dxcc_nuovo(spot, pfx)

        self.tree.insert("", 0, values=(
            spot['utc'], spot['dx'], spot['freq'], spot['banda'],
            spot['modo'], spot['spotter'], spot['commento']), tags=tuple(tags))
        self._n_spot += 1
        self.lbl_count.configure(text=T("dxc_spot_count", n=self._n_spot))
        children = self.tree.get_children()
        if len(children) > 500:
            for iid in children[500:]:
                self.tree.delete(iid)

    def _notifica_dxcc_nuovo(self, spot, pfx):
        """Notifica sonora + popup non invasivo per un possibile DXCC nuovo."""
        # Suono (non bloccante)
        if self._suono_dxcc.get():
            try:
                import sys
                if sys.platform.startswith("win"):
                    import winsound
                    winsound.PlaySound("SystemAsterisk", winsound.SND_ASYNC | winsound.SND_ALIAS)
                else:
                    self.bell()
            except Exception:
                try: self.bell()
                except Exception: pass
        # Popup toast non bloccante
        if self._notifica_dxcc.get():
            try:
                self._mostra_toast(spot, pfx)
            except Exception:
                pass

    def _mostra_toast(self, spot, pfx):
        """Piccola finestra toast in basso a destra che sparisce da sola."""
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.attributes('-topmost', True)
        try:
            toast.attributes('-alpha', 0.0)
        except Exception:
            pass
        bg = "#1A3A2A"
        frame = tk.Frame(toast, bg=bg, highlightbackground="#48BB78",
                         highlightthickness=2)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=T("dxc_toast_titolo"), font=("Arial", 11, "bold"),
                 fg="#9AE6B4", bg=bg).pack(anchor="w", padx=12, pady=(8,2))
        tk.Label(frame, text=f"{spot['dx']}  ·  {spot['banda']}  {spot['modo']}",
                 font=("Consolas", 13, "bold"), fg="#F0FFF4", bg=bg).pack(anchor="w", padx=12)
        tk.Label(frame, text=f"{spot['freq']} kHz  ·  {T('dxc_toast_prefisso')} {pfx}",
                 font=("Arial", 9), fg="#C6F6D5", bg=bg).pack(anchor="w", padx=12, pady=(0,8))

        toast.update_idletasks()
        w, h = toast.winfo_width(), toast.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = sw - w - 30, sh - h - 60
        toast.geometry(f"+{x}+{y}")

        def _fade_in(a=0.0):
            try:
                if not toast.winfo_exists(): return
                a = min(1.0, a + 0.12)
                toast.attributes('-alpha', a)
                if a < 1.0:
                    toast.after(25, lambda: _fade_in(a))
                else:
                    toast.after(3500, _fade_out)
            except Exception:
                pass
        def _fade_out(a=1.0):
            try:
                if not toast.winfo_exists(): return
                a = max(0.0, a - 0.08)
                toast.attributes('-alpha', a)
                if a > 0.0:
                    toast.after(25, lambda: _fade_out(a))
                else:
                    toast.destroy()
            except Exception:
                try: toast.destroy()
                except Exception: pass
        # Click per chiudere subito
        for w_ in (frame, *frame.winfo_children()):
            w_.bind("<Button-1>", lambda e: toast.destroy())
        _fade_in()

    @staticmethod
    def _match_call(call, pattern):
        """Verifica se 'call' matcha uno dei pattern (separati da virgola).
        Supporta wildcard * e ?. Se il pattern non ha wildcard, matcha
        come 'inizia con' (così 'IK1' prende IK1ABC) oppure esatto se
        contiene già la lunghezza completa.
        Esempi:
          IK1*     → tutti gli IK1...
          IK1ABC   → solo IK1ABC (o call che iniziano con IK1ABC)
          CU,CO,CM → Cuba (prefissi cubani)
          *DX*     → contiene DX
        """
        import fnmatch
        call = call.upper()
        for pat in pattern.split(','):
            pat = pat.strip().upper()
            if not pat:
                continue
            if '*' in pat or '?' in pat:
                if fnmatch.fnmatch(call, pat):
                    return True
            else:
                # Senza wildcard: match "inizia con" (prefisso o call parziale)
                if call.startswith(pat):
                    return True
        return False

    @staticmethod
    def _prefisso(call):
        m = re.match(r'^([A-Z0-9]{1,3}?)\d', call.upper())
        return m.group(1) if m else call[:2]

    def _carica_dxcc_log(self):
        self._dxcc_nel_log.clear()
        self._dxcc_gia_notificati.clear()
        try:
            for q in self.app_ref.qsos_caricati:
                c = str(q.get('call','')).upper()
                if c:
                    self._dxcc_nel_log.add(self._prefisso(c))
        except Exception:
            pass

    def _toggle_pausa(self):
        self._paused = not self._paused
        self.btn_pause.configure(text=T("dxc_riprendi") if self._paused else T("dxc_pausa"))

    def _pulisci(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._n_spot = 0
        self.lbl_count.configure(text=T("dxc_spot_count", n=0))

    def _apri_invia_spot(self):
        """Dialog per inviare uno spot al cluster: DX <call> <freq> <commento>."""
        if not self._sock or not self._running:
            messagebox.showwarning(T("dxc_non_connesso"),
                T("dxc_connetti_prima"), parent=self)
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title(T("dxc_spot_titolo"))
        dlg.geometry("400x330")
        dlg.resizable(False, False)
        dlg.grab_set(); dlg.lift(); dlg.focus_force()

        ctk.CTkLabel(dlg, text=T("dxc_spot_head"),
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(14,2))
        ctk.CTkLabel(dlg, text=T("dxc_spot_sub"),
                     font=ctk.CTkFont(size=10), text_color="gray").pack(pady=(0,10))

        frame = ctk.CTkFrame(dlg, fg_color="transparent")
        frame.pack(fill="x", padx=24)

        ctk.CTkLabel(frame, text=T("dxc_spot_call"), anchor="w",
                     font=ctk.CTkFont(size=11)).pack(fill="x", pady=(4,0))
        e_call = ctk.CTkEntry(frame, placeholder_text=T("sb_owner_ph"), height=30)
        e_call.pack(fill="x", pady=(0,6))

        ctk.CTkLabel(frame, text=T("dxc_spot_freq"), anchor="w",
                     font=ctk.CTkFont(size=11)).pack(fill="x", pady=(4,0))
        e_freq = ctk.CTkEntry(frame, placeholder_text=T("dxc_freq_ph"), height=30)
        e_freq.pack(fill="x", pady=(0,6))

        ctk.CTkLabel(frame, text=T("dxc_spot_comm"), anchor="w",
                     font=ctk.CTkFont(size=11)).pack(fill="x", pady=(4,0))
        e_comm = ctk.CTkEntry(frame, placeholder_text=T("dxc_spot_comm_ph"), height=30)
        e_comm.pack(fill="x", pady=(0,4))

        # Precompila con la spot selezionata, se presente
        sel = self.tree.selection()
        if sel:
            v = self.tree.item(sel[0], "values")
            e_call.insert(0, v[1]); e_freq.insert(0, v[2])

        def _invia():
            call = e_call.get().strip().upper()
            freq = e_freq.get().strip()
            comm = e_comm.get().strip()
            if not call or not freq:
                messagebox.showwarning(T("dxc_dati_mancanti"),
                    T("dxc_compila_tutto"), parent=dlg)
                return
            try:
                float(freq)
            except ValueError:
                messagebox.showwarning(T("dxc_freq_invalida"),
                    T("dxc_freq_khz"), parent=dlg)
                return
            # Comando standard DXSpider/AR-Cluster: DX <freq> <call> <commento>
            cmd = f"DX {freq} {call} {comm}".strip()
            try:
                self._sock.sendall((cmd + "\r\n").encode())
                messagebox.showinfo(T("dxc_spot_inviato"),
                    T("dxc_spot_ok", call=call, freq=freq), parent=dlg)
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror(T("dxc_errore"), str(ex), parent=dlg)

        fr_btn = ctk.CTkFrame(dlg, fg_color="transparent")
        fr_btn.pack(fill="x", padx=24, pady=14)
        ctk.CTkButton(fr_btn, text=T("dxc_spot_invia"), command=_invia, height=34,
                      fg_color="#276749", hover_color="#2F855A"
                      ).pack(side="left", expand=True, fill="x", padx=(0,6))
        ctk.CTkButton(fr_btn, text=T("dxc_annulla"), command=dlg.destroy,
                      height=34, width=90, fg_color="#718096").pack(side="left")

    def _invia_comando(self):
        cmd = self.entry_cmd.get().strip()
        if not cmd or not self._sock:
            return
        try:
            self._sock.sendall((cmd + "\r\n").encode())
            self.entry_cmd.delete(0, 'end')
        except Exception as ex:
            messagebox.showerror(T("dxc_errore"), str(ex), parent=self)

    def _apri_menu_opzioni(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title(T("dxc_opz_titolo"))
        dlg.geometry("400x600")
        dlg.transient(self)
        dlg.after(200, lambda: (dlg.lift(), dlg.focus_force()))
        dlg.grab_set(); dlg.lift()

        def _chiudi_opzioni():
            self._salva_opzioni()
            dlg.destroy()
        # Salva anche se si chiude con la X della finestra
        dlg.protocol("WM_DELETE_WINDOW", _chiudi_opzioni)

        # Pulsante Chiudi ancorato in basso (sempre visibile, fuori dallo scroll)
        bottom = ctk.CTkFrame(dlg, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", pady=8)
        ctk.CTkButton(bottom, text=T("dxc_chiudi"), command=_chiudi_opzioni,
                      width=120, fg_color="#2B6CB0").pack()

        # Contenuto scrollabile (così nessun controllo resta tagliato,
        # in qualsiasi lingua)
        cont = ctk.CTkScrollableFrame(dlg, fg_color="transparent")
        cont.pack(fill="both", expand=True, padx=4, pady=(4, 0))

        ctk.CTkLabel(cont, text=T("dxc_filtri_banda"),
                     font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(12,4))
        frame_b = ctk.CTkFrame(cont, fg_color="transparent")
        frame_b.pack(fill="x", padx=16)
        for i, banda in enumerate(self._BANDE_FILTRO):
            v = self._filtri_banda.get(banda) or ctk.BooleanVar(value=False)
            self._filtri_banda[banda] = v
            ctk.CTkCheckBox(frame_b, text=banda, variable=v,
                            font=ctk.CTkFont(size=11), width=70
                            ).grid(row=i//3, column=i%3, sticky="w", padx=4, pady=2)

        ctk.CTkLabel(cont, text=T("dxc_filtro_modo"),
                     font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(14,4))
        ctk.CTkOptionMenu(cont, variable=self._filtro_modo,
                          values=[T("dxc_tutti"),"FT8","FT4","CW","SSB","RTTY","PSK"],
                          width=160).pack()

        ctk.CTkLabel(cont, text=T("dxc_filtro_call"),
                     font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(14,2))
        ctk.CTkEntry(cont, textvariable=self._filtro_call, width=220,
                     placeholder_text=T("dxc_filtro_call_ph")).pack()
        ctk.CTkLabel(cont,
                     text=T("dxc_filtro_call_hint"),
                     font=ctk.CTkFont(size=9), text_color="gray",
                     justify="center").pack(pady=(2,0))

        ctk.CTkCheckBox(cont, text=T("dxc_evidenzia_dxcc"),
                        variable=self._evidenzia_nuovi,
                        font=ctk.CTkFont(size=11),
                        command=self._carica_dxcc_log).pack(pady=(16,4))

        # Sezione notifiche DXCC nuovo
        ctk.CTkCheckBox(cont, text=T("dxc_notifica_dxcc"),
                        variable=self._notifica_dxcc,
                        font=ctk.CTkFont(size=11)).pack(pady=(2,2))
        ctk.CTkCheckBox(cont, text=T("dxc_suono_dxcc"),
                        variable=self._suono_dxcc,
                        font=ctk.CTkFont(size=11)).pack(pady=(2,2))
        # Auto-riconnessione
        ctk.CTkCheckBox(cont, text=T("dxc_auto_riconn"),
                        variable=self._auto_riconnetti,
                        font=ctk.CTkFont(size=11)).pack(pady=(8,4))
        # QSY radio al doppio click
        ctk.CTkCheckBox(cont, text=T("dxc_qsy_dblclick"),
                        variable=self._qsy_al_doppioclick,
                        font=ctk.CTkFont(size=11)).pack(pady=(2,4))
        # Modi digitali → USB-D invece di RTTY
        ctk.CTkCheckBox(cont, text=T("dxc_dig_usbd"),
                        variable=self._dig_come_usbd,
                        font=ctk.CTkFont(size=11)).pack(pady=(2,4))
        # Band plan IARU R1: deduci il modo dalla frequenza
        ctk.CTkCheckBox(cont, text=T("dxc_bandplan"),
                        variable=self._usa_bandplan,
                        font=ctk.CTkFont(size=11)).pack(pady=(2,4))
        # Diagnostica modi radio (per calibrare i valori del proprio rig)
        ctk.CTkButton(cont, text=T("dxc_diag_modi"), command=self._diagnostica_modi,
                      font=ctk.CTkFont(size=11), fg_color="#4A5568",
                      height=28).pack(pady=(6,4))

        ctk.CTkLabel(cont, text=T("dxc_filtri_nota")+"\n"+T("dxc_dblclick_nota"),
                     font=ctk.CTkFont(size=10), text_color="gray",
                     justify="left").pack(pady=(10,4))

    def _menu_contestuale(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        import tkinter as _tk
        menu = _tk.Menu(self, tearoff=0)
        menu.add_command(label=T("dxc_aggiungi_qso"),
                         command=self._aggiungi_qso_da_spot)
        menu.add_command(label=T("dxc_qsy_radio"),
                         command=self._qsy_da_spot)
        menu.add_command(label=T("menu_copia_call"),
                         command=self._copia_call)
        menu.tk_popup(event.x_root, event.y_root)

    def _copia_call(self):
        sel = self.tree.selection()
        if sel:
            call = self.tree.item(sel[0], "values")[1]
            self.clipboard_clear()
            self.clipboard_append(call)

    def _diagnostica_modi(self):
        """Finestra che legge in tempo reale il valore Mode grezzo dalla radio.
        Serve a calibrare la mappa modi per il proprio rig: metti la radio in
        un modo, leggi il numero, e comunicalo per adattare il codice."""
        rig = getattr(self.app_ref, "_omnirig", None)
        if rig is None or not rig.disponibile():
            messagebox.showwarning(T("dxc_omnirig_no"),
                                   T("dxc_omnirig_assente"), parent=self)
            return
        dlg = ctk.CTkToplevel(self)
        dlg.title(T("dxc_diag_modi"))
        dlg.geometry("460x380")
        dlg.transient(self); dlg.lift(); dlg.focus_force()
        dlg.after(200, lambda: (dlg.lift(), dlg.focus_force()))

        ctk.CTkLabel(dlg, text=T("dxc_diag_istruzioni"),
                     font=ctk.CTkFont(size=11), justify="left",
                     wraplength=420).pack(pady=(12,8), padx=16)

        box = ctk.CTkTextbox(dlg, width=420, height=210, font=("Consolas", 12))
        box.pack(padx=16, pady=(0,8), fill="both", expand=True)

        def _leggi():
            try:
                # Assicura la connessione COM prima di leggere
                if not rig._assicura():
                    box.insert("end", "OmniRig non connesso. Verifica che sia "
                               "avviato e collegato alla radio (RIG1 verde).\n")
                    box.see("end")
                    return
                m = int(rig._rig.Mode)
                f = rig.get_freq()
                modo_str = rig.get_modo() or "?"
                stato = rig.stato() or "?"
                riga = f"Mode = 0x{m:08X} ({m})  →  {modo_str}   freq={f}   [{stato}]\n"
                box.insert("end", riga)
                box.see("end")
            except Exception as ex:
                box.insert("end", f"Errore: {ex}\n")
                box.see("end")

        def _leggi_ini():
            try:
                box.insert("end", "\n=== Configurazione OmniRig (.ini) ===\n")
                box.insert("end", rig.diagnostica_ini() + "\n")
                box.see("end")
            except Exception as ex:
                box.insert("end", f"Errore .ini: {ex}\n")
                box.see("end")

        ctk.CTkButton(dlg, text=T("dxc_diag_leggi"), command=_leggi,
                      height=34, fg_color="#2B6CB0").pack(pady=(0,4))
        ctk.CTkButton(dlg, text=T("dxc_diag_ini"), command=_leggi_ini,
                      height=30, fg_color="#4A5568").pack(pady=(0,4))
        ctk.CTkButton(dlg, text=T("dxc_chiudi"), command=dlg.destroy,
                      height=30, fg_color="#718096").pack(pady=(0,12))

    def _qsy_da_spot(self):
        """Porta la radio (via OmniRig) sulla frequenza/modo della spot selezionata."""
        sel = self.tree.selection()
        if not sel:
            return
        v = self.tree.item(sel[0], "values")
        # values = (utc, dx, freq_khz, banda, modo, spotter, commento)
        try:
            freq_khz = float(v[2])
            hz = int(round(freq_khz * 1000))
        except (ValueError, IndexError):
            return
        modo = v[4] if len(v) > 4 else ""
        rig = getattr(self.app_ref, "_omnirig", None)
        if rig is None or not rig.disponibile():
            messagebox.showwarning(T("dxc_omnirig_no"),
                                   T("dxc_omnirig_assente"), parent=self)
            return
        try:
            ok = rig.qsy(hz, modo, dig_come_usbd=self._dig_come_usbd.get(),
                         usa_bandplan=self._usa_bandplan.get())
            if ok:
                self.lbl_stato.configure(
                    text=T("dxc_qsy_fatto", call=v[1], freq=v[2]),
                    text_color="#48BB78")
            else:
                messagebox.showwarning(T("dxc_omnirig_no"),
                                       T("dxc_qsy_errore"), parent=self)
        except Exception as ex:
            messagebox.showerror(T("dxc_errore"), str(ex), parent=self)

    def _aggiungi_qso_da_spot(self):
        sel = self.tree.selection()
        if not sel:
            return
        v = self.tree.item(sel[0], "values")
        # Se attivo, porta anche la radio sulla frequenza dello spot
        if self._qsy_al_doppioclick.get():
            try:
                self._qsy_da_spot()
            except Exception:
                pass
        try:
            # Se la finestra Aggiungi QSO è già aperta, la riuso e aggiorno
            # i campi invece di aprirne una nuova ad ogni click.
            dlg = getattr(self.app_ref, '_aggiungi_qso_dlg', None)
            if dlg is not None and dlg.winfo_exists():
                self._precompila(v)
                try:
                    dlg.lift()
                    dlg.focus_force()
                except Exception:
                    pass
            else:
                self.app_ref.apri_aggiungi_qso()
                self.after(300, lambda: self._precompila(v))
        except Exception as ex:
            messagebox.showerror(T("dxc_errore"), str(ex), parent=self)

    def _precompila(self, v):
        """Precompila la finestra Aggiungi QSO con i dati dello spot.
        v = (utc, dx, freq_khz, banda, modo, spotter, commento)"""
        try:
            dlg = getattr(self.app_ref, '_aggiungi_qso_dlg', None)
            if dlg is None or not dlg.winfo_exists():
                return
            # Callsign
            if hasattr(dlg, '_aq_call') and v[1]:
                dlg._aq_call.delete(0, 'end')
                dlg._aq_call.insert(0, v[1])
            # Frequenza: kHz → MHz
            if hasattr(dlg, '_aq_freq') and v[2]:
                try:
                    mhz = f"{float(v[2])/1000:.6f}".rstrip('0').rstrip('.')
                    dlg._aq_freq.delete(0, 'end')
                    dlg._aq_freq.insert(0, mhz)
                except Exception:
                    pass
            # Banda (StringVar dell'OptionMenu) — normalizza a minuscolo (es. 20M→20m)
            if hasattr(dlg, '_aq_var_banda') and v[3]:
                banda = v[3].lower()
                try:
                    dlg._aq_var_banda.set(banda)
                except Exception:
                    pass
            # Modo (StringVar dell'OptionMenu)
            if hasattr(dlg, '_aq_var_modo') and v[4]:
                try:
                    dlg._aq_var_modo.set(v[4].upper())
                except Exception:
                    pass
        except Exception:
            pass


