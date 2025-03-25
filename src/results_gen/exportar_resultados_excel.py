# PATH: src/service/exportar_resultados_excel.py

import os
import pandas as pd

def exportar_resultados_excel(tareas, timeline, turnos_ocupacion, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    df_tareas = pd.DataFrame(tareas)
    df_timeline = pd.DataFrame(timeline, columns=["tiempo", "ocupacion", "texto"])
    df_turnos = pd.DataFrame(turnos_ocupacion)

    ruta_salida = os.path.join(output_dir, "solucion_planificada.xlsx")
    with pd.ExcelWriter(ruta_salida, engine="xlsxwriter") as writer:
        df_tareas.to_excel(writer, sheet_name="Tareas", index=False)
        df_timeline.to_excel(writer, sheet_name="Timeline", index=False)
        df_turnos.to_excel(writer, sheet_name="Turnos", index=False)

    print(f"\n📁 Solución exportada a: {ruta_salida}")