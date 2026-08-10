import os
import sys

# Ensure package modules can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk
from config import _tema_iniziale
from gui.main_window import ADIFtoPDFApp

if __name__ == '__main__':
    app = ADIFtoPDFApp()
    app.mainloop()
