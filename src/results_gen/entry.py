# PATH: src/service/entry.py

from src.results_gen.exportar_resultados_excel import exportar_resultados_excel
from src.results_gen.generar_diagrama_gantt import generar_diagrama_gantt
from src.results_gen.imprimir_resultados_consola import imprimir_resultados_consola


def mostrar_resultados( tareas,
                        timeline,
                        turnos_ocupacion,
                        imprimir=False,
                        exportar=False,
                        output_dir=None,
                        generar_gantt=False):
    if imprimir:
        imprimir_resultados_consola(tareas, timeline, turnos_ocupacion)

    if exportar and output_dir:
        exportar_resultados_excel(tareas, timeline, turnos_ocupacion, output_dir)

    if generar_gantt:
        generar_diagrama_gantt(tareas)
