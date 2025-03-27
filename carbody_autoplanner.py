# PATH: carbody_autoplanner.py

from src.model.solver import planificar_linea_produccion
from src.results_gen.entry import mostrar_resultados

import os
import sys
from tkinter import Tk, filedialog

def seleccionar_archivo_excel():
    Tk().withdraw()
    ruta = filedialog.askopenfilename(
        title="Selecciona archivo Excel de entrada",
        filetypes=[("Archivos Excel", "*.xlsx *.xls")]
    )
    return ruta

if __name__ == "__main__":
    ruta_archivo_base = seleccionar_archivo_excel()

    if not ruta_archivo_base:
        print("❌ No se seleccionó ningún archivo. Saliendo...")
        sys.exit(1)

    output_dir = os.path.join(os.path.dirname(ruta_archivo_base), "output", "google-or")
    modo_debug = True

    sol_tareas, timeline, df_capac, resumen_pedidos = planificar_linea_produccion(ruta_archivo_base, modo_debug)

    mostrar_resultados(
        ruta_archivo_base,
        df_capac,
        tareas=sol_tareas,
        timeline=timeline,
        resumen_pedidos=resumen_pedidos,
        imprimir=False,
        exportar=True,
        output_dir=output_dir,
        generar_gantt=False,
        guardar_raw=True
    )
