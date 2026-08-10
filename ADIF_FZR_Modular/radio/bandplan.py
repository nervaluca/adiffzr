import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

def modo_da_bandplan(freq_hz):
    """Deduce il modo operativo dalla frequenza secondo il band plan IARU
    Region 1 (Europa/Africa). Ritorna una stringa modo ('CW','USB','LSB',
    'FT8','RTTY','FM','AM'...) oppure None se fuori dai segmenti noti.

    I segmenti sono espressi in kHz. Per ogni banda si elencano gli
    intervalli (start, end, modo). La sideband SSB segue la convenzione:
    LSB sotto 10 MHz, USB sopra.
    """
    khz = freq_hz / 1000.0

    # Ogni voce: (start_khz, end_khz, modo)
    # Modi: CW, DIGI (digitale generico → FT8/USB-D), RTTY, USB, LSB, FM, AM
    SEGMENTI = [
        # 160m
        (1810, 1838, "CW"), (1838, 1840, "RTTY"), (1840, 1843, "FT8"),
        (1843, 2000, "LSB"),
        # 80m
        (3500, 3570, "CW"), (3570, 3580, "FT8"), (3580, 3600, "RTTY"),
        (3600, 3800, "LSB"),
        # 60m
        (5351, 5354, "CW"), (5354, 5366, "USB"),
        # 40m
        (7000, 7040, "CW"), (7040, 7050, "RTTY"), (7050, 7200, "LSB"),
        (7074, 7078, "FT8"),  # sovrascrive: FT8 dentro il segmento SSB
        # 30m
        (10100, 10130, "CW"), (10130, 10150, "RTTY"), (10136, 10140, "FT8"),
        # 20m
        (14000, 14070, "CW"), (14070, 14099, "RTTY"), (14074, 14078, "FT8"),
        (14099, 14101, "CW"), (14101, 14350, "USB"),
        # 17m
        (18068, 18095, "CW"), (18095, 18109, "RTTY"), (18100, 18104, "FT8"),
        (18109, 18168, "USB"),
        # 15m
        (21000, 21070, "CW"), (21070, 21110, "RTTY"), (21074, 21078, "FT8"),
        (21110, 21450, "USB"),
        # 12m
        (24890, 24915, "CW"), (24915, 24929, "RTTY"), (24915, 24919, "FT8"),
        (24929, 24990, "USB"),
        # 10m
        (28000, 28070, "CW"), (28070, 28190, "RTTY"), (28074, 28078, "FT8"),
        (28190, 28300, "USB"), (28300, 29000, "USB"), (29000, 29700, "FM"),
        # 6m
        (50000, 50100, "CW"), (50100, 50300, "USB"), (50313, 50320, "FT8"),
        (50300, 50400, "USB"), (50400, 52000, "FM"),
        # 2m
        (144000, 144150, "CW"), (144150, 144400, "USB"), (144174, 144180, "FT8"),
        (144400, 145000, "USB"), (145000, 146000, "FM"),
        # 70cm
        (432000, 432100, "CW"), (432100, 432400, "USB"), (432174, 432180, "FT8"),
        (432400, 433000, "USB"), (433000, 435000, "FM"),
    ]

    # Cerca il segmento più specifico: preferisce FT8 se la freq cade
    # in un segmento FT8 stretto, altrimenti prende il segmento generale.
    match_ft8 = None
    match_gen = None
    for start, end, modo in SEGMENTI:
        if start <= khz < end:
            if modo == "FT8":
                match_ft8 = modo
            elif match_gen is None:
                match_gen = modo
    return match_ft8 or match_gen


