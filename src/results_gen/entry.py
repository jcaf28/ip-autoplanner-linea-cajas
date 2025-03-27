# PATH: src/results_gen/entry.py

from src.results_gen.exportar_resultados_excel import exportar_resultados_excel
from src.results_gen.generar_diagrama_gantt import generar_diagrama_gantt
from src.results_gen.imprimir_resultados_consola import imprimir_resultados_consola
from src.results_gen.guardar_resultados_raw import guardar_resultados_raw 


def mostrar_resultados( ruta_archivo_base,
                        df_capac,
                        tareas,
                        timeline,
                        resumen_pedidos=None,
                        imprimir=False,
                        exportar=False,
                        output_dir=None,
                        generar_gantt=False,
                        guardar_raw=False):
    if imprimir:
        imprimir_resultados_consola(tareas, timeline)

    if exportar and output_dir:
        exportar_resultados_excel(df_capac, tareas, timeline, resumen_pedidos, output_dir, open_file_location=False)

    if generar_gantt:
        generar_diagrama_gantt(tareas, timeline, df_capac)

    if guardar_raw and output_dir:
        guardar_resultados_raw(df_capac, tareas, timeline, resumen_pedidos, output_dir, ruta_archivo_base)

