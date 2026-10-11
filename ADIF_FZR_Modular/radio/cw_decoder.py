# -*- coding: utf-8 -*-
"""
cw_decoder.py — Decoder CW da audio (Goertzel + timing adattivo).

Riceve blocchi PCM 16-bit mono (bytes) via feed(), stima l'inviluppo del tono
alla frequenza 'pitch', ricava punti/linee con soglia adattiva e traduce in
testo. WPM stimato in automatico.

Nessun servizio esterno: usa numpy (già presente per skyfield).
Limiti onesti: funziona bene su segnali puliti e stabili; con rumore/QSB,
segnali sovrapposti o mano irregolare sbaglia — come ogni decoder CW software.
"""

import math
import numpy as np

SR = 44100

# Tabella Morse -> carattere
_MORSE = {
    ".-": "A", "-...": "B", "-.-.": "C", "-..": "D", ".": "E", "..-.": "F",
    "--.": "G", "....": "H", "..": "I", ".---": "J", "-.-": "K", ".-..": "L",
    "--": "M", "-.": "N", "---": "O", ".--.": "P", "--.-": "Q", ".-.": "R",
    "...": "S", "-": "T", "..-": "U", "...-": "V", ".--": "W", "-..-": "X",
    "-.--": "Y", "--..": "Z",
    "-----": "0", ".----": "1", "..---": "2", "...--": "3", "....-": "4",
    ".....": "5", "-....": "6", "--...": "7", "---..": "8", "----.": "9",
    ".-.-.-": ".", "--..--": ",", "..--..": "?", "-..-.": "/", "-...-": "=",
    ".-.-.": "+", "-....-": "-", "-.--.": "(", "-.--.-": ")", ".--.-.": "@",
    "---...": ":", ".----.": "'", "..--.-": "_", "...-..-": "$",
    "-.-.--": "!", ".-..-.": '"', "-.-.-.": ";",
    # prosigni comuni
    "...-.-": "<SK>", "-.-.-": "<KA>", "...-.": "<SN>", ".-.-": "<AA>",
    "-...-.-": "<BK>",
}


