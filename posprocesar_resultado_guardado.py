# PATH: postprocesar_resultado_guardado.py

import os
import pickle
import tkinter as tk
from tkinter import filedialog

from src.model.results_postprocessing import extraer_solucion
from src.results_gen.generar_diagrama_gantt import generar_diagrama_gantt

def cargar_resultado_pickle():
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="Selecciona archivo .pkl con resultados del solver",
        filetypes=[("Pickle files", "*.pkl")],
        initialdir="archivos/debug/intermedios_solver"
    )
    return path

def postprocesar_desde_pickle(path_pickle, mostrar_gantt=True):
    if not os.path.isfile(path_pickle):
        print(f"❌ Archivo no encontrado: {path_pickle}")
        return

    print(f"\n📂 Cargando archivo: {path_pickle}")
    with open(path_pickle, "rb") as f:
        datos = pickle.load(f)

    # Extraemos componentes necesarios
    solver = datos["solver"]
    status = datos["status"]
    all_vars = datos["all_vars"]
    intervals = datos["intervals"]
    cap_int = datos["capacity_per_interval"]
    df_calend = datos["df_calend"]
    df_entregas = datos["df_entregas"]

    # Procesamos resultados
    print("📊 Postprocesando solución...")
    sol_tareas, timeline, resumen_pedidos = extraer_solucion(
        solver, status, all_vars, intervals, cap_int, df_calend, df_entregas
    )

    print(f"✅ {len(sol_tareas)} tareas procesadas")

    if mostrar_gantt:
        from src.model.data_processing import leer_datos
        ruta_original = datos.get("ruta_excel", "??")
        df_capac = leer_datos(ruta_original)["df_capac"]
        generar_diagrama_gantt(sol_tareas, timeline, df_capac, resumen_pedidos)

if __name__ == "__main__":
    path = cargar_resultado_pickle()
    if path:
        postprocesar_desde_pickle(path)
