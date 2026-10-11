# -*- coding: utf-8 -*-
"""
digimodes.py — Decoder RTTY (Baudot/ITA2) e PSK31 (BPSK) da audio.

Stessa interfaccia del CWDecoder così la GUI (spettro + waterfall + barre)
si riusa senza modifiche:
    feed(pcm_bytes)          # blocchi PCM 16-bit mono
    on_text(str)            # testo decodificato
    on_level(lvl01, tuned01)# barre livello / sintonia
    on_spectrum(mags01, peak_freq, fmax)
    imposta_pitch(f)        # RTTY: freq. di MARK ; PSK: freq. portante
    reset()
    info()                  # etichetta di stato (baud/shift)

Solo numpy. Limiti onesti: funzionano bene su segnali puliti e ben sintonizzati;
con QRM/QSB o sintonia errata sbagliano, come ogni decoder software.
"""

import numpy as np

SR = 44100


# ------------------------------------------------------------------ #
#  Helper spettro (identico in logica al CWDecoder, condiviso)        #
# ------------------------------------------------------------------ #
class _Spettro:
    def __init__(self, fmax=2600.0, pmin=250.0, pmax=2400.0):
        self._nfft = 4096
        self._binhz = float(SR) / self._nfft
        self._fmax = float(fmax)
        self._kmax = int(self._fmax / self._binhz)
        self._kpmin = int(pmin / self._binhz)
        self._kpmax = int(pmax / self._binhz)
        self._win = np.hanning(self._nfft).astype(np.float32)
        self._buf = np.zeros(self._nfft, dtype=np.float32)
        self._acc = 0
        self._hop = int(SR * 0.08)
        self.on_spectrum = None

    def push(self, x):
        if self.on_spectrum is None:
            return
        m = x.size
        if m >= self._nfft:
            self._buf = x[-self._nfft:].astype(np.float32)
        else:
            self._buf = np.concatenate([self._buf[m:], x])
        self._acc += m
        if self._acc < self._hop:
            return
        self._acc = 0
        try:
            sp = np.abs(np.fft.rfft(self._buf * self._win))[:self._kmax]
            a = max(0, self._kpmin)
            b = min(sp.size, self._kpmax)
            if b > a:
                peak_bin = a + int(np.argmax(sp[a:b]))
            else:
                peak_bin = int(np.argmax(sp)) if sp.size else 0
            mx = float(sp.max()) if sp.size else 0.0
            mags01 = np.sqrt(sp / mx) if mx > 1e-9 else sp * 0.0
            self.on_spectrum(mags01, float(peak_bin * self._binhz),
                             float(self._kmax * self._binhz))
        except Exception:
            pass


# ================================================================== #
#  RTTY — Baudot / ITA2, 45.45 baud, shift 170 Hz (predefiniti)       #
# ================================================================== #
_ITA2_LTRS = {
    0x00: "\x00", 0x01: "E", 0x02: "\n", 0x03: "A", 0x04: " ", 0x05: "S",
    0x06: "I", 0x07: "U", 0x08: "\r", 0x09: "D", 0x0A: "R", 0x0B: "J",
    0x0C: "N", 0x0D: "F", 0x0E: "C", 0x0F: "K", 0x10: "T", 0x11: "Z",
    0x12: "L", 0x13: "W", 0x14: "H", 0x15: "Y", 0x16: "P", 0x17: "Q",
    0x18: "O", 0x19: "B", 0x1A: "G", 0x1C: "M", 0x1D: "X", 0x1E: "V",
}
_ITA2_FIGS = {
    0x01: "3", 0x02: "\n", 0x03: "-", 0x04: " ", 0x05: "'", 0x06: "8",
    0x07: "7", 0x08: "\r", 0x09: "$", 0x0A: "4", 0x0B: "'", 0x0C: ",",
    0x0D: "!", 0x0E: ":", 0x0F: "(", 0x10: "5", 0x11: "+", 0x12: ")",
    0x13: "2", 0x14: "#", 0x15: "6", 0x16: "0", 0x17: "1", 0x18: "9",
    0x19: "?", 0x1A: "&", 0x1C: ".", 0x1D: "/", 0x1E: ";",
}
_FIGS = 0x1B
_LTRS = 0x1F


