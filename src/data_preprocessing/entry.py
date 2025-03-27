# PATH: src/data_preprocessing/entry.py

import pandas as pd
import sys
import os
from tkinter import Tk, filedialog

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.data_preprocessing.preparar_tareas_por_tiempos_validados import preparar_tareas_por_tiempos_validados
from src.data_preprocessing.generar_calendario_turnos import generar_calendario_formateado

def seleccionar_archivo_excel():
    Tk().withdraw()  # Oculta la ventana principal de tkinter
    ruta = filedialog.askopenfilename(
        title="Selecciona archivo Excel de entrada",
        filetypes=[("Archivos Excel", "*.xlsx *.xls")])
    return ruta

if __name__ == "__main__":
    ruta_excel = seleccionar_archivo_excel()

    if not ruta_excel:
        print("❌ No se seleccionó ningún archivo. Saliendo...")
        sys.exit(1)

    preparar_tareas_por_tiempos_validados(ruta_excel)
    generar_calendario_formateado(ruta_excel)
