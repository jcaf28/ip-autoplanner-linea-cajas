import os
import pandas as pd
from datetime import datetime
import platform
import subprocess

def exportar_resultados_excel(capacidades, tareas, timeline, turnos_ocupacion, output_dir, open_file_location=True):
    os.makedirs(output_dir, exist_ok=True)

    df_tareas = pd.DataFrame(tareas)
    df_timeline = pd.DataFrame(timeline, columns=["tiempo", "ocupacion", "texto"])
    df_turnos = pd.DataFrame(turnos_ocupacion)
    df_capacidades = pd.DataFrame(capacidades)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"solucion_planificada_{timestamp}.xlsx"
    ruta_salida = os.path.join(output_dir, filename)

    with pd.ExcelWriter(ruta_salida, engine="xlsxwriter") as writer:
        df_tareas.to_excel(writer, sheet_name="Tareas", index=False)
        df_timeline.to_excel(writer, sheet_name="Timeline", index=False)
        df_turnos.to_excel(writer, sheet_name="Turnos", index=False)
        df_capacidades.to_excel(writer, sheet_name="Capacidades", index=False)

    print(f"\n📁 Solución exportada a: {ruta_salida}")

    if open_file_location:
        abrir_explorador(output_dir)

def abrir_explorador(path):
    sistema = platform.system()
    try:
        if sistema == "Windows":
            os.startfile(os.path.realpath(path))
        elif sistema == "Darwin":  # macOS
            subprocess.Popen(["open", path])
        else:  # Linux (con entorno gráfico)
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"⚠️ No se pudo abrir la carpeta: {e}")