class RTTYDecoder:
    def __init__(self, mark=2125.0, shift=170.0, baud=45.45, reverse=False):
        self.mark = float(mark)
        self.shift = float(shift)
        self.baud = float(baud)
        self.rev = bool(reverse)
        self.uos = True                    # Unshift On Space
        self.on_text = None
        self.on_level = None
        self._spec = _Spettro(fmax=2800.0, pmin=800.0, pmax=2600.0)
        self._resto = np.zeros(0, dtype=np.float32)
        self._prep()
        self.reset()

    # -- config --
    def _prep(self):
        # USB: MARK = tono più alto, SPACE = mark - shift.
        # reverse (LSB/invertito): SPACE dall'altro lato.
        self.space = self.mark + self.shift if self.rev else self.mark - self.shift
        self._osr = 8                                   # decisioni per bit
        self._win = max(8, int(round(SR / self.baud / self._osr)))
        t = np.arange(self._win)
        self._rm = np.exp(-2j * np.pi * self.mark * t / SR)
        self._rs = np.exp(-2j * np.pi * self.space * t / SR)

    def imposta_pitch(self, f):
        # per coerenza con la GUI: 'pitch' = MARK
        self.mark = float(f)
        self._prep()

    def imposta_shift(self, s):
        self.shift = float(s)
        self._prep()

    def imposta_reverse(self, b):
        self.rev = bool(b)
        self._prep()

    def info(self):
        return "RTTY %.2f bd / %d Hz%s" % (self.baud, int(self.shift),
                                           " INV" if self.rev else "")

    def wpm(self):
        return int(round(self.baud))

    def reset(self):
        self._resto = np.zeros(0, dtype=np.float32)
        self._state = 0            # 0 idle, 1 start, 2 data, 3 stop
        self._cnt = 0
        self._val = 0
        self._bit = 0
        self._figs = False
        self._lvl = 0.0
        self._tuned = 0.0

    # -- ingresso --
    def feed(self, pcm):
        if not pcm:
            return
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        self._spec.push(x)
        if self._resto.size:
            x = np.concatenate([self._resto, x])
        n = self._win
        nfr = x.size // n
        for i in range(nfr):
            seg = x[i * n:(i + 1) * n]
            mm = abs(np.dot(seg, self._rm)) / n
            ms = abs(np.dot(seg, self._rs)) / n
            self._decisione(mm, ms)
        self._resto = x[nfr * n:].copy()

    def _decisione(self, mm, ms):
        tot = mm + ms + 1e-9
        self._lvl = min(1.0, 3.0 * tot)
        self._tuned = abs(mm - ms) / tot          # ~1 se ben separati
        if self.on_level is not None:
            try:
                self.on_level(float(self._lvl), float(self._tuned))
            except Exception:
                pass
        d = 1 if mm >= ms else 0                  # 1 = mark, 0 = space
        self._uart(d)

    def _uart(self, d):
        osr = self._osr
        if self._state == 0:                      # IDLE: attende start (space)
            if d == 0:
                self._state = 1; self._cnt = 0
        elif self._state == 1:                    # verifica metà start-bit
            self._cnt += 1
            if self._cnt >= osr // 2:
                if d == 0:
                    self._state = 2; self._cnt = 0; self._val = 0; self._bit = 0
                else:
                    self._state = 0
        elif self._state == 2:                    # 5 bit dati, LSB first
            self._cnt += 1
            if self._cnt >= osr:
                self._cnt = 0
                self._val |= (d << self._bit)
                self._bit += 1
                if self._bit >= 5:
                    self._state = 3
        elif self._state == 3:                    # stop bit -> emetti
            self._cnt += 1
            if self._cnt >= osr:
                self._cnt = 0
                self._emit(self._val)
                self._state = 0

    def _emit(self, v):
        if v == _FIGS:
            self._figs = True; return
        if v == _LTRS:
            self._figs = False; return
        ch = (_ITA2_FIGS if self._figs else _ITA2_LTRS).get(v, "")
        # UOS: dopo uno spazio torna alle lettere (riduce il garbage in FIGS)
        if self.uos and v == 0x04:
            self._figs = False
        if ch and ch not in ("\x00",):
            if self.on_text is not None:
                try:
                    self.on_text(ch)
                except Exception:
                    pass

    # -- spettro bridge --
    @property
    def on_spectrum(self):
        return self._spec.on_spectrum

    @on_spectrum.setter
    def on_spectrum(self, cb):
        self._spec.on_spectrum = cb


