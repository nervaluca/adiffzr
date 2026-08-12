import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import datetime as _dt
import customtkinter as ctk
import theme as TH
from tkinter import messagebox
import tkinter.ttk as _ttk
from config import T

class DuplicatiDialog(ctk.CTkToplevel):
    def __init__(self, parent, app_ref):
        super().__init__(parent)
        self.title(T("dup_titolo"))
        self.geometry("920x640")
        self.resizable(True, True)
        self.grab_set()
        self.app_ref = app_ref   # istanza ADIFtoPDFApp: legge/scrive app_ref.qsos_caricati
        self.gruppi_dup = []
        self._iid_to_qso = {}
        self._sel = {}
        self._undo_stack = []   # lista di snapshot qsos_caricati per undo

        ctk.CTkLabel(self, text=T("dup_titolo"),
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=10)

        # Opzioni criteri
        frame_crit = ctk.CTkFrame(self)
        frame_crit.pack(fill="x", padx=15, pady=5)
        ctk.CTkLabel(frame_crit, text=T("dup_criteri"),
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        frame_checks = ctk.CTkFrame(frame_crit, fg_color="transparent")
        frame_checks.pack(fill="x", padx=10, pady=(0,8))

        self.var_call  = ctk.BooleanVar(value=True)
        self.var_data  = ctk.BooleanVar(value=True)
        self.var_banda = ctk.BooleanVar(value=True)
        self.var_modo  = ctk.BooleanVar(value=True)
        self.var_tolleranza = ctk.BooleanVar(value=True)
        self.entry_minuti = None

        ctk.CTkCheckBox(frame_checks, text=T("dup_callsign"), variable=self.var_call).pack(side="left", padx=10)
        ctk.CTkCheckBox(frame_checks, text=T("dup_data"),  variable=self.var_data).pack(side="left", padx=10)
        ctk.CTkCheckBox(frame_checks, text=T("dup_banda"), variable=self.var_banda).pack(side="left", padx=10)
        ctk.CTkCheckBox(frame_checks, text=T("dup_modo"),  variable=self.var_modo).pack(side="left", padx=10)

        frame_tol = ctk.CTkFrame(frame_crit, fg_color="transparent")
        frame_tol.pack(fill="x", padx=10, pady=(0,6))
        ctk.CTkCheckBox(frame_tol, text=T("dup_toll_utc"),
                        variable=self.var_tolleranza).pack(side="left")
        self.entry_minuti = ctk.CTkEntry(frame_tol, width=50)
        self.entry_minuti.insert(0, "1")
        self.entry_minuti.pack(side="left", padx=6)
        ctk.CTkLabel(frame_tol, text=T("dup_toll_min"),
                     font=ctk.CTkFont(size=10), text_color="gray").pack(side="left")

        ctk.CTkButton(frame_checks, text=T("dup_cerca"), command=self.cerca,
                      fg_color=TH.PRIMARY, width=100).pack(side="right", padx=10)

        # Risultati
        self.lbl_risultato = ctk.CTkLabel(self, text=T("dup_premi_cerca"),
                                           text_color="gray")
        self.lbl_risultato.pack(pady=4)

        # Tabella risultati con tkinter Treeview
        import tkinter as tk
        import tkinter.ttk as ttk

        frame_tree = ctk.CTkFrame(self)
        frame_tree.pack(fill="both", expand=True, padx=15, pady=5)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Dup.Treeview",
                        background="#F7FAFC",
                        foreground="#1A202C",
                        rowheight=22,
                        fieldbackground="#F7FAFC",
                        font=("Arial", 9))
        style.configure("Dup.Treeview.Heading",
                        background="#1A365D",
                        foreground="white",
                        font=("Arial", 9, "bold"))
        style.map("Dup.Treeview", background=[("selected", "#2B6CB0")])

        cols = ("Sel", T("dup_col_gruppo"), T("dup_col_data"), "UTC", "Callsign", T("dup_banda"), T("dup_modo"), "RST TX", "RST RX", "Country", T("dup_col_elimina"))
        self.tree = ttk.Treeview(frame_tree, columns=cols, show="headings",
                                  style="Dup.Treeview", height=14, selectmode="extended")

        larghezze = {"Sel":34, T("dup_col_gruppo"):50, T("dup_col_data"):75, "UTC":55, "Callsign":85,
                     T("dup_banda"):55, T("dup_modo"):55, "RST TX":55, "RST RX":55, "Country":140,
                     T("dup_col_elimina"):40}
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=larghezze.get(col,80), anchor="center")

        self.tree.tag_configure("dup_a", background="#FED7D7")
        self.tree.tag_configure("dup_b", background="#FEEBC8")
        self.tree.tag_configure("dup_c", background="#C6F6D5")

        sb = ttk.Scrollbar(frame_tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Click sulla colonna 🗑 → elimina subito quel QSO
        self.tree.bind("<Button-1>", self._on_click_tree)

        # Pulsanti azione
        frame_btns1 = ctk.CTkFrame(self, fg_color="transparent")
        frame_btns1.pack(fill="x", pady=(6,2), padx=15)
        ctk.CTkButton(frame_btns1, text=T("dup_sel_tranne"),
                      command=self._seleziona_default,
                      fg_color="#4A5568", height=32).pack(side="left", padx=(0,6))
        ctk.CTkButton(frame_btns1, text=T("dup_elimina_sel"),
                      command=self.elimina_selezionati,
                      fg_color=TH.WARNING_H, hover_color=TH.WARNING_H, height=32).pack(side="left", padx=(0,6))
        self.btn_undo = ctk.CTkButton(frame_btns1, text=T("dup_annulla"),
                      command=self._undo,
                      fg_color="#718096", width=110, height=32, state="disabled")
        self.btn_undo.pack(side="left")
        ctk.CTkButton(frame_btns1, text=T("chiudi"), command=self.destroy,
                      fg_color=TH.PRIMARY, width=100, height=32).pack(side="right")

    def _on_click_tree(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col_id = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if not row_id or not col_id:
            return
        col_num = int(col_id.replace('#','')) - 1
        cols = self.tree["columns"]
        if col_num == 0:
            # Colonna "Sel" → toggle checkbox
            self._sel[row_id] = not self._sel.get(row_id, False)
            v = list(self.tree.item(row_id, "values"))
            v[0] = "☑" if self._sel[row_id] else "☐"
            self.tree.item(row_id, values=v)
            return "break"
        if col_num == len(cols) - 1:
            # Colonna 🗑 → elimina subito quel QSO
            self._elimina_riga(row_id)
            return "break"

    def _salva_snapshot(self):
        """Salva una copia del log corrente per poter fare undo."""
        self._undo_stack.append(list(self.app_ref.qsos_caricati))
        if hasattr(self, 'btn_undo'):
            self.btn_undo.configure(state="normal")

    def _undo(self):
        """Ripristina l'ultimo snapshot del log."""
        if not self._undo_stack:
            return
        self.app_ref.qsos_caricati = self._undo_stack.pop()
        self.app_ref._aggiorna_tree()
        if not self._undo_stack:
            self.btn_undo.configure(state="disabled")
        self.cerca()

    def _elimina_riga(self, iid):
        """Elimina il QSO di questa riga — se ci sono righe selezionate
        nel treeview, le elimina tutte (selezione multipla con Ctrl/Shift)."""
        selezionate = self.tree.selection()
        if len(selezionate) > 1 and iid in selezionate:
            # Multi-selezione via Ctrl/Shift click sul treeview
            da_elim = [self._iid_to_qso[i] for i in selezionate if i in self._iid_to_qso]
        else:
            da_elim = [self._iid_to_qso[iid]] if iid in self._iid_to_qso else []

        if not da_elim:
            return

        self._salva_snapshot()
        self.app_ref.qsos_caricati = [
            q for q in self.app_ref.qsos_caricati
            if not any(q is d for d in da_elim)]
        self.app_ref._aggiorna_tree()
        self.cerca()

    def _seleziona_default(self):
        """Seleziona automaticamente tutti i QSO tranne il primo di ogni gruppo."""
        for item in self.tree.get_children():
            v = list(self.tree.item(item, "values"))
            # v[1] è la colonna gruppo "#N"; il primo elemento di ogni gruppo ha iid "gN_0"
            is_primo = item.endswith("_0")
            self._sel[item] = not is_primo
            v[0] = "☐" if is_primo else "☑"
            self.tree.item(item, values=v)

    def elimina_selezionati(self):
        """Elimina solo i QSO marcati con la checkbox ☑."""
        da_eliminare = [self._iid_to_qso[iid] for iid, sel in self._sel.items()
                         if sel and iid in self._iid_to_qso]
        if not da_eliminare:
            messagebox.showinfo(T("dup_titolo"),
                "Nessun QSO selezionato per l'eliminazione.\n"
                "Usa ☑ per selezionare le righe o '☑ Seleziona tutti tranne il primo'.")
            return

        if not messagebox.askyesno(T("dup_titolo"), T("dup_conferma_bulk", n=len(da_eliminare))):
            return

        self._salva_snapshot()
        self.app_ref.qsos_caricati = [
            q for q in self.app_ref.qsos_caricati
            if not any(q is d for d in da_eliminare)
        ]
        self.app_ref._aggiorna_tree()
        messagebox.showinfo(T("dup_titolo"), T("dup_eliminati_n", n=len(da_eliminare)))
        self.cerca()

    def cerca(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._iid_to_qso.clear()
        self._sel.clear()

        qsos = self.app_ref.qsos_caricati

        def _minuti_assoluti(qso):
            """Converte data+ora UTC in minuti assoluti per il confronto di tolleranza."""
            d = str(qso.get('qso_date','')).strip()
            t = str(qso.get('time_on','')).strip().zfill(4)
            if len(d) != 8:
                return None
            try:
                hh = int(t[0:2]) if len(t) >= 2 else 0
                mm = int(t[2:4]) if len(t) >= 4 else 0
                import datetime as _dt
                dt = _dt.datetime.strptime(d, "%Y%m%d") + _dt.timedelta(hours=hh, minutes=mm)
                return int(dt.timestamp() // 60)
            except Exception:
                return None

        usa_tolleranza = self.var_tolleranza.get()
        try:
            tol_min = int(self.entry_minuti.get().strip())
        except (ValueError, AttributeError):
            tol_min = 1

        chiave_fissa_fn = lambda q: tuple([
            str(q.get('call','')).upper().strip()  if self.var_call.get()  else "",
            str(q.get('band','')).upper().strip()   if self.var_banda.get() else "",
            str(q.get('mode','')).upper().strip()   if self.var_modo.get()  else "",
        ])

        if usa_tolleranza:
            # Raggruppa per chiave fissa (call+banda+modo), poi clusterizza per tempo
            per_chiave = {}
            for qso in qsos:
                k = chiave_fissa_fn(qso)
                per_chiave.setdefault(k, []).append(qso)

            self.gruppi_dup = []
            for k, lista in per_chiave.items():
                # Ordina per tempo assoluto; QSO senza data/ora valida vanno in gruppi a parte
                con_tempo = [(q, _minuti_assoluti(q)) for q in lista]
                con_tempo_validi = sorted([x for x in con_tempo if x[1] is not None], key=lambda x: x[1])
                senza_tempo = [x[0] for x in con_tempo if x[1] is None]

                cluster = []
                for qso, mins in con_tempo_validi:
                    if cluster and (mins - cluster[-1][1]) <= tol_min:
                        cluster.append((qso, mins))
                    else:
                        if len(cluster) > 1:
                            self.gruppi_dup.append((k, [c[0] for c in cluster]))
                        cluster = [(qso, mins)]
                if len(cluster) > 1:
                    self.gruppi_dup.append((k, [c[0] for c in cluster]))

                # Se richiesta anche la data esatta come criterio, filtra cluster cross-day già gestiti da minuti assoluti
                if not self.var_data.get():
                    pass  # già ignorato: la data non influenza la chiave fissa
        else:
            chiave_fn = lambda q: chiave_fissa_fn(q) + (
                (str(q.get('qso_date','')).strip(),) if self.var_data.get() else (),)
            raggruppati = {}
            for qso in qsos:
                k = chiave_fn(qso)
                raggruppati.setdefault(k, []).append(qso)
            self.gruppi_dup = [(k, v) for k, v in raggruppati.items() if len(v) > 1]

        colori_tag = ["dup_a", "dup_b", "dup_c"]
        n_dup = 0
        for g_idx, (k, lista) in enumerate(self.gruppi_dup):
            tag = colori_tag[g_idx % 3]
            for j, qso in enumerate(lista):
                data = str(qso.get('qso_date',''))
                if len(data)==8:
                    data = f"{data[6:8]}/{data[4:6]}/{data[0:4]}"
                utc = str(qso.get('time_on',''))
                if len(utc)>=4:
                    utc = f"{utc[0:2]}:{utc[2:4]}"
                iid = f"g{g_idx}_{j}"
                self.tree.insert("", "end", iid=iid, values=(
                    "☐",
                    f"#{g_idx+1}",
                    data,
                    utc,
                    str(qso.get('call','')).upper(),
                    str(qso.get('band','')).upper(),
                    str(qso.get('mode','')).upper(),
                    str(qso.get('rst_sent','')),
                    str(qso.get('rst_rcvd','')),
                    str(qso.get('country','')).upper(),
                    "🗑",
                ), tags=(tag,))
                self._iid_to_qso[iid] = qso
                self._sel[iid] = False
                n_dup += 1

        totale_gruppi = len(self.gruppi_dup)
        if totale_gruppi == 0:
            self.lbl_risultato.configure(
                text=T("dup_nessuno"), text_color=TH.OK_TEXT)
        else:
            self.lbl_risultato.configure(
                text=T("dup_trovati", g=totale_gruppi, n=n_dup),
                text_color=TH.DANGER)
            self._seleziona_default()

    def destroy(self):
        # Il ripristino tema ttk è opzionale: se la funzione non è
        # disponibile non deve impedire la chiusura della finestra.
        try:
            _ripristina_tema_ttk()
        except Exception:
            pass
        super().destroy()


# ─────────────────────────────────────────────
#  QSL Card Designer — editor visuale 140×90mm
# ─────────────────────────────────────────────
