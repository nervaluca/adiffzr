"""Genera un 'sample' di diploma stilizzato per gli award (immagine PIL).

Design proprietario (pergamena/oro), NON riproduce certificati ufficiali
ARRL/CQ (coperti da copyright). Usato come anteprima in alto a destra nella
finestra award e, su click, salvabile/stampabile a piena pagina.

API principale:
    img = genera_sample_diploma(fullname, subtitle, target, call, scale=1.0)
    -> PIL.Image (RGB). Rapporto ~1.45 (orizzontale).
"""

from PIL import Image, ImageDraw, ImageFont

# Palette pergamena/oro
_CREAM = (246, 239, 221)
_CREAM_EDGE = (216, 201, 160)
_GOLD = (184, 150, 63)
_NAVY = (33, 50, 77)
_MUTED = (107, 93, 62)
_SIGN = (138, 122, 82)

# Font serif: prima quelli tipici di Windows, poi DejaVu (Linux/build).
_SERIF = ["georgia.ttf", "times.ttf", "constan.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "DejaVuSerif.ttf"]
_SERIF_B = ["georgiab.ttf", "timesbd.ttf", "constanb.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "DejaVuSerif-Bold.ttf"]
_SERIF_I = ["georgiai.ttf", "timesi.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
            "DejaVuSerif-Italic.ttf"]


def _font(cands, size):
    for name in cands:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def _tw(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0], b[3] - b[1]


def _fit_font(draw, text, cands, size, max_w):
    """Riduce la dimensione finché il testo sta in max_w (min 60% della size)."""
    s = size
    while s > int(size * 0.6):
        f = _font(cands, s)
        if _tw(draw, text, f)[0] <= max_w:
            return f
        s -= 2
    return _font(cands, s)


def _center(draw, cx, y, text, font, fill, spacing=0):
    if spacing:
        w = sum(_tw(draw, ch, font)[0] + spacing for ch in text) - spacing
        x = cx - w / 2
        for ch in text:
            draw.text((x, y), ch, font=font, fill=fill)
            x += _tw(draw, ch, font)[0] + spacing
    else:
        w = _tw(draw, text, font)[0]
        draw.text((cx - w / 2, y), text, font=font, fill=fill)


def genera_sample_diploma(fullname, subtitle, target, call, scale=1.0,
                          watermark="SAMPLE"):
    """Ritorna una PIL.Image del diploma campione.
    fullname/subtitle/target vengono da AWARD_INFO; call dal profilo."""
    W, H = int(900 * scale), int(620 * scale)
    def s(v): return int(v * scale)

    img = Image.new("RGB", (W, H), _CREAM)
    d = ImageDraw.Draw(img)

    # Cornici
    d.rectangle([s(10), s(10), W - s(10), H - s(10)], outline=_CREAM_EDGE, width=s(2))
    d.rectangle([s(30), s(30), W - s(30), H - s(30)], outline=_GOLD, width=s(3))
    d.rectangle([s(40), s(40), W - s(40), H - s(40)], outline=_GOLD, width=s(1))
    for (cx, cy) in [(s(40), s(40)), (W - s(40), s(40)),
                     (s(40), H - s(40)), (W - s(40), H - s(40))]:
        d.ellipse([cx - s(5), cy - s(5), cx + s(5), cy + s(5)], fill=_GOLD)

    cx = W // 2

    # Filigrana SAMPLE (layer ruotato, semitrasparente)
    if watermark:
        wm = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        wd = ImageDraw.Draw(wm)
        wf = _font(_SERIF_B, s(150))
        ww, wh = _tw(wd, watermark, wf)
        wd.text(((W - ww) / 2, (H - wh) / 2 - s(20)), watermark, font=wf,
                fill=(_GOLD[0], _GOLD[1], _GOLD[2], 28))
        wm = wm.rotate(20, expand=False, resample=Image.BICUBIC)
        img.paste(wm, (0, 0), wm)
        d = ImageDraw.Draw(img)

    # Intestazione
    _center(d, cx, s(58), "ADIF FZR", _font(_SERIF, s(15)), _NAVY, spacing=s(6))
    d.line([cx - s(90), s(86), cx + s(90), s(86)], fill=_GOLD, width=s(1))

    # Titolo award (auto-fit)
    tf = _fit_font(d, fullname, _SERIF_B, s(46), W - s(160))
    _, th = _tw(d, fullname, tf)
    _center(d, cx, s(112), fullname, tf, _NAVY)

    _center(d, cx, s(178), subtitle, _font(_SERIF_I, s(16)), _MUTED)

    _center(d, cx, s(228), "Si certifica che", _font(_SERIF_I, s(17)), _NAVY)
    _center(d, cx, s(262), (call or "—").upper(), _font(_SERIF_B, s(40)), _GOLD,
            spacing=s(2))
    _center(d, cx, s(322), "ha completato i requisiti dell'award qui rappresentato",
            _font(_SERIF, s(15)), _NAVY)

    # Sigillo con il target
    sy = s(410)
    d.ellipse([cx - s(34), sy - s(34), cx + s(34), sy + s(34)], outline=_GOLD, width=s(2))
    d.ellipse([cx - s(27), sy - s(27), cx + s(27), sy + s(27)], outline=_GOLD, width=s(1))
    _center(d, cx, sy - s(16), str(target), _font(_SERIF_B, s(26)), _NAVY)

    # Firme
    d.line([s(140), s(452), s(320), s(452)], fill=_SIGN, width=s(1))
    _center(d, s(230), s(460), "Data", _font(_SERIF, s(13)), _MUTED)
    d.line([W - s(320), s(452), W - s(140), s(452)], fill=_SIGN, width=s(1))
    _center(d, W - s(230), s(460), "Firma", _font(_SERIF, s(13)), _MUTED)

    return img
