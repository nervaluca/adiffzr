# -*- coding: utf-8 -*-
"""
Tavolozza semantica di ADIF FZR — fonte unica dei colori
=========================================================
Un solo posto per i colori dell'interfaccia, organizzati per RUOLO
(non per tinta). Ogni token è una coppia (chiaro, scuro): passandolo
direttamente a CustomTkinter come fg_color/text_color, CTk sceglie da
solo la variante giusta secondo il tema attivo (light/dark).

    import theme as TH
    ctk.CTkButton(parent, text="Inserisci", fg_color=TH.SUCCESS,
                  hover_color=TH.SUCCESS_H)

Per contesti che vogliono un colore SINGOLO (es. grafici matplotlib,
Canvas tkinter, ReportLab) usa i valori *_DARK / *_LIGHT o l'helper
solid(token, scuro=True).

Blu primario · accento ciano. Nessun lime.
"""

# ── Token (chiaro, scuro) ────────────────────────────────────────
BG          = ("#F4F7FB", "#0E1621")   # sfondo app
SURFACE     = ("#FFFFFF", "#16202E")   # pannelli
CARD        = ("#EEF3F9", "#1C2838")   # card / riquadri
LINE        = ("#D5DEE9", "#2A3A4E")   # bordi / separatori

TEXT        = ("#14202E", "#E6EDF5")   # testo primario
TEXT_MUTED  = ("#5B6B7D", "#9FB0C3")   # testo secondario

PRIMARY     = ("#2F6BA6", "#3B82C4")   # azione primaria
PRIMARY_H   = ("#255A8D", "#2F6BA6")   # hover
SECONDARY   = ("#556070", "#4A5568")   # azione secondaria / neutra
SECONDARY_H = ("#454E5C", "#3B4453")
SUCCESS     = ("#2F855A", "#2F9E5E")   # conferma / inserisci
SUCCESS_H   = ("#276749", "#27834D")
DANGER      = ("#C53030", "#D8564C")   # elimina / errore
DANGER_H    = ("#9B2626", "#C0463D")
WARNING     = ("#C05621", "#E0A44A")   # avviso
WARNING_H   = ("#9C4419", "#C98F3B")
ACCENT      = ("#0E7490", "#38BDC9")   # accento (ciano): badge, highlight
ACCENT_H    = ("#0B5E75", "#2FA6B1")

# Colori "di stato" testuali usati spesso inline
OK_TEXT     = ("#2F855A", "#48D392")   # "✓ riconosciuto", LoTW Y
WARN_TEXT   = ("#C05621", "#F6AD55")   # "⚠ verifica"
LINK        = ("#2B6CB0", "#90CDF4")

# ── Accessori a colore singolo (grafici / canvas / PDF) ──────────
def solid(token, scuro=True):
    """Restituisce il colore singolo (str) di un token, variante scura
    (default) o chiara. Per matplotlib/Canvas che non accettano tuple."""
    return token[1] if scuro else token[0]

# Comodità: versioni piatte più usate nei grafici (tema scuro)
BG_DARK      = BG[1]
SURFACE_DARK = SURFACE[1]
CARD_DARK    = CARD[1]
LINE_DARK    = LINE[1]
TEXT_DARK    = TEXT[1]
PRIMARY_DARK = PRIMARY[1]
ACCENT_DARK  = ACCENT[1]
