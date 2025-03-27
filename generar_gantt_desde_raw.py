# PATH: generar_gantt_desde_raw.py

import os
import pickle
import tkinter as tk
from tkinter import filedialog

from src.results_gen.generar_diagrama_gantt import generar_diagrama_gantt

def cargar_y_generar_gantt(path_raw):
    if not os.path.isfile(path_raw):
        print(f"❌ No se encontró el archivo: {path_raw}")
        return

    print(f"\n📂 Cargando resultados desde: {path_raw}")
    with open(path_raw, "rb") as f:
        datos = pickle.load(f)

    tareas = datos.get("tareas", [])
    timeline = datos.get("timeline", [])
    capacidades = datos.get("capacidades", [])
    resumen_pedidos = datos.get("resumen_pedidos", None)

    print(f"   • tareas: {len(tareas)} registros")
    print(f"   • timeline: {len(timeline)} eventos")
    print(f"   • capacidades: {len(capacidades)} ubicaciones")

    print("\n📊 Generando diagrama de Gantt...\n")
    generar_diagrama_gantt(tareas, timeline, capacidades, resumen_pedidos)

def buscar_ultimo_pickle_en(directorio):
    if not os.path.isdir(directorio):
        print(f"❌ Directorio no encontrado: {directorio}")
        return None

    archivos = [f for f in os.listdir(directorio) if f.endswith(".pkl")]
    if not archivos:
        print(f"⚠️ No se encontraron archivos .pkl en {directorio}")
        return None

    archivos.sort(key=lambda f: os.path.getmtime(os.path.join(directorio, f)), reverse=True)
    return os.path.join(directorio, archivos[0])

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    path_raw = filedialog.askopenfilename(
        title="Selecciona el archivo .pkl",
        filetypes=[("Pickle files", "*.pkl")],
        initialdir="archivos/db_dev/output/google-or/raw"
    )

    if path_raw:
        cargar_y_generar_gantt(path_raw)
