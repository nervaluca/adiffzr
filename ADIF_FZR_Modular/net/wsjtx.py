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
import struct
import tkinter.ttk as _ttk
from tkinter import messagebox
import customtkinter as ctk
from config import T

class WSJTXListener(ctk.CTkToplevel):
    """Listener UDP per WSJT-X: riceve i QSO loggati in tempo reale.
    Attivazione manuale (opt-in). WSJT-X invia pacchetti binari sulla
    porta configurata in Impostazioni → Reporting → UDP Server (def. 2237)."""

    MAGIC = 0xADBCCBDA

    def __init__(self, parent, app_ref):
        super().__init__(parent)
        self.title(T("wsx_titolo"))
        self.geometry("720x480")
        self.minsize(560, 360)
        self.app_ref = app_ref
        self._sock = None
        self._thread = None
        self._running = False
        self._queue = []
        self._auto_add = ctk.BooleanVar(value=False)
        self.transient(parent)
        self.lift(); self.focus_force()
        self.after(200, lambda: (self.lift(), self.focus_force()))

        # Barra superiore
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10,4))
        ctk.CTkLabel(top, text=T("wsx_indirizzo"), font=ctk.CTkFont(size=11)).pack(side="left")
        self.entry_addr = ctk.CTkEntry(top, width=120, height=28,
                                        placeholder_text="127.0.0.1")
        self.entry_addr.pack(side="left", padx=(4,8))
        ctk.CTkLabel(top, text=T("wsx_porta"), font=ctk.CTkFont(size=11)).pack(side="left")
        self.entry_porta = ctk.CTkEntry(top, width=70, height=28)
        self.entry_porta.insert(0, "2237")
        self.entry_porta.pack(side="left", padx=6)

        self.btn_start = ctk.CTkButton(top, text=T("wsx_avvia"), width=130, height=28,
                                        command=self._toggle,
                                        fg_color="#276749", hover_color="#2F855A",
                                        font=ctk.CTkFont(size=11))
        self.btn_start.pack(side="left", padx=4)

        self.lbl_stato = ctk.CTkLabel(top, text=T("wsx_fermo"),
                                       font=ctk.CTkFont(size=11), text_color="gray")
        self.lbl_stato.pack(side="left", padx=8)

        ctk.CTkCheckBox(top, text=T("wsx_auto_add"),
                        variable=self._auto_add,
                        font=ctk.CTkFont(size=11)).pack(side="right")

        # Treeview QSO ricevuti
        import tkinter.ttk as _ttk
        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=10, pady=4)
        style = _ttk.Style()
        style.configure("WSJTX.Treeview", background="#101825", foreground="#E2E8F0",
                        rowheight=24, fieldbackground="#101825", font=("Consolas", 10))
        style.configure("WSJTX.Treeview.Heading", background="#1A365D",
                        foreground="white", font=("Arial", 10, "bold"))

        cols = ("data","ora","call","banda","modo","rst_s","rst_r","grid")
        self.tree = _ttk.Treeview(frame, columns=cols, show="headings", style="WSJTX.Treeview")
        hdr = {"data":T("wsx_col_data"),"ora":T("dxc_col_utc"),"call":T("wsx_col_call"),"banda":T("dxc_col_banda"),"modo":T("dxc_col_modo"),
               "rst_s":T("wsx_col_inv"),"rst_r":T("wsx_col_ric"),"grid":T("wsx_col_grid")}
        wid = {"data":80,"ora":60,"call":100,"banda":60,"modo":60,"rst_s":50,"rst_r":50,"grid":70}
        for c in cols:
            self.tree.heading(c, text=hdr[c])
            self.tree.column(c, width=wid[c], anchor="center")
        vsb = _ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Barra inferiore
        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.pack(fill="x", padx=10, pady=(2,10))
        ctk.CTkButton(bot, text=T("wsx_aggiungi_sel"), height=28,
                      command=self._aggiungi_selezionato,
                      fg_color="#2B6CB0", font=ctk.CTkFont(size=11)).pack(side="left")
        self.lbl_info = ctk.CTkLabel(bot,
            text=T("wsx_info"),
            font=ctk.CTkFont(size=10), text_color="gray")
        self.lbl_info.pack(side="right", padx=6)

        self._qso_ricevuti = {}  # iid → dict QSO
        self.protocol("WM_DELETE_WINDOW", self._chiudi)
        self.after(400, self._processa_coda)

    def _toggle(self):
        if self._running:
            self._stop()
        else:
            self._start()

    def _start(self):
        import socket, threading, struct
        try:
            porta = int(self.entry_porta.get().strip())
        except ValueError:
            messagebox.showwarning(T("wsx_porta_invalida"), T("wsx_porta_num"), parent=self)
            return
        addr = self.entry_addr.get().strip()
        # Rileva se è un indirizzo multicast (224.0.0.0 – 239.255.255.255)
        is_multicast = False
        if addr:
            try:
                primo = int(addr.split('.')[0])
                is_multicast = 224 <= primo <= 239
            except (ValueError, IndexError):
                is_multicast = False
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # SO_REUSEPORT permette a più programmi di condividere la porta (dove supportato)
            if hasattr(socket, 'SO_REUSEPORT'):
                try:
                    self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            if is_multicast:
                # Multicast: si unisce al gruppo, così più programmi ricevono insieme
                self._sock.bind(("", porta))
                mreq = struct.pack("4sl", socket.inet_aton(addr), socket.INADDR_ANY)
                self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            else:
                # Unicast: ascolta su tutte le interfacce
                self._sock.bind(("0.0.0.0", porta))
            self._sock.settimeout(1.0)
        except Exception as ex:
            messagebox.showerror(T("wsx_errore"), T("wsx_porta_apri_err", porta=porta, ex=ex), parent=self)
            return
        self._running = True
        _stato = T("wsx_ascolto_mc", addr=addr, porta=porta) if is_multicast else T("wsx_ascolto", porta=porta)
        self.lbl_stato.configure(text=_stato, text_color="#48BB78")
        self.btn_start.configure(text=T("wsx_ferma"), fg_color="#9C4221", hover_color="#7B3618")

        def _run():
            while self._running:
                try:
                    data, _addr = self._sock.recvfrom(8192)
                    self._decodifica(data)
                except TimeoutError:
                    continue
                except OSError:
                    break

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def _stop(self):
        self._running = False
        try:
            if self._sock: self._sock.close()
        except Exception:
            pass
        self._sock = None
        try:
            if self.winfo_exists():
                self.lbl_stato.configure(text=T("wsx_fermo"), text_color="gray")
                self.btn_start.configure(text=T("wsx_avvia"),
                                          fg_color="#276749", hover_color="#2F855A")
        except Exception:
            pass

    def _chiudi(self):
        self._stop()
        self.destroy()

    def _decodifica(self, data):
        """Decodifica un pacchetto UDP WSJT-X. Interessa solo il tipo 5 (QSO Logged)."""
        import struct
        try:
            pos = 0
            def u32():
                nonlocal pos
                v = struct.unpack_from('>I', data, pos)[0]; pos += 4; return v
            def u64():
                nonlocal pos
                v = struct.unpack_from('>Q', data, pos)[0]; pos += 8; return v
            def u8():
                nonlocal pos
                v = struct.unpack_from('>B', data, pos)[0]; pos += 1; return v
            def qstr():
                nonlocal pos
                ln = u32()
                if ln == 0xFFFFFFFF:
                    return ""
                v = data[pos:pos+ln].decode('utf-8', errors='replace'); pos += ln
                return v
            def qdt():
                nonlocal pos
                jd = u64(); ms = u32(); u8()  # spec
                l = jd + 68569; n = (4*l)//146097
                l = l - (146097*n + 3)//4; i = (4000*(l+1))//1461001
                l = l - (1461*i)//4 + 31; j = (80*l)//2447
                day = l - (2447*j)//80; l2 = j//11
                month = j + 2 - 12*l2; year = 100*(n-49) + i + l2
                h = ms//3600000; mi = (ms%3600000)//60000; s = (ms%60000)//1000
                return f"{year:04d}{month:02d}{day:02d}", f"{h:02d}{mi:02d}{s:02d}"

            magic = u32()
            if magic != self.MAGIC:
                return
            u32()          # schema
            mtype = u32()
            if mtype != 5:  # solo QSO Logged
                return
            qstr()                    # id WSJT-X
            d_off, t_off = qdt()      # DateTimeOff
            dxcall = qstr()
            dxgrid = qstr()
            freq = u64()
            mode = qstr()
            rst_s = qstr()
            rst_r = qstr()
            pwr = qstr()
            comm = qstr()
            name = qstr()
            d_on, t_on = qdt()        # DateTimeOn

            banda = self._freq_banda(freq/1e6)
            qso = {
                'call': dxcall.upper(), 'gridsquare': dxgrid.upper(),
                'freq': f"{freq/1e6:.6f}".rstrip('0').rstrip('.'),
                'band': banda, 'mode': mode.upper(),
                'rst_sent': rst_s, 'rst_rcvd': rst_r,
                'qso_date': d_on, 'time_on': t_on,
                'qso_date_off': d_off, 'time_off': t_off,
                'name': name, 'tx_pwr': pwr, 'comment': comm,
            }
            self._queue.append(qso)
        except Exception:
            pass

    @staticmethod
    def _freq_banda(mhz):
        tab = [(1.8,2.0,"160m"),(3.5,4.0,"80m"),(5.25,5.45,"60m"),(7.0,7.3,"40m"),
               (10.1,10.15,"30m"),(14.0,14.35,"20m"),(18.0,18.17,"17m"),
               (21.0,21.45,"15m"),(24.89,24.99,"12m"),(28.0,29.7,"10m"),
               (50.0,54.0,"6m"),(144.0,148.0,"2m"),(430.0,440.0,"70cm")]
        for lo, hi, b in tab:
            if lo <= mhz <= hi:
                return b
        return "?"

    def _processa_coda(self):
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        while self._queue:
            qso = self._queue.pop(0)
            self._mostra(qso)
        self.after(400, self._processa_coda)

    def _mostra(self, qso):
        iid = self.tree.insert("", 0, values=(
            qso['qso_date'], qso['time_on'][:4], qso['call'], qso['band'],
            qso['mode'], qso['rst_sent'], qso['rst_rcvd'], qso['gridsquare']))
        self._qso_ricevuti[iid] = qso
        if self._auto_add.get():
            self._add_al_log(qso)

    def _aggiungi_selezionato(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(T("wsx_no_sel"),
                T("wsx_sel_qso"), parent=self)
            return
        n = 0
        for iid in sel:
            qso = self._qso_ricevuti.get(iid)
            if qso:
                self._add_al_log(qso); n += 1
        messagebox.showinfo(T("wsx_aggiunti"), T("wsx_n_aggiunti", n=n), parent=self)

    def _add_al_log(self, qso):
        q = {k: v for k, v in qso.items() if k not in ('qso_date_off','time_off')}
        self.app_ref.qsos_caricati.append(q)
        self.app_ref._log_modificato = True
        self.app_ref.qsos_caricati.sort(key=lambda x: (
            str(x.get('qso_date','')).strip(),
            str(x.get('time_on','')).strip().zfill(6)))
        self.app_ref.qsos_filtrati = list(self.app_ref.qsos_caricati)
        self.app_ref._aggiorna_tree()


