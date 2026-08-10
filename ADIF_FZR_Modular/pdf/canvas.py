import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import math
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.colors import Color

class ElegantNumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.stazione_call = ""
        self.dettagli_op = ""
        self.colore_primario = "#1A365D"

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            if self._pageNumber == 1:
                self.disegna_filigrana_mappamondo()
            else:
                self.disegna_decorazioni_footer(num_pages)
            super().showPage()
        super().save()

    def disegna_filigrana_mappamondo(self):
        """Filigrana tech: globo con reticolo, anelli radar, collegamenti DX
        ad arco, punti stazione con onde radio, tacche graduate e crosshair HUD."""
        self.saveState()
        import math
        from reportlab.lib.colors import Color

        def rgba(hex_str, alpha):
            h = hex_str.lstrip('#')
            r, g, b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
            return Color(r, g, b, alpha)

        w, h = self._pagesize
        cx, cy = w / 2, h / 2
        R  = 190          # raggio globo
        c1 = self.colore_primario
        ACC = "#2B6CB0"   # accent

        # ── Anelli radar concentrici esterni ──
        for i, (rr, aa) in enumerate([(R+18, 0.10), (R+38, 0.07), (R+58, 0.05)]):
            self.setStrokeColor(rgba(ACC, aa))
            self.setLineWidth(0.7)
            self.circle(cx, cy, rr, fill=0, stroke=1)

        # ── Tacche graduate ogni 10° sull'anello esterno ──
        self.setStrokeColor(rgba(ACC, 0.18))
        for deg in range(0, 360, 10):
            a = math.radians(deg)
            lungh = 8 if deg % 30 == 0 else 4
            x1 = cx + (R+18) * math.cos(a); y1 = cy + (R+18) * math.sin(a)
            x2 = cx + (R+18-lungh) * math.cos(a); y2 = cy + (R+18-lungh) * math.sin(a)
            self.setLineWidth(1.0 if deg % 30 == 0 else 0.5)
            self.line(x1, y1, x2, y2)

        # ── Crosshair HUD (4 segmenti che puntano al centro) ──
        self.setStrokeColor(rgba(ACC, 0.25))
        self.setLineWidth(1.0)
        gap = R + 6; seg = 14
        for a_deg in (0, 90, 180, 270):
            a = math.radians(a_deg)
            x1 = cx + gap * math.cos(a);        y1 = cy + gap * math.sin(a)
            x2 = cx + (gap+seg) * math.cos(a);  y2 = cy + (gap+seg) * math.sin(a)
            self.line(x1, y1, x2, y2)

        # ── Cerchio oceano ──
        self.setFillColor(rgba("#C8E6FA", 0.25))
        self.setStrokeColor(rgba(c1, 0.22))
        self.setLineWidth(1.2)
        self.circle(cx, cy, R, fill=1, stroke=1)

        # ── Meridiani ──
        self.setStrokeColor(rgba(c1, 0.13))
        self.setLineWidth(0.5)
        for lon_deg in range(-180, 181, 30):
            lon = math.radians(lon_deg)
            punti = []
            for lat_deg in range(-90, 91, 3):
                lat = math.radians(lat_deg)
                if math.cos(lat) * math.cos(lon) >= 0:
                    punti.append((cx + R*math.cos(lat)*math.sin(lon), cy + R*math.sin(lat)))
                else:
                    if punti: self._disegna_polilinea(punti); punti = []
            if punti: self._disegna_polilinea(punti)

        # ── Paralleli ──
        for lat_deg in range(-60, 91, 30):
            lat = math.radians(lat_deg)
            punti = []
            for lon_deg in range(-180, 181, 3):
                lon = math.radians(lon_deg)
                if math.cos(lat) * math.cos(lon) >= 0:
                    punti.append((cx + R*math.cos(lat)*math.sin(lon), cy + R*math.sin(lat)))
                else:
                    if punti: self._disegna_polilinea(punti); punti = []
            if punti: self._disegna_polilinea(punti)

        # ── Equatore evidenziato ──
        self.setStrokeColor(rgba(c1, 0.26))
        self.setLineWidth(0.9)
        punti = []
        for lon_deg in range(-180, 181, 2):
            lon = math.radians(lon_deg)
            if math.cos(lon) >= 0:
                punti.append((cx + R*math.sin(lon), cy))
            else:
                if punti: self._disegna_polilinea(punti); punti = []
        if punti: self._disegna_polilinea(punti)

        # ── Continenti ──
        continenti = {
            "EU": [(35,-10),(35,30),(60,30),(70,25),(71,28),(70,20),(65,15),(58,5),(51,2),(43,-9),(36,-10),(35,-10)],
            "NA": [(15,-85),(20,-105),(30,-115),(49,-125),(60,-140),(70,-140),(72,-95),(72,-75),(60,-65),(47,-55),(43,-65),(25,-80),(15,-85)],
            "SA": [(-5,-80),(10,-75),(12,-72),(10,-62),(5,-52),(-5,-35),(-20,-40),(-35,-58),(-55,-68),(-55,-72),(-40,-72),(-20,-70),(-5,-80)],
            "AF": [(37,10),(37,37),(12,42),(0,42),(-10,40),(-35,27),(-35,18),(-20,12),(-5,8),(5,2),(5,-5),(15,-17),(30,-13),(37,10)],
            "AS": [(70,30),(70,100),(55,160),(35,140),(22,120),(10,105),(1,104),(5,95),(20,90),(22,70),(10,77),(25,57),(35,37),(40,37),(42,45),(60,60),(70,60),(70,30)],
            "OC": [(-15,130),(-15,145),(-25,153),(-38,147),(-38,140),(-30,115),(-22,114),(-15,130)],
        }
        self.setFillColor(rgba(c1, 0.18))
        for ponti in continenti.values():
            coords = []
            for lat_d, lon_d in ponti:
                lat, lon = math.radians(lat_d), math.radians(lon_d)
                if math.cos(lat)*math.cos(lon) >= -0.05:
                    coords.append((cx + R*math.cos(lat)*math.sin(lon), cy + R*math.sin(lat)))
            if len(coords) >= 3:
                p = self.beginPath()
                p.moveTo(*coords[0])
                for pt in coords[1:]: p.lineTo(*pt)
                p.close()
                self.drawPath(p, fill=1, stroke=0)

        # ── Punti stazione + collegamenti DX ad arco ──
        def proietta(lat_d, lon_d):
            lat, lon = math.radians(lat_d), math.radians(lon_d)
            if math.cos(lat)*math.cos(lon) < 0:
                return None
            return (cx + R*math.cos(lat)*math.sin(lon), cy + R*math.sin(lat))

        stazioni = [(45, 8), (40, -74), (-34, -58), (35, 139), (-26, 28), (51, 0)]
        proiettate = [p for p in (proietta(la, lo) for la, lo in stazioni) if p]

        # Archi DX (quadratic bezier "gonfiati" verso l'esterno)
        self.setStrokeColor(rgba(ACC, 0.30))
        self.setLineWidth(0.8)
        coppie = [(0,1),(0,3),(0,4),(1,2),(0,5)]
        for i, j in coppie:
            if i < len(proiettate) and j < len(proiettate):
                x1, y1 = proiettate[i]; x2, y2 = proiettate[j]
                mx, my = (x1+x2)/2, (y1+y2)/2
                # Solleva il punto medio radialmente dal centro
                dx, dy = mx - cx, my - cy
                dist = max(math.hypot(dx, dy), 1)
                lift = 40
                cpx = mx + dx/dist * lift
                cpy = my + dy/dist * lift
                p = self.beginPath()
                p.moveTo(x1, y1)
                p.curveTo(cpx, cpy, cpx, cpy, x2, y2)
                self.drawPath(p, fill=0, stroke=1)

        # Punti stazione con onde concentriche
        for (px, py) in proiettate:
            self.setFillColor(rgba(ACC, 0.55))
            self.circle(px, py, 2.4, fill=1, stroke=0)
            self.setLineWidth(0.5)
            for rr, aa in ((5, 0.30), (8, 0.16)):
                self.setStrokeColor(rgba(ACC, aa))
                self.circle(px, py, rr, fill=0, stroke=1)

        # ── Bordo globo finale ──
        self.setStrokeColor(rgba(c1, 0.30))
        self.setLineWidth(1.8)
        self.circle(cx, cy, R, fill=0, stroke=1)

        self.restoreState()


    def _disegna_polilinea(self, punti):
        if len(punti) < 2:
            return
        p = self.beginPath()
        p.moveTo(*punti[0])
        for pt in punti[1:]:
            p.lineTo(*pt)
        self.drawPath(p, fill=0, stroke=1)

    def disegna_decorazioni_footer(self, page_count):
        self.saveState()
        self.setFont('Helvetica', 9)
        self.setFillColor(colors.HexColor("#718096"))
        self.setStrokeColor(colors.lightgrey)
        self.setLineWidth(0.5)
        self.line(25, 35, self._pagesize[0] - 25, 35)
        testo_sinistra = "Registro Log Radio"
        if self.stazione_call:
            testo_sinistra = f"Stazione: {self.stazione_call}"
            if self.dettagli_op:
                testo_sinistra += f" - {self.dettagli_op}"
        elif self.dettagli_op:
            testo_sinistra = self.dettagli_op
        self.drawString(25, 20, testo_sinistra)
        self.drawRightString(self._pagesize[0] - 25, 20, f"Pagina {self._pageNumber} di {page_count}")
        self.restoreState()


# ─────────────────────────────────────────────
#  Calendar Popup (no external dependencies)
# ─────────────────────────────────────────────
import calendar as _cal

