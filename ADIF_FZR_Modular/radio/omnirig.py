import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import sys
import os
import time
from radio.bandplan import modo_da_bandplan

class OmniRigControl:
    """Controllo radio via OmniRig (componente COM di Windows, VE3NEA).

    OmniRig gestisce fino a 2 radio (RIG1, RIG2). Questa classe è un wrapper
    sottile e difensivo: se OmniRig o pywin32 non sono disponibili, tutti i
    metodi falliscono in modo silenzioso e l'app continua a funzionare.

    Uso tipico:
        rig = OmniRigControl()
        if rig.disponibile():
            rig.connetti()
            rig.set_freq(14025000)      # Hz
            rig.set_modo("CW")
            f = rig.get_freq()          # Hz o None
            m = rig.get_modo()          # "CW"/"SSB"/... o None
    """

    # Costanti dei modi OmniRig (valori del bitmask PM_*)
    PM = {
        "CW_U": 0x02000000, "CW_L": 0x01000000,
        "SSB_U": 0x02000000 >> 0, "USB": 0x00040000, "LSB": 0x00080000,
        "DIG_U": 0x00010000, "DIG_L": 0x00020000,
        "AM": 0x00100000, "FM": 0x00200000,
    }

    def __init__(self, rig_num=1):
        self.rig_num = rig_num          # 1 = RIG1, 2 = RIG2
        self._omni = None               # oggetto COM OmniRig
        self._rig = None                # oggetto radio (RIG1/RIG2)
        self._ok = False
        # Percorsi personalizzati (se impostati dall'utente hanno priorità
        # sulla ricerca automatica). Vuoti = ricerca automatica.
        self.exe_path = ""              # percorso di OmniRig.exe
        self.rigs_path = ""             # cartella Rigs con i file .ini
        self._avviato_da_noi = False    # True se siamo stati noi ad avviarlo
        self.avvio_auto = True          # se False, l'app non lancia mai OmniRig

    def disponibile(self):
        """True se OmniRig è installato e istanziabile su questo sistema."""
        import sys
        if not sys.platform.startswith("win"):
            return False
        try:
            import win32com.client  # noqa: F401
            return True
        except Exception:
            return False

    def connetti(self, avvia_se_serve=True):
        """Istanzia OmniRig e seleziona la radio. Ritorna True se riuscito.

        avvia_se_serve: se il Dispatch COM fallisce (OmniRig non in esecuzione
        e non auto-avviante), tenta di lanciare OmniRig.exe e riprova.
        """
        import sys
        if not sys.platform.startswith("win"):
            return False

        def _dispatch():
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            self._omni = win32com.client.Dispatch("OmniRig.OmniRigX")
            self._rig = self._omni.Rig1 if self.rig_num == 1 else self._omni.Rig2
            self._ok = True
            return True

        # Se l'avvio automatico è disattivato e OmniRig NON è già in
        # esecuzione, non tentare il Dispatch (che lo avvierebbe via COM).
        # Così, con flag OFF, l'app non fa mai partire OmniRig da sola;
        # se invece è già aperto, lo usa normalmente.
        if not self.avvio_auto and not self._omnirig_in_esecuzione():
            self._ok = False
            self._omni = None
            self._rig = None
            return False

        # Primo tentativo: il Dispatch di solito avvia il server COM da solo
        try:
            return _dispatch()
        except Exception:
            self._ok = False
            self._omni = None
            self._rig = None

        # Secondo tentativo: avvia OmniRig.exe e riprova — solo se l'avvio
        # automatico è consentito.
        if self.avvio_auto and avvia_se_serve and self._avvia_omnirig_exe():
            import time
            time.sleep(2.0)   # dà tempo a OmniRig di registrarsi
            try:
                return _dispatch()
            except Exception:
                self._ok = False
                self._omni = None
                self._rig = None
        return False

    def _trova_omnirig_exe(self):
        """Cerca il percorso di OmniRig.exe. Ritorna il path o None.
        Se l'utente ha impostato exe_path, quello ha priorità."""
        import os
        if self.exe_path and os.path.isfile(self.exe_path):
            return self.exe_path
        candidati = [
            r"C:\Program Files\OmniRig\OmniRig.exe",
            r"C:\Program Files (x86)\OmniRig\OmniRig.exe",
            r"C:\Program Files\Afreet\OmniRig\OmniRig.exe",
            r"C:\Program Files (x86)\Afreet\OmniRig\OmniRig.exe",
            r"C:\OmniRig\OmniRig.exe",
        ]
        # Prova anche dal registro (LocalServer32 del CLSID OmniRig)
        try:
            import winreg
            # ProgID OmniRig.OmniRigX → CLSID → LocalServer32
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                r"OmniRig.OmniRigX\CLSID") as k:
                clsid = winreg.QueryValue(k, "")
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                rf"CLSID\{clsid}\LocalServer32") as k:
                path = winreg.QueryValue(k, "")
                path = path.strip().strip('"')
                if path and os.path.isfile(path):
                    candidati.insert(0, path)
        except Exception:
            pass
        for p in candidati:
            if os.path.isfile(p):
                return p
        return None

    def _omnirig_in_esecuzione(self):
        """True se un processo OmniRig.exe è già attivo (Windows)."""
        import sys
        if not sys.platform.startswith("win"):
            return False
        try:
            import subprocess
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq OmniRig.exe"],
                capture_output=True, text=True, timeout=5,
                creationflags=0x08000000)  # CREATE_NO_WINDOW
            return "OmniRig.exe" in out.stdout
        except Exception:
            return False

    def _avvia_omnirig_exe(self):
        """Avvia OmniRig.exe se non è già in esecuzione. Ritorna True se
        l'ha avviato o era già attivo. Ricorda se siamo stati noi ad avviarlo,
        così alla chiusura possiamo terminarlo (solo se l'abbiamo avviato noi)."""
        import sys
        if not sys.platform.startswith("win"):
            return False
        if self._omnirig_in_esecuzione():
            return True   # era già attivo: NON lo marchiamo come nostro
        exe = self._trova_omnirig_exe()
        if not exe:
            return False
        try:
            import subprocess, os
            subprocess.Popen([exe], cwd=os.path.dirname(exe),
                             creationflags=0x08000000)  # senza finestra console
            self._avviato_da_noi = True
            return True
        except Exception:
            return False

    def chiudi_omnirig(self, forza=False):
        """Termina OmniRig.exe. Per default lo fa SOLO se siamo stati noi ad
        avviarlo (per non interferire con altri programmi che lo usano).
        Con forza=True lo chiude comunque."""
        import sys
        if not sys.platform.startswith("win"):
            return False
        if not forza and not self._avviato_da_noi:
            return False
        # Rilascia prima l'oggetto COM
        try:
            self._rig = None
            self._omni = None
            self._ok = False
        except Exception:
            pass
        try:
            import subprocess
            subprocess.run(["taskkill", "/IM", "OmniRig.exe", "/F"],
                           capture_output=True, timeout=5,
                           creationflags=0x08000000)
            self._avviato_da_noi = False
            return True
        except Exception:
            return False

    def _assicura(self):
        if not self._ok or self._rig is None:
            return self.connetti()
        return True

    # ─────────────────────────────────────────────────────────────────
    #  Parser dei file di definizione OmniRig (.ini)  — INFRASTRUTTURA
    #  Legge quali modi supporta una radio dal suo file .ini. Per ora è
    #  uno strumento diagnostico: la mappa modi operativa resta quella
    #  calibrata (get_modo/set_modo). Va completato verificando la
    #  corrispondenza tra i valori letti via COM e le costanti pm*.
    # ─────────────────────────────────────────────────────────────────

    # Costanti PM_* ufficiali di OmniRig (dal codice sorgente, fisse per tutte
    # le radio). Verificate incrociando i Flag dei file .ini con i valori letti
    # via COM dall'IC-7600. Valgono per Icom, Yaesu, Kenwood, ecc.
    PM_MODI = {
        "pmCW_U":  0x00800000,
        "pmCW_L":  0x01000000,
        "pmSSB_U": 0x02000000,   # USB
        "pmSSB_L": 0x04000000,   # LSB
        "pmDIG_U": 0x08000000,   # USB-D (USB data)
        "pmDIG_L": 0x10000000,   # RTTY / LSB data
        "pmAM":    0x20000000,
        "pmFM":    0x40000000,
    }
    # Nome pm* → stringa modo ADIF
    PM_TO_MODO = {
        "pmCW_U": "CW", "pmCW_L": "CW",
        "pmSSB_U": "USB", "pmSSB_L": "LSB",
        "pmDIG_U": "USB-D", "pmDIG_L": "RTTY",
        "pmAM": "AM", "pmFM": "FM",
    }

    def _trova_cartella_rigs(self):
        """Trova la cartella Rigs/ di OmniRig (contiene i file .ini).
        Se l'utente ha impostato rigs_path, quello ha priorità."""
        import os
        if self.rigs_path and os.path.isdir(self.rigs_path):
            return self.rigs_path
        basi = [
            r"C:\Program Files\OmniRig\Rigs",
            r"C:\Program Files (x86)\OmniRig\Rigs",
            r"C:\OmniRig\Rigs",
            # OmniRig v2 usa spesso percorsi per-utente
            os.path.join(os.environ.get("APPDATA", ""), "OmniRig", "Rigs"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "OmniRig", "Rigs"),
            os.path.join(os.environ.get("PROGRAMDATA", ""), "OmniRig", "Rigs"),
            r"C:\Program Files\Afreet\OmniRig\Rigs",
            r"C:\Program Files (x86)\Afreet\OmniRig\Rigs",
        ]
        # Dedotta dal percorso dell'exe (se trovato)
        exe = self._trova_omnirig_exe()
        if exe:
            d = os.path.dirname(exe)
            basi.insert(0, os.path.join(d, "Rigs"))
            basi.insert(1, os.path.join(d, "rigs"))
        for b in basi:
            if b and os.path.isdir(b):
                return b
        # Ultimo tentativo: scansiona le cartelle OmniRig più comuni cercando
        # una sottocartella con dentro file .ini che contengono [pmCW_L]
        radici = [r"C:\Program Files", r"C:\Program Files (x86)",
                  os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")]
        for radice in radici:
            if not radice or not os.path.isdir(radice):
                continue
            for nome in os.listdir(radice):
                if "omnirig" in nome.lower():
                    cand = os.path.join(radice, nome, "Rigs")
                    if os.path.isdir(cand):
                        return cand
        return None

    def _radio_selezionata(self):
        """Nome del file .ini della radio selezionata in OmniRig (RIG1/RIG2).
        Legge OmniRig.ini dalla config. Ritorna es. 'IC-7600.ini' o None."""
        import os
        # OmniRig salva la config in questi percorsi tipici
        cfg_paths = [
            os.path.join(os.environ.get("APPDATA", ""), "OmniRig", "OmniRig.ini"),
            r"C:\Program Files\OmniRig\OmniRig.ini",
            r"C:\Program Files (x86)\OmniRig\OmniRig.ini",
            r"C:\Program Files\Afreet\OmniRig\OmniRig.ini",
            r"C:\Program Files (x86)\Afreet\OmniRig\OmniRig.ini",
            os.path.join(os.environ.get("APPDATA", ""), "Afreet", "OmniRig", "OmniRig.ini"),
        ]
        # Aggiungi anche il config accanto all'exe trovato
        try:
            exe = self._trova_omnirig_exe()
            if exe:
                cfg_paths.insert(0, os.path.join(os.path.dirname(exe), "OmniRig.ini"))
        except Exception:
            pass
        chiave = "Rig1" if self.rig_num == 1 else "Rig2"
        for cfg in cfg_paths:
            if not cfg or not os.path.isfile(cfg):
                continue
            try:
                with open(cfg, "r", encoding="utf-8", errors="ignore") as f:
                    for riga in f:
                        r = riga.strip()
                        # Cerca es. "Rig1=IC-7600.ini" o "RigType=..."
                        if r.lower().startswith(chiave.lower()) and "=" in r:
                            val = r.split("=", 1)[1].strip()
                            if val.lower().endswith(".ini"):
                                return val
            except Exception:
                continue
        return None

    def nome_radio(self):
        """Ritorna un nome leggibile della radio connessa (es. 'IC-7600'),
        o None. Prova prima RigType via COM (più affidabile), poi il nome del
        file .ini selezionato in OmniRig."""
        # 1) RigType/DeviceName via COM (se connesso)
        try:
            if self._assicura():
                for prop in ("RigType", "DeviceName"):
                    try:
                        v = getattr(self._rig, prop)
                        if v and str(v).strip():
                            nome = str(v).strip()
                            # pulisce suffissi tipo "-DATA" per compattezza
                            return nome
                    except Exception:
                        continue
        except Exception:
            pass
        # 2) Nome del file .ini selezionato (es. "IC-7600.ini" → "IC-7600")
        try:
            ini = self._radio_selezionata()
            if ini:
                import os
                return os.path.splitext(os.path.basename(ini))[0]
        except Exception:
            pass
        return None

    @staticmethod
    def _modi_supportati_da_ini(path_ini):
        """Legge un file .ini OmniRig e ritorna l'insieme dei modi supportati
        (nomi pm* → stringhe modo). Utile per sapere cosa la radio può fare."""
        import os
        if not path_ini or not os.path.isfile(path_ini):
            return {}
        pm_to_modo = {
            "pmCW_U": "CW", "pmCW_L": "CW",
            "pmSSB_U": "USB", "pmSSB_L": "LSB",
            "pmDIG_U": "USB-D", "pmDIG_L": "RTTY",
            "pmAM": "AM", "pmFM": "FM",
        }
        trovati = {}
        try:
            with open(path_ini, "r", encoding="utf-8", errors="ignore") as f:
                testo = f.read()
            for pm, modo in pm_to_modo.items():
                # Il modo è supportato se esiste la sezione [pm*] (comando SET)
                if f"[{pm}]" in testo:
                    trovati[pm] = modo
        except Exception:
            pass
        return trovati

    def diagnostica_ini(self):
        """Ritorna una stringa diagnostica: percorso exe, cartella Rigs, radio
        selezionata, modi supportati. Per capire la configurazione OmniRig."""
        import os
        righe = []
        exe = self._trova_omnirig_exe()
        righe.append(f"OmniRig.exe: {exe or 'NON TROVATO'}")
        righe.append(f"In esecuzione: {'sì' if self._omnirig_in_esecuzione() else 'no'}")
        cartella = self._trova_cartella_rigs()
        righe.append(f"Cartella Rigs: {cartella or 'NON TROVATA'}")
        # Prova a leggere il tipo di radio direttamente via COM (più affidabile
        # del file .ini): alcune versioni espongono RigType.
        try:
            if self._assicura():
                for prop in ("RigType", "DeviceName"):
                    try:
                        v = getattr(self._rig, prop)
                        if v:
                            righe.append(f"{prop} (COM): {v}")
                    except Exception:
                        pass
                try:
                    righe.append(f"Status (COM): {self._rig.StatusStr}")
                except Exception:
                    pass
        except Exception:
            pass
        radio = self._radio_selezionata()
        righe.append(f"Radio dal config: {radio or 'NON RILEVATA'}")
        if cartella and radio:
            path = os.path.join(cartella, radio)
            modi = self._modi_supportati_da_ini(path)
            if modi:
                righe.append("Modi supportati dal file:")
                for pm, modo in modi.items():
                    righe.append(f"  {pm} → {modo}")
        return "\n".join(righe)

    def get_freq(self):
        """Frequenza corrente in Hz, o None.

        Prova Freq (simplex), poi FreqA (VFO principale), poi FreqB.
        Su radio con VFO separati (es. IC-9700 in split/SAT) .Freq può
        tornare 0, quindi si ripiega su FreqA/FreqB.
        """
        if not self._assicura():
            return None
        for prop in ("Freq", "FreqA", "FreqB"):
            try:
                f = int(getattr(self._rig, prop))
                if f > 0:
                    return f
            except Exception:
                continue
        return None

    def get_freq_ab(self):
        """Ritorna (freq_a, freq_b) in Hz per i due VFO, o None dove non
        disponibile. Utile per split e satellite (uplink/downlink separati).

        FreqA = VFO principale (RX/downlink), FreqB = VFO secondario (TX/uplink).
        Se la radio è in simplex, .Freq riempie A e B resta None."""
        if not self._assicura():
            return (None, None)
        fa = fb = None
        try:
            v = int(self._rig.FreqA)
            fa = v if v > 0 else None
        except Exception:
            pass
        try:
            v = int(self._rig.FreqB)
            fb = v if v > 0 else None
        except Exception:
            pass
        # Se FreqA non c'è ma .Freq sì (radio in simplex), usa .Freq come A
        if fa is None:
            try:
                v = int(self._rig.Freq)
                fa = v if v > 0 else None
            except Exception:
                pass
        return (fa, fb)

    def get_modo_ab(self):
        """Ritorna (modo_a, modo_b) per i due VFO, o None dove non disponibile.
        Molte radio espongono solo il modo del VFO attivo; in tal caso modo_b
        sarà None e si mostra solo modo_a."""
        if not self._assicura():
            return (None, None)
        ma = self.get_modo()   # modo del VFO attivo
        mb = None
        # Alcuni file OmniRig espongono TxMode / ModeB; tentativo difensivo
        for prop in ("ModeB", "TxMode"):
            try:
                raw = int(getattr(self._rig, prop))
                if raw:
                    for pm in ["pmDIG_U","pmDIG_L","pmCW_U","pmCW_L",
                               "pmSSB_U","pmSSB_L","pmAM","pmFM"]:
                        if raw & self.PM_MODI[pm]:
                            mb = self.PM_TO_MODO[pm]
                            break
                    if mb:
                        break
            except Exception:
                continue
        return (ma, mb)

    def set_freq(self, hz):
        """Imposta la frequenza (Hz). Prova prima FreqA, poi Freq."""
        if not self._assicura():
            return False
        try:
            self._rig.SetSimplexMode(int(hz))
            return True
        except Exception:
            pass
        try:
            self._rig.Freq = int(hz)
            return True
        except Exception:
            return False

    # Costanti comando VFO/Split di OmniRig.
    # NOTA: i valori split reali di questa versione di OmniRig (letti dalla
    # diagnostica: .Split = 65536 = ON) sono più piccoli delle costanti VFO.
    PM_VFO_A     = 0x00800000000
    PM_VFO_B     = 0x01000000000
    PM_VFO_EQUAL = 0x02000000000
    PM_VFO_SWAP  = 0x04000000000
    PM_SPLIT_ON  = 0x8000           # 32768  — verificato sul rig (split attivo)
    PM_SPLIT_OFF = 0x10000          # 65536  — verificato sul rig (split spento)

    def diagnostica_split(self):
        """Esamina cosa espone OmniRig per lo split. Mostra .Split in decimale,
        hex e binario, così confrontando split ON vs OFF si capisce quale bit
        cambia. Ritorna un testo diagnostico."""
        righe = []
        if not self._assicura():
            return "OmniRig non connesso."
        # Valore .Split dettagliato (dec / hex / bit)
        try:
            v = int(self._rig.Split)
            righe.append(f".Split = {v}  (hex {v:#x})")
        except Exception as ex:
            righe.append(f".Split non leggibile ({type(ex).__name__})")
        # Frequenze VFO (per dedurre lo split dallo scostamento)
        for prop in ("Freq", "FreqA", "FreqB"):
            try:
                righe.append(f"  .{prop} = {getattr(self._rig, prop)}")
            except Exception:
                righe.append(f"  .{prop} → n/d")
        # Metodi disponibili
        righe.append("Metodi: " + ", ".join(
            m for m in ("SetSplit", "SetSplitMode", "SetSimplexMode")
            if hasattr(self._rig, m)))
        return "\n".join(righe)

    def leggi_valore_split(self):
        """Ritorna il valore grezzo di .Split (int) o None. Per il monitor."""
        if not self._assicura():
            return None
        try:
            return int(self._rig.Split)
        except Exception:
            return None

    def is_split(self):
        """Ritorna True se lo split è attivo, False se no, None se non
        determinabile. Legge la proprietà .Split, che su questo OmniRig vale
        32768 (0x8000) quando lo split è ON e 65536 (0x10000) quando è OFF.
        Verificato direttamente sulla radio."""
        if not self._assicura():
            return None
        try:
            v = int(self._rig.Split)
            if v == self.PM_SPLIT_ON:      # 32768 = split attivo
                return True
            if v == self.PM_SPLIT_OFF:     # 65536 = split spento
                return False
        except Exception:
            pass
        # Fallback: FreqB diverso da FreqA di più di 100 Hz
        try:
            fa, fb = self.get_freq_ab()
            if fa and fb:
                return abs(fb - fa) > 100
        except Exception:
            pass
        return None

    def toggle_split(self):
        """Attiva/disattiva lo split scrivendo la proprietà .Split con le
        costanti verificate sul rig: pmSplitOn=32768 (0x8000),
        pmSplitOff=65536 (0x10000). Ritorna il nuovo stato o None se fallito."""
        if not self._assicura():
            return None
        # Stato attuale dalla proprietà .Split (valori esatti)
        attuale_on = None
        try:
            v = int(self._rig.Split)
            if v == self.PM_SPLIT_ON:
                attuale_on = True
            elif v == self.PM_SPLIT_OFF:
                attuale_on = False
        except Exception:
            attuale_on = self.is_split()
        vuoi_on = not bool(attuale_on)
        nuovo = self.PM_SPLIT_ON if vuoi_on else self.PM_SPLIT_OFF
        # Scrive la costante nella proprietà .Split
        try:
            self._rig.Split = nuovo
            return vuoi_on
        except Exception:
            pass
        # Fallback: SetSplitMode / SetSimplexMode
        try:
            fa, fb = self.get_freq_ab()
            if vuoi_on and fb:
                self._rig.SetSplitMode(int(fb))
                return True
            elif not vuoi_on and fa:
                self._rig.SetSimplexMode(int(fa))
                return False
        except Exception:
            pass
        return None

    def vfo_swap(self):
        """Scambia VFO-A e VFO-B (pmVfoSwap). Supportato dalle radio che
        espongono il comando (es. IC-9700). Sul IC-7600, che non espone
        pmVfoSwap, ripiega sullo scambio manuale delle due frequenze.
        Ritorna True se un comando è stato inviato."""
        if not self._assicura():
            return False
        # Metodo 1: comando pmVfoSwap (radio che lo supportano)
        try:
            self._rig.Vfo = self.PM_VFO_SWAP
            return True
        except Exception:
            pass
        # Metodo 2 (fallback): scambia manualmente le frequenze RX<->TX
        try:
            fa, fb = self.get_freq_ab()
            if fa and fb:
                self._rig.FreqA = int(fb)
                self._rig.FreqB = int(fa)
                return True
        except Exception:
            pass
        return False

    def get_modo(self):
        """Modo corrente come stringa ('CW','USB','LSB','USB-D','RTTY','AM',
        'FM'), o None.

        Usa le costanti PM_* ufficiali di OmniRig (universali per tutte le
        radio: Icom, Yaesu, Kenwood...). Verificate sull'IC-7600.
        """
        if not self._assicura():
            return None
        try:
            m = int(self._rig.Mode)
        except Exception:
            return None
        if m == 0:
            return None
        # Controlla i bit in ordine di specificità (CW_U prima di CW_L, ecc.)
        ordine = ["pmDIG_U", "pmDIG_L", "pmCW_U", "pmCW_L",
                  "pmSSB_U", "pmSSB_L", "pmAM", "pmFM"]
        for pm in ordine:
            if m & self.PM_MODI[pm]:
                return self.PM_TO_MODO[pm]
        return None

    def set_modo(self, modo, dig_come_usbd=True):
        """Imposta il modo dalla stringa ADIF ('CW','SSB','USB','LSB','FT8'...).

        Usa le costanti PM_* ufficiali di OmniRig (universali). Verificate
        sull'IC-7600 e valide per tutte le radio supportate da OmniRig.

        dig_come_usbd: se True, i modi digitali (FT8, FT4, PSK, JT65...) vanno
        in USB-D (pmDIG_U), il modo giusto per FT8. Se False, vanno in RTTY.
        """
        if not self._assicura():
            return False
        modo = (modo or "").upper()
        if not modo:
            return False   # nessun modo: non toccare la radio
        P = self.PM_MODI

        if modo == "USB":
            bit = P["pmSSB_U"]
        elif modo == "USB-D":
            bit = P["pmDIG_U"]
        elif modo == "LSB":
            bit = P["pmSSB_L"]
        elif modo == "LSB-D":
            bit = P["pmDIG_L"]
        elif modo == "CW":
            bit = P["pmCW_L"]
        elif modo in ("CWR", "CW-R"):
            bit = P["pmCW_U"]
        elif modo == "AM":
            bit = P["pmAM"]
        elif modo == "FM":
            bit = P["pmFM"]
        elif modo == "SSB":
            f = self.get_freq() or 14000000
            bit = P["pmSSB_U"] if f >= 10000000 else P["pmSSB_L"]
        elif modo == "RTTY":
            bit = P["pmDIG_L"]
        else:
            # Modi digitali (FT8, FT4, PSK, JT65, JT9, MSK144...)
            bit = P["pmDIG_U"] if dig_come_usbd else P["pmDIG_L"]
        try:
            self._rig.Mode = bit
            return True
        except Exception:
            return False

    def qsy(self, hz, modo=None, dig_come_usbd=True, usa_bandplan=True):
        """Porta la radio su frequenza (Hz) e imposta il modo.

        usa_bandplan: se True (default), il modo viene dedotto dal band plan
        IARU R1 in base alla frequenza, con PRIORITÀ sul modo passato. Questo
        garantisce anche la sideband corretta (LSB<10MHz, USB>10MHz) e riempie
        il modo quando lo spot non lo indica. Se il band plan non copre la
        frequenza, si ripiega sul modo passato.
        """
        ok = self.set_freq(hz)
        modo_finale = None
        if usa_bandplan:
            modo_finale = modo_da_bandplan(hz)
        if not modo_finale and modo and modo.strip():
            modo_finale = modo.strip()
        if modo_finale:
            self.set_modo(modo_finale, dig_come_usbd=dig_come_usbd)
        return ok

    def stato(self):
        """Stringa di stato leggibile: nome radio e stato connessione."""
        if not self._assicura():
            return None
        try:
            return str(self._rig.StatusStr)
        except Exception:
            return None

    def diagnostica(self):
        """Ritorna una stringa con i valori grezzi letti da OmniRig,
        utile per capire perché la lettura non funziona."""
        if not self._assicura():
            return "OmniRig non connesso (connetti() ha fallito)."
        righe = []
        for prop in ("Status", "StatusStr", "Freq", "FreqA", "FreqB",
                     "Mode", "Vfo", "Rit", "Xit", "Split"):
            try:
                val = getattr(self._rig, prop)
                righe.append(f"{prop} = {val}")
            except Exception as ex:
                righe.append(f"{prop} = <errore: {ex}>")
        return "\n".join(righe)