# ================================================================== #
#  PSK31 — BPSK differenziale + varicode                             #
# ================================================================== #
_VARICODE = {
    0: "1010101011", 1: "1011011011", 2: "1011101101", 3: "1101110111",
    4: "1011101011", 5: "1101011111", 6: "1011101111", 7: "1011111101",
    8: "1011111111", 9: "11101111", 10: "11101", 11: "1101101111",
    12: "1011011101", 13: "11111", 14: "1101110101", 15: "1110101011",
    16: "1011110111", 17: "1011110101", 18: "1110101101", 19: "1110101111",
    20: "1101011011", 21: "1101101011", 22: "1101101101", 23: "1101010111",
    24: "1101111011", 25: "1101111101", 26: "1110110111", 27: "1101010101",
    28: "1101011101", 29: "1110111011", 30: "1011111011", 31: "1101111111",
    32: "1", 33: "111111111", 34: "101011111", 35: "111110101",
    36: "111011011", 37: "1011010101", 38: "1010111011", 39: "101111111",
    40: "11111011", 41: "11110111", 42: "101101111", 43: "111011111",
    44: "1110101", 45: "110101", 46: "1010111", 47: "110101111",
    48: "10110111", 49: "10111101", 50: "11101101", 51: "11111111",
    52: "101110111", 53: "101011011", 54: "101101011", 55: "110101101",
    56: "110101011", 57: "110110111", 58: "11110101", 59: "110111101",
    60: "111101101", 61: "1010101", 62: "111010111", 63: "1010101111",
    64: "1010111101", 65: "1111101", 66: "11101011", 67: "10101101",
    68: "10110101", 69: "1110111", 70: "11011011", 71: "11111101",
    72: "101010101", 73: "1111111", 74: "111111101", 75: "101111101",
    76: "11010111", 77: "10111011", 78: "11011101", 79: "10101011",
    80: "11010101", 81: "111011101", 82: "10101111", 83: "1101111",
    84: "1101101", 85: "101010111", 86: "110110101", 87: "101011101",
    88: "101110101", 89: "101111011", 90: "1010101101", 91: "111110111",
    92: "111101111", 93: "111111011", 94: "1010111111", 95: "101101101",
    96: "1011011111", 97: "1011", 98: "1011111", 99: "101111",
    100: "101101", 101: "11", 102: "111101", 103: "1011011",
    104: "101011", 105: "1101", 106: "111101011", 107: "10111111",
    108: "11011", 109: "111011", 110: "1111", 111: "111",
    112: "111111", 113: "110111111", 114: "10101", 115: "10111",
    116: "101", 117: "110111", 118: "1111011", 119: "1101011",
    120: "11011111", 121: "1011101", 122: "111010101", 123: "1010110111",
    124: "110111011", 125: "1010110101", 126: "1011010111", 127: "1110110101",
}
_VARI_REV = {v: k for k, v in _VARICODE.items()}