class CWDecoder:
    def __init__(self, pitch=700, frame=330):
        self.pitch = int(pitch)
        self.frame = int(frame)          # campioni per frame (~7.5 ms a 44100)
        self.frame_ms = 1000.0 * self.frame / SR
        self._ref = None
        self._ref_lo = None
        self._ref_hi = None
        self._prep_ref()
        self._resto = np.zeros(0, dtype=np.float32)
        # callback
        self.on_text = None              # on_text(str)  -> testo decodificato
        self.on_level = None             # on_level(mag01, tuned01)
        self.on_spectrum = None          # on_spectrum(mags01, peak_freq, fmax)
        # spettro (FFT)
        self._nfft = 4096
        self._binhz = float(SR) / self._nfft
        self._fmax = 1400.0
        self._kmax = int(self._fmax / self._binhz)
        # ricerca del picco solo nella banda CW audio (evita ronzio/50 Hz)
        self._kpmin = int(250.0 / self._binhz)
        self._kpmax = int(1150.0 / self._binhz)
        self._win = np.hanning(self._nfft).astype(np.float32)
        self._spec_buf = np.zeros(self._nfft, dtype=np.float32)
        self._spec_acc = 0
        self._spec_hop = int(SR * 0.08)   # ricalcola lo spettro ~ ogni 80 ms
        self.reset()

    # ---- configurazione ----
    def _prep_ref(self):
        n = self.frame
        t = np.arange(n)
        self._ref = np.exp(-2j * np.pi * self.pitch * t / SR)
        self._ref_lo = np.exp(-2j * np.pi * max(200, self.pitch - 120) * t / SR)
        self._ref_hi = np.exp(-2j * np.pi * (self.pitch + 120) * t / SR)

    def imposta_pitch(self, f):
        self.pitch = int(f)
        self._prep_ref()

    def reset(self):
        self.dot = 60.0                  # ms stimati per un punto (~20 wpm)
        self._sym = ""                   # . e - del carattere in corso
        self._char_flushed = False
        self._word_flushed = True
        self._env = 0.0
        self._peak = 1e-9
        self._noise = 1e-9
        self._on = False                 # uscita isteresi (grezza)
        # debounce (antirimbalzo) sulle transizioni
        self._deb_state = 0              # stato logico confermato (0/1)
        self._deb_count = 0             # frame candidati al cambio
        self._cur_ms = 0.0               # durata dello stato confermato

    def wpm(self):
        try:
            return int(round(1200.0 / max(5.0, self.dot)))
        except Exception:
            return 0

    def info(self):
        return "%d WPM" % self.wpm()

    def imposta_shift(self, s):
        pass

    # ---- ingresso audio ----
    def feed(self, pcm_bytes):
        if not pcm_bytes:
            return
        x = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        # aggiorna il buffer per lo spettro e ricalcolalo ogni tanto
        self._aggiorna_spettro(x)
        if self._resto.size:
            x = np.concatenate([self._resto, x])
        n = self.frame
        nfr = x.size // n
        for i in range(nfr):
            seg = x[i * n:(i + 1) * n]
            self._elabora_frame(seg)
        self._resto = x[nfr * n:].copy()

    def _aggiorna_spettro(self, x):
        if self.on_spectrum is None:
            return
        m = x.size
        if m >= self._nfft:
            self._spec_buf = x[-self._nfft:].astype(np.float32)
        else:
            self._spec_buf = np.concatenate([self._spec_buf[m:], x])
        self._spec_acc += m
        if self._spec_acc < self._spec_hop:
            return
        self._spec_acc = 0
        try:
            sp = np.abs(np.fft.rfft(self._spec_buf * self._win))[:self._kmax]
            # picco cercato solo nella banda CW (250–1150 Hz)
            a = max(0, self._kpmin)
            b = min(sp.size, self._kpmax)
            if b > a:
                peak_bin = a + int(np.argmax(sp[a:b]))
            else:
                peak_bin = int(np.argmax(sp)) if sp.size else 0
            peak_freq = peak_bin * self._binhz
            mx = float(sp.max()) if sp.size else 0.0
            mags01 = np.sqrt(sp / mx) if mx > 1e-9 else sp * 0.0
            self.on_spectrum(mags01, float(peak_freq), float(self._kmax * self._binhz))
        except Exception:
            pass

    def _elabora_frame(self, seg):
        mag = abs(np.dot(seg, self._ref)) / self.frame
        # inviluppo poco smussato (edge più netti)
        self._env = 0.35 * self._env + 0.65 * mag
        # aggiorna picco e rumore (floor)
        if mag > self._peak:
            self._peak = mag
        else:
            self._peak *= 0.9993
        if mag < self._noise:
            self._noise = 0.5 * self._noise + 0.5 * mag
        else:
            self._noise = self._noise * 0.9997 + mag * 0.0003
        span = max(1e-9, self._peak - self._noise)
        thr_hi = self._noise + 0.40 * span
        thr_lo = self._noise + 0.22 * span
        # isteresi
        if not self._on and self._env > thr_hi:
            self._on = True
        elif self._on and self._env < thr_lo:
            self._on = False

        # indicatore livello + sintonia (centro vs lati)
        if self.on_level is not None:
            try:
                mlo = abs(np.dot(seg, self._ref_lo)) / self.frame
                mhi = abs(np.dot(seg, self._ref_hi)) / self.frame
                tuned = mag / (mag + mlo + mhi + 1e-9)   # ~1 se centrato
                lvl = min(1.0, mag / (self._peak + 1e-9))
                self.on_level(float(lvl), float(tuned))
            except Exception:
                pass

        self._debounce(self._on)

    # ---- antirimbalzo + macchina a stati punti/linee ----
    def _deb_need(self):
        # quanti frame consecutivi servono per confermare un cambio di stato:
        # ~ 1/3 di punto, ma almeno 1 frame e al più 4 (evita di mangiare i dit)
        g_ms = min(18.0, 0.33 * self.dot)
        return max(1, min(4, int(round(g_ms / self.frame_ms))))

    def _debounce(self, raw):
        self._cur_ms += self.frame_ms
        if raw == self._deb_state:
            self._deb_count = 0
            # durante il silenzio confermato: sfoga carattere/parola
            if self._deb_state == 0:
                if self._sym and (not self._char_flushed) and self._cur_ms >= 2.0 * self.dot:
                    self._emetti_char()
                    self._char_flushed = True
                if (not self._word_flushed) and self._cur_ms >= 5.0 * self.dot:
                    self._emetti(" ")
                    self._word_flushed = True
            return
        # candidato al cambio
        self._deb_count += 1
        need = self._deb_need()
        if self._deb_count < need:
            return
        # conferma la transizione: durata reale ≈ cur_ms meno i frame candidati
        dur = max(self.frame_ms, self._cur_ms - self.frame_ms * need)
        finito = self._deb_state
        self._deb_state = raw
        self._deb_count = 0
        self._cur_ms = self.frame_ms * need   # il nuovo stato dura già 'need' frame
        if finito == 1:
            # è finito un MARK -> punto o linea
            self._fine_mark(dur)
        else:
            # è iniziato un MARK -> nuovo silenzio azzerato
            self._char_flushed = False
            self._word_flushed = False

    def _fine_mark(self, dur):
        if dur < 2.0 * self.dot:
            self._sym += "."
            self.dot = 0.70 * self.dot + 0.30 * dur           # adatta dai punti
        else:
            self._sym += "-"
            self.dot = 0.85 * self.dot + 0.15 * (dur / 3.0)   # adatta dalle linee
        self.dot = min(180.0, max(25.0, self.dot))

    def _emetti_char(self):
        if not self._sym:
            return
        ch = _MORSE.get(self._sym, "")
        self._sym = ""
        if ch:
            self._emetti(ch)

    def _emetti(self, s):
        if self.on_text is not None:
            try:
                self.on_text(s)
            except Exception:
                pass


if __name__ == "__main__":
    # Auto-test: genera CW sintetico "PARIS" e verifica la decodifica
    d = CWDecoder(pitch=700)
    out = []
    d.on_text = lambda s: out.append(s)
    wpm = 20
    dot = 1.2 / wpm
    def tono(sec, on):
        n = int(SR * sec)
        t = np.arange(n)
        if on:
            sig = 0.5 * np.sin(2 * np.pi * 700 * t / SR)
        else:
            sig = np.zeros(n)
        return (sig * 32767).astype(np.int16).tobytes()
    seq = {".": ("1",), "-": ("3",)}
    testo = "PARIS PARIS"
    code = {"P": ".--.", "A": ".-", "R": ".-.", "I": "..", "S": "..."}
    for wi, w in enumerate(testo.split(" ")):
        for ci, chc in enumerate(w):
            pat = code[chc]
            for k, el in enumerate(pat):
                d.feed(tono(dot * (1 if el == "." else 3), True))
                if k < len(pat) - 1:
                    d.feed(tono(dot, False))
            d.feed(tono(3 * dot, False))
        d.feed(tono(7 * dot, False))
    print("decodificato:", "".join(out))
