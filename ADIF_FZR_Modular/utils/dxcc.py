import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_target_pkg = r'C:\Users\nerva\Desktop\printlog\innosetup3.2\ADIF_FZR_Modular'
if _target_pkg not in sys.path:
    sys.path.insert(0, _target_pkg)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

from config import DXCC_PREFIX_TABLE, _DXCC_PREFIX_LENGTHS

def dxcc_da_nominativo(call):
    """Cerca il nominativo nella tabella prefissi DXCC, provando prima i
    prefissi più lunghi (più specifici, es. 'IS0') e poi quelli più corti
    (es. 'I'). Ignora eventuali suffissi /P /MM /QRP /numero portatile dopo
    lo slash. Ritorna (country, dxcc_code, continente) o None se non trovato."""
    if not call:
        return None
    c = str(call).strip().upper()
    if "/" in c:
        # Per nominativi come IK1ABC/QO-100 o W1AW/3, considera solo la
        # parte prima dello slash per il prefisso (caso più comune); se la
        # parte dopo lo slash è più corta e somiglia a un prefisso country
        # valido da solo (es. F/IK1ABC), si potrebbe estendere in futuro.
        c = c.split("/")[0]
    for length in _DXCC_PREFIX_LENGTHS:
        if len(c) >= length and c[:length] in DXCC_PREFIX_TABLE:
            return DXCC_PREFIX_TABLE[c[:length]]
    return None