class PSKDecoder:
    def __init__(self, pitch=1000.0):
        self.pitch = float(pitch)
        self.baud = 31.25
        self.on_text = None
        self.on_level = None
        self._spec = _Spettro(fmax=1800.0, pmin=300.0, pmax=1600.0)
        # decimazione: filtro FIR passa-basso poi ne prendo 1 su D
        self._D = 44
        self.fs2 = SR / self._D                  # ~1002 Hz
        self.sps2 = self.fs2 / self.baud          # ~32 campioni/simbolo
        # FIR passa-basso (~180 Hz) per il downsampling
        ntap = 64
        fc = 180.0 / (SR / 2.0)
        k = np.arange(ntap) - (ntap - 1) / 2.0
        h = np.sinc(2 * fc * k) * np.hamming(ntap)
        self._fir = (h / h.sum()).astype(np.float64)
        self.reset()

    def imposta_pitch(self, f):
        self.pitch = float(f)

    def imposta_shift(self, s):
        pass

    def info(self):
        return "PSK31 (BPSK 31.25 bd)"

    def wpm(self):
        return 31

    def reset(self):
        self._n = 0                      # indice campione globale (mixer NCO)
        self._tail = np.zeros(0, dtype=np.float64)   # coda per il FIR
        self._dec_i = 0                  # contatore per la decimazione
        self._lp = 0j                    # passa-basso 1-polo sul baseband
        # buffer decimato con indice assoluto (per interpolare i simboli)
        self._zbuf = []
        self._zbase = 0                  # indice assoluto di _zbuf[0]
        self._zidx = -1                  # indice assoluto dell'ultimo campione
        # timing recovery (Gardner)
        self._tnext = 2.0 * self.sps2    # istante (assoluto) del prossimo centro
        self._kt = 0.02                  # guadagno anello di timing
        self._last_sym = 1 + 0j
        self._bits = ""                  # varicode in costruzione
        self._lvl = 0.0
        self._tuned = 0.0

    def feed(self, pcm):
        if not pcm:
            return
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float64) / 32768.0
        self._spec.push(x.astype(np.float32))
        # mixer NCO alla portante (fase continua)
        idx = self._n + np.arange(x.size)
        bb = x * np.exp(-2j * np.pi * self.pitch * idx / SR)
        self._n += x.size
        # FIR + decimazione (mantengo coda)
        if self._tail.size:
            buf = np.concatenate([self._tail, bb])
        else:
            buf = bb
        ntap = self._fir.size
        if buf.size < ntap:
            self._tail = buf
            return
        yr = np.convolve(buf.real, self._fir, mode="valid")
        yi = np.convolve(buf.imag, self._fir, mode="valid")
        y = yr + 1j * yi                 # lunghezza buf.size-ntap+1
        self._tail = buf[-(ntap - 1):]
        # decimazione a passo D con contatore continuo
        start = (-self._dec_i) % self._D
        dec = y[start::self._D]
        self._dec_i = (self._dec_i + y.size - start) % self._D
        for s in dec:
            self._campione(s)

    def _interp(self, t):
        li = int(np.floor(t))
        j = li - self._zbase
        if j < 0 or j + 1 >= len(self._zbuf):
            return None
        frac = t - li
        a = self._zbuf[j]; b = self._zbuf[j + 1]
        return a + (b - a) * frac

    def _campione(self, s):
        # passa-basso 1-polo (matched filter leggero)
        self._lp = 0.55 * self._lp + 0.45 * s
        z = self._lp
        self._zbuf.append(z)
        self._zidx += 1
        mag = abs(z)
        self._lvl = 0.97 * self._lvl + 0.03 * min(1.0, 4.0 * mag)
        # produci simboli finché ho campioni oltre il centro corrente
        while self._tnext + 1.0 <= self._zidx:
            self._simbolo()
        # sfoltisci il buffer tenendo margine dietro al prossimo centro
        keep_from = int(self._tnext - 2.0 * self.sps2)
        if keep_from - self._zbase > int(4 * self.sps2):
            drop = keep_from - self._zbase
            if drop > 0:
                self._zbuf = self._zbuf[drop:]
                self._zbase += drop

    def _simbolo(self):
        z = self._interp(self._tnext)
        mid = self._interp(self._tnext - 0.5 * self.sps2)
        if z is None or mid is None:
            self._tnext += self.sps2
            return
        prev = self._last_sym
        # Gardner TED (BPSK): e = Re{ conj(mid) * (curr - prev) }
        e = np.real(np.conj(mid) * (z - prev))
        norm = abs(z) * abs(prev) + 1e-6
        self._tnext += self.sps2 - self._kt * (e / norm)
        self._last_sym = z
        # sintonia: quanto è sull'asse reale
        m = abs(z) + 1e-9
        self._tuned = 0.9 * self._tuned + 0.1 * min(1.0, abs(np.real(z)) / m)
        if self.on_level is not None:
            try:
                self.on_level(float(self._lvl), float(self._tuned))
            except Exception:
                pass
        # BPSK differenziale: reversal se prodotto col precedente è negativo
        d = z * np.conj(prev)
        bit = 0 if np.real(d) < 0 else 1     # 0 = reversal, 1 = no reversal
        self._varicode(bit)

    def _varicode(self, bit):
        if bit == 0:
            # separatore fra caratteri = "00"
            if self._bits.endswith("0"):
                seq = self._bits[:-1]
                self._bits = ""
                if seq:
                    code = _VARI_REV.get(seq)
                    if code is not None and 0 <= code < 128:
                        ch = chr(code)
                        if ch not in ("\x00",) and self.on_text is not None:
                            try:
                                self.on_text(ch if ch != "\r" else "")
                            except Exception:
                                pass
            else:
                self._bits += "0"
        else:
            self._bits += "1"
            if len(self._bits) > 24:              # varicode mai così lungo
                self._bits = self._bits[-24:]

    @property
    def on_spectrum(self):
        return self._spec.on_spectrum

    @on_spectrum.setter
    def on_spectrum(self, cb):
        self._spec.on_spectrum = cb


