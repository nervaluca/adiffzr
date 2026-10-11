# -*- coding: utf-8 -*-
"""
audio_out.py — Riproduzione audio nativa Windows (winmm waveOut, solo ctypes).

Gemello di WinRecorder: manda PCM 16-bit mono 44100 Hz alla scheda audio
scelta (tipicamente quella collegata all'ingresso della radio, per la TX dei
modi digitali). Nessuna dipendenza esterna.

    p = WinPlayer()
    p.list_outputs()                      # [(-1,"Predefinito"), (0,"..."), ...]
    p.play(pcm_bytes, device_id=-1, on_done=cb)   # non bloccante
    p.stop()                              # interrompe subito (waveOutReset)
    p.is_playing()
"""

import threading


class WinPlayer:
    SR = 44100
    CH = 1
    BITS = 16

    WAVE_MAPPER = 0xFFFFFFFF
    CALLBACK_EVENT = 0x00050000
    WHDR_DONE = 0x00000001
    WAVE_FORMAT_PCM = 1

    def __init__(self):
        import ctypes
        self.ctypes = ctypes
        self.winmm = ctypes.windll.winmm
        self.kernel32 = ctypes.windll.kernel32
        self._hwo = None
        self._event = None
        self._hdr = None
        self._buf = None
        self._thread = None
        self._playing = False
        self._stop = False
        self.on_done = None
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

        class WAVEOUTCAPS(c.Structure):
            _fields_ = [("wMid", WORD), ("wPid", WORD), ("vDriverVersion", UINT),
                        ("szPname", c.c_wchar * 32), ("dwFormats", DWORD),
                        ("wChannels", WORD), ("wReserved1", WORD),
                        ("dwSupport", DWORD)]

        self.WAVEFORMATEX = WAVEFORMATEX
        self.WAVEHDR = WAVEHDR
        self.WAVEOUTCAPS = WAVEOUTCAPS

        self.winmm.waveOutGetNumDevs.restype = UINT
        self.winmm.waveOutGetDevCapsW.argtypes = [UINT, c.POINTER(WAVEOUTCAPS), UINT]
        self.winmm.waveOutGetDevCapsW.restype = UINT
        self.winmm.waveOutOpen.argtypes = [c.POINTER(c.c_void_p), UINT,
                                           c.POINTER(WAVEFORMATEX), c.c_void_p,
                                           DWORD_PTR, DWORD]
        self.winmm.waveOutOpen.restype = UINT
        for fn in ("waveOutPrepareHeader", "waveOutUnprepareHeader", "waveOutWrite"):
            f = getattr(self.winmm, fn)
            f.argtypes = [c.c_void_p, c.POINTER(WAVEHDR), UINT]; f.restype = UINT
        for fn in ("waveOutReset", "waveOutClose"):
            f = getattr(self.winmm, fn)
            f.argtypes = [c.c_void_p]; f.restype = UINT

    # ---- elenco uscite ----
    def list_outputs(self):
        c = self.ctypes
        out = [(-1, "Predefinito di Windows")]
        try:
            n = self.winmm.waveOutGetNumDevs()
        except Exception:
            n = 0
        for i in range(n):
            caps = self.WAVEOUTCAPS()
            if self.winmm.waveOutGetDevCapsW(i, c.byref(caps), c.sizeof(caps)) == 0:
                out.append((i, caps.szPname))
        return out

    # ---- riproduzione ----
    def is_playing(self):
        return self._playing

    def play(self, pcm_bytes, device_id=-1, on_done=None):
        if self._playing:
            self.stop()
        if not pcm_bytes:
            if on_done:
                on_done()
            return
        c = self.ctypes
        self.on_done = on_done
        self._stop = False
        wfx = self.WAVEFORMATEX(self.WAVE_FORMAT_PCM, self.CH, self.SR,
                                self.SR * self.CH * self.BITS // 8,
                                self.CH * self.BITS // 8, self.BITS, 0)
        self._event = self.kernel32.CreateEventW(None, False, False, None)
        hwo = c.c_void_p()
        dev = self.WAVE_MAPPER if (device_id is None or device_id < 0) else (device_id & 0xFFFFFFFF)
        r = self.winmm.waveOutOpen(c.byref(hwo), dev, c.byref(wfx),
                                   c.cast(self._event, c.c_void_p), 0, self.CALLBACK_EVENT)
        if r != 0:
            raise RuntimeError("waveOutOpen err " + str(r))
        self._hwo = hwo
        # buffer unico con tutto il PCM
        self._buf = c.create_string_buffer(bytes(pcm_bytes), len(pcm_bytes))
        hdr = self.WAVEHDR()
        hdr.lpData = c.cast(self._buf, c.c_void_p)
        hdr.dwBufferLength = len(pcm_bytes)
        hdr.dwFlags = 0
        self._hdr = hdr
        self.winmm.waveOutPrepareHeader(hwo, c.byref(hdr), c.sizeof(hdr))
        self.winmm.waveOutWrite(hwo, c.byref(hdr), c.sizeof(hdr))
        self._playing = True
        self._thread = threading.Thread(target=self._wait_loop, daemon=True)
        self._thread.start()

    def _wait_loop(self):
        c = self.ctypes
        try:
            while self._playing and not self._stop:
                try:
                    self.kernel32.WaitForSingleObject(self._event, 100)
                except Exception:
                    pass
                if self._hdr is not None and (self._hdr.dwFlags & self.WHDR_DONE):
                    break
        finally:
            self._cleanup()
            cb = self.on_done
            if cb:
                try:
                    cb()
                except Exception:
                    pass

    def _cleanup(self):
        c = self.ctypes
        self._playing = False
        try:
            if self._hwo is not None:
                self.winmm.waveOutReset(self._hwo)
                if self._hdr is not None:
                    self.winmm.waveOutUnprepareHeader(self._hwo, c.byref(self._hdr),
                                                      c.sizeof(self._hdr))
                self.winmm.waveOutClose(self._hwo)
        except Exception:
            pass
        try:
            if self._event:
                self.kernel32.CloseHandle(self._event)
        except Exception:
            pass
        self._hwo = None; self._hdr = None; self._buf = None; self._event = None

    def stop(self):
        self._stop = True
        try:
            if self._hwo is not None:
                self.winmm.waveOutReset(self._hwo)   # marca i buffer come DONE
        except Exception:
            pass
        t = self._thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=1.0)
        self._playing = False


if __name__ == "__main__":
    # Test a secco: elenco uscite (richiede Windows)
    try:
        p = WinPlayer()
        print("Uscite audio:", p.list_outputs())
    except Exception as e:
        print("Solo Windows:", e)
