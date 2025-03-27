# PATH: src/data_preprocessing/entry.py

import pandas as pd

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.data_preprocessing.preparar_tareas_por_tiempos_validados import preparar_tareas_por_tiempos_validados
from src.data_preprocessing.generar_calendario_turnos import generar_calendario_formateado

if __name__ == "__main__":
    ruta_excel = "archivos/db_dev/Datos_entrada_v17_autocalendar.xlsx"
    preparar_tareas_por_tiempos_validados(ruta_excel)
    generar_calendario_formateado(ruta_excel)