# ================================================================== #
#  GENERATORI DI TRASMISSIONE (audio TX) — RTTY e PSK31              #
# ================================================================== #
# Mappe carattere -> codice Baudot (per la TX)
_LTRS_ENC = {}
_FIGS_ENC = {}
for _v, _c in _ITA2_LTRS.items():
    _LTRS_ENC.setdefault(_c, _v)
for _v, _c in _ITA2_FIGS.items():
    _FIGS_ENC.setdefault(_c, _v)


def rtty_tx(testo, mark=2125.0, shift=170.0, baud=45.45, reverse=False,
            ampl=0.6, idle_s=0.4, stop_bits=1.5, noise=0.0):
    """Genera l'audio AFSK Baudot (RTTY) per il testo dato. Ritorna PCM 16-bit
    mono (bytes) a 44100 Hz. reverse=True scambia i toni (LSB/invertito)."""
    space = mark + shift if reverse else mark - shift
    spb = SR / baud
    seq = []  # (is_mark, unità_bit)

    def put(mk, units):
        seq.append((1 if mk else 0, units))

    # preambolo: diddle di LTRS a riposo
    n_idle = max(0, int(round(idle_s * baud / 7.5)))
    for _ in range(max(3, n_idle)):
        put(1, 1)                      # start non serve per il diddle grezzo -> usiamo mark idle
    figs = None                        # forza il primo shift
    testo = (testo or "").upper()
    for ch in testo:
        code = None; want_figs = None
        if ch in _LTRS_ENC and ch not in ("\x00",):
            code = _LTRS_ENC[ch]; want_figs = False
        if code is None and ch in _FIGS_ENC:
            code = _FIGS_ENC[ch]; want_figs = True
        if code is None:
            continue
        if want_figs is not None and want_figs != figs:
            sc = _FIGS if want_figs else _LTRS
            put(0, 1)                                  # start
            for i in range(5):
                put((sc >> i) & 1, 1)                  # LSB first
            put(1, stop_bits)                          # stop
            figs = want_figs
        put(0, 1)
        for i in range(5):
            put((code >> i) & 1, 1)
        put(1, stop_bits)
    # coda idle
    for _ in range(max(3, n_idle)):
        put(1, 1)

    out = []
    phase = 0.0
    for mk, units in seq:
        n = int(round(spb * units))
        if n <= 0:
            continue
        f = mark if mk else space
        t = np.arange(n)
        ph = phase + 2 * np.pi * f * t / SR
        out.append(ampl * np.sin(ph))
        phase = (ph[-1] + 2 * np.pi * f / SR)
    y = np.concatenate(out) if out else np.zeros(1)
    # piccola dissolvenza a inizio/fine per evitare click
    nf = min(220, y.size // 4)
    if nf > 0:
        y[:nf] *= np.linspace(0, 1, nf)
        y[-nf:] *= np.linspace(1, 0, nf)
    if noise > 0:
        y = y + noise * np.random.randn(y.size)
    return (np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes()


def psk_tx(testo, pitch=1000.0, baud=31.25, ampl=0.6, idle_syms=32, noise=0.0):
    """Genera l'audio BPSK31 (PSK31) per il testo dato. Ritorna PCM 16-bit
    mono (bytes) a 44100 Hz. Preambolo/coda: inversioni continue (idle)."""
    stream = "0" * int(idle_syms)
    for ch in (testo or ""):
        stream += _VARICODE.get(ord(ch), _VARICODE[32]) + "00"
    stream += "0" * int(idle_syms)
    spb = SR / baud
    # fase per simbolo: '0' = inversione (+pi), '1' = invariata
    ph_sym = []
    cur = 0.0
    for b in stream:
        if b == "0":
            cur += np.pi
        ph_sym.append(cur)
    total = int(round(spb * len(ph_sym)))
    out = np.zeros(total)
    for k, ph in enumerate(ph_sym):
        i0 = int(round(k * spb)); i1 = int(round((k + 1) * spb))
        n = i1 - i0
        if n <= 0:
            continue
        t = np.arange(n)
        env = np.ones(n)
        # sagomatura a coseno rialzato: ampiezza va a zero quando c'è inversione
        if k > 0 and abs(ph_sym[k] - ph_sym[k - 1]) > 0.1:
            env = 0.5 * (1 - np.cos(2 * np.pi * (t + 0.5) / n))
        out[i0:i1] = env * np.cos(2 * np.pi * pitch * (i0 + t) / SR + ph)
    y = ampl * out
    if noise > 0:
        y = y + noise * np.random.randn(y.size)
    return (np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes()


# alias interni per gli auto-test
def _gen_rtty(testo, mark=2125.0, shift=170.0, baud=45.45, ampl=0.5, noise=0.0):
    return rtty_tx(testo, mark=mark, shift=shift, baud=baud, ampl=ampl, noise=noise)


def _gen_psk(testo, pitch=1000.0, baud=31.25, ampl=0.5, noise=0.0):
    return psk_tx(testo, pitch=pitch, baud=baud, ampl=ampl, noise=noise)


if __name__ == "__main__":
    # Round-trip TX -> decoder (verifica reciproca)
    print("== RTTY TX->RX ==")
    d = RTTYDecoder(mark=2125.0, shift=170.0)
    out = []
    d.on_text = lambda s: out.append(s)
    d.feed(rtty_tx("CQ CQ DE IW1FZR", noise=0.05))
    print("decodificato:", repr("".join(out)))

    print("== PSK31 TX->RX ==")
    p = PSKDecoder(pitch=1000.0)
    out2 = []
    p.on_text = lambda s: out2.append(s)
    p.feed(psk_tx("CQ DE IW1FZR", noise=0.02))
    print("decodificato:", repr("".join(out2)))
