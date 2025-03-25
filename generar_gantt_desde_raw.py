# PATH: generar_gantt_desde_raw.py

import os
import pickle
import sys
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
    turnos_ocupacion = datos.get("turnos_ocupacion", [])

    print(f"   • tareas: {len(tareas)} registros")
    print(f"   • timeline: {len(timeline)} eventos")
    print(f"   • turnos_ocupacion: {len(turnos_ocupacion)} turnos")

    print("\n📊 Generando diagrama de Gantt...\n")
    generar_diagrama_gantt(tareas, timeline, turnos_ocupacion)

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
    if len(sys.argv) > 1:
        path_raw = sys.argv[1]
    else:
        path_raw = buscar_ultimo_pickle_en("archivos/db_dev/output/google-or/raw")

    if path_raw:
        cargar_y_generar_gantt(path_raw)
