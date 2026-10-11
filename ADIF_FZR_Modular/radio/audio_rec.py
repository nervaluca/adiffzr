"""
Registratore audio per i QSO "mitici" di ADIF FZR.

Backend NATIVO Windows (winmm via ctypes): NESSUNA dipendenza esterna
(niente sounddevice, niente PortAudio, niente numpy). Si impacchetta sempre
nell'exe: l'utente finale non installa nulla.

- Ingresso audio SCELTO OGNI VOLTA (scheda della radio / microfono).
- Salva in WAV; se e' disponibile ffmpeg (imageio-ffmpeg o nel PATH) -> MP3.
- File in  <backup>/audio/CALL_YYYYMMDD_HHMM  e collegabili al QSO selezionato
  (campo APP_ADIFFZR_AUDIO, che resta nell'export ADIF).
"""

import os
import sys
import wave
import array
import threading
import time
import datetime
import subprocess

import customtkinter as ctk


def _ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    import shutil
    return shutil.which("ffmpeg")


# ============================================================
#  Backend audio nativo Windows (winmm) — solo ctypes stdlib
# ============================================================
class WinRecorder:
    SR = 44100
    CH = 1
    BITS = 16
    NBUF = 8
    BUF_MS = 100  # durata di ogni buffer

    WAVE_MAPPER = 0xFFFFFFFF
    CALLBACK_EVENT = 0x00050000
    WHDR_DONE = 0x00000001
    WAVE_FORMAT_PCM = 1

    def __init__(self):
        import ctypes
        self.ctypes = ctypes
        self.winmm = ctypes.windll.winmm
        self.kernel32 = ctypes.windll.kernel32
        self._hwi = None
        self._event = None
        self._headers = []
        self._buffers = []
        self._chunks = []
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._level = 0.0
        self.on_chunk = None      # callback(bytes) opzionale per streaming (decoder CW)
        self.accumula = True      # se False non tiene i chunk in memoria (solo streaming)
        self._define_types()

    def _define_types(self):
        c = self.ctypes
        WORD = c.c_ushort; DWORD = c.c_uint; UINT = c.c_uint
        DWORD_PTR = c.c_size_t

        class WAVEFORMATEX(c.Structure):
            _fields_ = [("wFormatTag", WORD), ("nChannels", WORD),
                        ("nSamplesPerSec", DWORD), ("nAvgBytesPerSec", DWORD),
                        ("nBlockAlign", WORD), ("wBitsPerSample", WORD),
                        ("cbSize", WORD)]

        class WAVEHDR(c.Structure):
            pass
        WAVEHDR._fields_ = [("lpData", c.c_void_p), ("dwBufferLength", DWORD),
                            ("dwBytesRecorded", DWORD), ("dwUser", DWORD_PTR),
                            ("dwFlags", DWORD), ("dwLoops", DWORD),
                            ("lpNext", c.c_void_p), ("reserved", DWORD_PTR)]

        class WAVEINCAPS(c.Structure):
            _fields_ = [("wMid", WORD), ("wPid", WORD), ("vDriverVersion", UINT),
                        ("szPname", c.c_wchar * 32), ("dwFormats", DWORD),
                        ("wChannels", WORD), ("wReserved1", WORD)]

        self.WAVEFORMATEX = WAVEFORMATEX
        self.WAVEHDR = WAVEHDR
        self.WAVEINCAPS = WAVEINCAPS

        self.winmm.waveInGetNumDevs.restype = UINT
        self.winmm.waveInGetDevCapsW.argtypes = [UINT, c.POINTER(WAVEINCAPS), UINT]
        self.winmm.waveInGetDevCapsW.restype = UINT
        self.winmm.waveInOpen.argtypes = [c.POINTER(c.c_void_p), UINT,
                                          c.POINTER(WAVEFORMATEX), c.c_void_p,
                                          DWORD_PTR, DWORD]
        self.winmm.waveInOpen.restype = UINT
        for fn in ("waveInPrepareHeader", "waveInUnprepareHeader", "waveInAddBuffer"):
            f = getattr(self.winmm, fn)
            f.argtypes = [c.c_void_p, c.POINTER(WAVEHDR), UINT]; f.restype = UINT
        for fn in ("waveInStart", "waveInStop", "waveInReset", "waveInClose"):
            f = getattr(self.winmm, fn)
            f.argtypes = [c.c_void_p]; f.restype = UINT

    # ---- elenco ingressi ----
    def list_inputs(self):
        c = self.ctypes
        out = [(-1, "Predefinito di Windows")]
        try:
            n = self.winmm.waveInGetNumDevs()
        except Exception:
            n = 0
        for i in range(n):
            caps = self.WAVEINCAPS()
            if self.winmm.waveInGetDevCapsW(i, c.byref(caps), c.sizeof(caps)) == 0:
                out.append((i, caps.szPname))
        return out

    # ---- registrazione ----
    def start(self, device_id):
        c = self.ctypes
        wfx = self.WAVEFORMATEX(self.WAVE_FORMAT_PCM, self.CH, self.SR,
                                self.SR * self.CH * self.BITS // 8,
                                self.CH * self.BITS // 8, self.BITS, 0)
        self._event = self.kernel32.CreateEventW(None, False, False, None)
        hwi = c.c_void_p()
        dev = self.WAVE_MAPPER if (device_id is None or device_id < 0) else (device_id & 0xFFFFFFFF)
        r = self.winmm.waveInOpen(c.byref(hwi), dev, c.byref(wfx),
                                  c.cast(self._event, c.c_void_p), 0, self.CALLBACK_EVENT)
        if r != 0:
            raise RuntimeError("waveInOpen err " + str(r))
        self._hwi = hwi

        bufbytes = self.SR * self.CH * self.BITS // 8 * self.BUF_MS // 1000
        self._headers = []; self._buffers = []; self._chunks = []
        for _ in range(self.NBUF):
            buf = c.create_string_buffer(bufbytes)
            hdr = self.WAVEHDR()
            hdr.lpData = c.cast(buf, c.c_void_p)
            hdr.dwBufferLength = bufbytes
            hdr.dwFlags = 0
            self.winmm.waveInPrepareHeader(hwi, c.byref(hdr), c.sizeof(hdr))
            self.winmm.waveInAddBuffer(hwi, c.byref(hdr), c.sizeof(hdr))
            self._buffers.append(buf); self._headers.append(hdr)

        self._running = True
        self.winmm.waveInStart(hwi)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        c = self.ctypes
        while self._running:
            try:
                self.kernel32.WaitForSingleObject(self._event, 120)
            except Exception:
                pass
            for hdr in self._headers:
                if hdr.dwFlags & self.WHDR_DONE:
                    n = hdr.dwBytesRecorded
                    if n:
                        data = c.string_at(hdr.lpData, n)
                        if self.accumula:
                            with self._lock:
                                self._chunks.append(data)
                        self._update_level(data)
                        cb = self.on_chunk
                        if cb:
                            try: cb(data)
                            except Exception: pass
                    if self._running:
                        hdr.dwFlags = hdr.dwFlags & ~self.WHDR_DONE
                        self.winmm.waveInAddBuffer(self._hwi, c.byref(hdr), c.sizeof(hdr))

    def _update_level(self, data):
        try:
            a = array.array('h'); a.frombytes(data)
            if not len(a):
                return
            step = max(1, len(a) // 400)
            m = 0
            for i in range(0, len(a), step):
                v = a[i]
                if v < 0:
                    v = -v
                if v > m:
                    m = v
            self._level = m / 32768.0
        except Exception:
            pass

    def level(self):
        return self._level

    def stop(self):
        c = self.ctypes
        self._running = False
        if not self._hwi:
            return b""
        try:
            self.winmm.waveInStop(self._hwi)
            self.winmm.waveInReset(self._hwi)
        except Exception:
            pass
        try:
            if self._thread:
                self._thread.join(timeout=1.0)
        except Exception:
            pass
        # raccogli eventuali buffer completati residui
        for hdr in self._headers:
            try:
                if hdr.dwFlags & self.WHDR_DONE and hdr.dwBytesRecorded:
                    with self._lock:
                        self._chunks.append(c.string_at(hdr.lpData, hdr.dwBytesRecorded))
            except Exception:
                pass
        for hdr in self._headers:
            try:
                self.winmm.waveInUnprepareHeader(self._hwi, c.byref(hdr), c.sizeof(hdr))
            except Exception:
                pass
        try:
            self.winmm.waveInClose(self._hwi)
        except Exception:
            pass
        try:
            if self._event:
                self.kernel32.CloseHandle(self._event)
        except Exception:
            pass
        self._hwi = None; self._event = None; self._headers = []; self._buffers = []
        with self._lock:
            return b"".join(self._chunks)


# ============================================================
#  Finestra registratore
# ============================================================
class RecorderWindow(ctk.CTkToplevel):
    SR = 44100
    CH = 1

    def __init__(self, parent, app, on_saved=None, call=None):
        super().__init__(parent)
        self.app = app
        self._on_saved = on_saved
        self._forced_call = call
        self.title("Registratore audio QSO")
        self.geometry("470x430")
        self.resizable(False, False)
        try:
            self.transient(parent); self.lift(); self.focus_force()
        except Exception:
            pass

        self._rec = None
        self._recording = False
        self._t0 = 0
        self._last_file = None
        self._inputs = []

        self._costruisci()
        self._init_backend()
        self._prefill_call()
        self._tick()
        self.protocol("WM_DELETE_WINDOW", self._chiudi)

    def _costruisci(self):
        ctk.CTkLabel(self, text="\U0001F399  Registratore QSO",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(14, 2))
        ctk.CTkLabel(self, text="Registra l'audio dall'ingresso scelto e allegalo al QSO.",
                     font=ctk.CTkFont(size=11), text_color="gray").pack(pady=(0, 10))

        fr = ctk.CTkFrame(self, fg_color="transparent"); fr.pack(fill="x", padx=18)
        ctk.CTkLabel(fr, text="Ingresso:", width=70, anchor="w").pack(side="left")
        self.cb_dev = ctk.CTkComboBox(fr, values=["(nessuno)"], width=310)
        self.cb_dev.pack(side="left", padx=(4, 0))

        fr2 = ctk.CTkFrame(self, fg_color="transparent"); fr2.pack(fill="x", padx=18, pady=(10, 0))
        ctk.CTkLabel(fr2, text="Livello:", width=70, anchor="w").pack(side="left")
        self.pb = ctk.CTkProgressBar(fr2, width=310); self.pb.set(0); self.pb.pack(side="left", padx=(4, 0))

        fr3 = ctk.CTkFrame(self, fg_color="transparent"); fr3.pack(fill="x", padx=18, pady=(10, 0))
        ctk.CTkLabel(fr3, text="Call:", width=70, anchor="w").pack(side="left")
        self.e_call = ctk.CTkEntry(fr3, width=150, placeholder_text="IK1ABC")
        self.e_call.pack(side="left")
        self.lbl_time = ctk.CTkLabel(fr3, text="00:00", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_time.pack(side="right")

        fr4 = ctk.CTkFrame(self, fg_color="transparent"); fr4.pack(fill="x", padx=18, pady=(14, 4))
        self.btn_rec = ctk.CTkButton(fr4, text="●  Registra", fg_color="#C0392B", hover_color="#96271b",
                                     height=40, command=self._toggle_rec)
        self.btn_rec.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.btn_play = ctk.CTkButton(fr4, text="▶ Riproduci", height=40, fg_color="#4A5568",
                                      hover_color="#2D3748", command=self._play_last, state="disabled")
        self.btn_play.pack(side="left", expand=True, fill="x")

        fr5 = ctk.CTkFrame(self, fg_color="transparent"); fr5.pack(fill="x", padx=18, pady=(8, 4))
        self.btn_attach = ctk.CTkButton(fr5, text="\U0001F4CE Allega al QSO selezionato", height=34,
                                        fg_color="#2C7BE5", command=self._attach, state="disabled")
        self.btn_attach.pack(fill="x")

        fr6 = ctk.CTkFrame(self, fg_color="transparent"); fr6.pack(fill="x", padx=18, pady=(4, 4))
        self.btn_playqso = ctk.CTkButton(fr6, text="▶ Audio del QSO selezionato", height=30,
                                         fg_color="#4A5568", hover_color="#2D3748",
                                         command=self._play_qso)
        self.btn_playqso.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.btn_delqso = ctk.CTkButton(fr6, text="\U0001F5D1 Rimuovi", height=30, width=100,
                                        fg_color="transparent", border_width=1, border_color="#E53E3E",
                                        text_color="#E53E3E", command=self._del_qso)
        self.btn_delqso.pack(side="left")

        self.lbl_stato = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.lbl_stato.pack(pady=(8, 0))

        # Riga cartella di destinazione (sempre visibile) + apri
        fr7 = ctk.CTkFrame(self, fg_color="transparent"); fr7.pack(fill="x", padx=18, pady=(2, 8))
        try:
            _dir = self._audio_dir()
        except Exception:
            _dir = "?"
        self.lbl_dir = ctk.CTkLabel(fr7, text="Cartella: " + _dir,
                                    font=ctk.CTkFont(size=10), text_color="#8a8f94",
                                    anchor="w", wraplength=330, justify="left")
        self.lbl_dir.pack(side="left", expand=True, fill="x")
        ctk.CTkButton(fr7, text="\U0001F4C2", width=34, height=26,
                      fg_color="#4A5568", hover_color="#2D3748",
                      command=lambda: self._apri_cartella()).pack(side="right")

    def _apri_cartella(self):
        try:
            d = self._audio_dir()
            if os.name == "nt":
                os.startfile(d)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:
            self._stato("Impossibile aprire la cartella: " + str(e), "#E53E3E")

    def _init_backend(self):
        if os.name != "nt":
            self._stato("Registrazione disponibile solo su Windows.", "#E53E3E")
            self.btn_rec.configure(state="disabled")
            return
        try:
            self._rec = WinRecorder()
            self._inputs = self._rec.list_inputs()
            names = [str(idx) + ": " + str(name) for idx, name in self._inputs]
            self.cb_dev.configure(values=names)
            self.cb_dev.set(names[0])
        except Exception as e:
            self._stato("Audio non disponibile: " + str(e), "#E53E3E")
            self.btn_rec.configure(state="disabled")

    def _dev_index(self):
        try:
            return int(self.cb_dev.get().split(":")[0])
        except Exception:
            return -1

    # ---- rec ----
    def _toggle_rec(self):
        if self._recording:
            self._stop()
        else:
            self._start()

    def _start(self):
        if not self._rec:
            return
        try:
            self._rec.start(self._dev_index())
            self._recording = True
            self._t0 = time.time()
            self.btn_rec.configure(text="■  Stop", fg_color="#2D3748", hover_color="#1A202C")
            self._stato("Registrazione in corso…", "#F6AD55")
        except Exception as e:
            self._stato("Impossibile aprire l'ingresso: " + str(e), "#E53E3E")

    def _stop(self):
        self._recording = False
        self.btn_rec.configure(text="●  Registra", fg_color="#C0392B", hover_color="#96271b")
        self.pb.set(0)
        try:
            pcm = self._rec.stop()
        except Exception as e:
            self._stato("Errore stop: " + str(e), "#E53E3E"); return
        self._salva(pcm)

    def _salva(self, pcm):
        if not pcm:
            self._stato("Niente da salvare.", "#E53E3E"); return
        call = (self.e_call.get().strip().upper() or "QSO")
        safe = "".join(ch for ch in call if ch.isalnum() or ch in "/_-") or "QSO"
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        adir = self._audio_dir()
        wav_path = os.path.join(adir, safe + "_" + ts + ".wav")
        try:
            with wave.open(wav_path, "wb") as w:
                w.setnchannels(self.CH); w.setsampwidth(2); w.setframerate(self.SR)
                w.writeframes(pcm)
        except Exception as e:
            self._stato("Errore salvataggio in:\n" + wav_path + "\n" + str(e), "#E53E3E")
            try:
                self.lbl_dir.configure(text="Cartella: " + adir)
            except Exception:
                pass
            return

        final = wav_path
        ff = _ffmpeg_exe()
        if ff:
            mp3_path = wav_path[:-4] + ".mp3"
            try:
                flags = 0
                try:
                    flags = subprocess.CREATE_NO_WINDOW
                except Exception:
                    flags = 0
                cmd = [ff, "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "3", mp3_path]
                if flags:
                    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
                else:
                    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if r.returncode == 0 and os.path.exists(mp3_path):
                    try: os.remove(wav_path)
                    except Exception: pass
                    final = mp3_path
            except Exception:
                pass

        self._last_file = final
        self.btn_play.configure(state="normal")
        self.btn_attach.configure(state="normal")
        if self._on_saved:
            try: self._on_saved(final)
            except Exception: pass
        dur = len(pcm) / float(self.SR * 2)
        self._stato("Salvato: " + os.path.basename(final) + "  (" + str(int(dur)) + "s)", "#38A169")

    # ---- play / qso ----
    def _apri_file(self, path):
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self._stato("Impossibile riprodurre: " + str(e), "#E53E3E")

    def _play_last(self):
        if self._last_file and os.path.exists(self._last_file):
            self._apri_file(self._last_file)

    def _attach(self):
        if not self._last_file:
            return
        try:
            ok = self.app._allega_audio_a_selezionato(self._last_file)
        except Exception as e:
            self._stato("Errore allega: " + str(e), "#E53E3E"); return
        if ok:
            self._stato("Audio allegato al QSO selezionato.", "#38A169")

    def _qso_audio_path(self):
        try:
            q = self.app._qso_selezionato()
        except Exception:
            q = None
        if not q:
            return None, None
        name = q.get("app_adiffzr_audio") or q.get("APP_ADIFFZR_AUDIO")
        if not name:
            return q, None
        p = name
        if not os.path.isabs(p):
            p = os.path.join(self._audio_dir(), name)
        return q, p

    def _play_qso(self):
        q, p = self._qso_audio_path()
        if not q:
            self._stato("Seleziona un QSO nella griglia.", "#F6AD55"); return
        if not p or not os.path.exists(p):
            self._stato("Il QSO selezionato non ha audio.", "#F6AD55"); return
        self._apri_file(p)

    def _del_qso(self):
        q, p = self._qso_audio_path()
        if not q or not p:
            self._stato("Nessun audio da rimuovere.", "#F6AD55"); return
        from tkinter import messagebox
        if not messagebox.askyesno("Rimuovi audio",
                                   "Scollegare l'audio dal QSO? (il file resta su disco)", parent=self):
            return
        try:
            q.pop("app_adiffzr_audio", None); q.pop("APP_ADIFFZR_AUDIO", None)
            self.app._log_modificato = True
            try: self.app._aggiorna_tree()
            except Exception: pass
            self._stato("Audio scollegato dal QSO.", "#38A169")
        except Exception as e:
            self._stato("Errore: " + str(e), "#E53E3E")

    # ---- util ----
    def _audio_dir(self):
        """Ritorna la PRIMA cartella realmente scrivibile per gli audio.

        Prova, in ordine: <backup>/audio, <dati>/audio, %APPDATA%/ADIF_FZR/audio,
        ~/Documents/ADIF_FZR/audio, cartella del programma, temp. Verifica la
        scrivibilita' creando un file di test, cosi' non fallisce piu' al salvataggio.
        """
        cand = []
        # 1) cartella di backup configurata dall'app
        try:
            cand.append(os.path.join(self.app._cartella_backup(), "audio"))
        except Exception:
            pass
        # 2) cartella dati dell'app
        try:
            from utils.log_profili import cartella_dati as _cd
            cand.append(os.path.join(_cd(), "audio"))
        except Exception:
            pass
        # 3) %APPDATA%\ADIF_FZR\audio
        ap = os.environ.get("APPDATA", "")
        if ap:
            cand.append(os.path.join(ap, "ADIF_FZR", "audio"))
        # 4) ~/Documents/ADIF_FZR/audio  e  ~/ADIF_FZR/audio
        home = os.path.expanduser("~")
        cand.append(os.path.join(home, "Documents", "ADIF_FZR", "audio"))
        cand.append(os.path.join(home, "ADIF_FZR", "audio"))
        # 5) temp di sistema
        try:
            import tempfile
            cand.append(os.path.join(tempfile.gettempdir(), "ADIF_FZR_audio"))
        except Exception:
            pass

        for d in cand:
            if not d:
                continue
            try:
                os.makedirs(d, exist_ok=True)
                test = os.path.join(d, ".scrittura_test")
                with open(test, "w") as _f:
                    _f.write("ok")
                os.remove(test)
                return d
            except Exception:
                continue
        # ultima spiaggia: cwd (senza garanzie)
        d = os.path.join(os.getcwd(), "audio")
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        return d

    def _prefill_call(self):
        try:
            if self._forced_call:
                self.e_call.delete(0, "end"); self.e_call.insert(0, str(self._forced_call).upper())
                return
            q = self.app._qso_selezionato()
            if q:
                c = q.get("call") or q.get("CALL")
                if c:
                    self.e_call.delete(0, "end"); self.e_call.insert(0, str(c).upper())
        except Exception:
            pass

    def _tick(self):
        try:
            if self._recording:
                el = int(time.time() - self._t0)
                self.lbl_time.configure(text="%02d:%02d" % (el // 60, el % 60))
                try:
                    self.pb.set(min(1.0, self._rec.level() * 1.4))
                except Exception:
                    pass
            self.after(150, self._tick)
        except Exception:
            pass

    def _stato(self, msg, col="gray"):
        try:
            self.lbl_stato.configure(text=msg, text_color=col)
        except Exception:
            pass

    def _chiudi(self):
        try:
            if self._recording:
                self._stop()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
