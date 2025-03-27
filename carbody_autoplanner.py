# PATH: carbody_autoplanner.py

from src.model.solver import planificar_linea_produccion
from src.results_gen.entry import mostrar_resultados

if __name__ == "__main__":
    ruta_archivo_base = "archivos/db_dev/Datos_entrada_v16_fechas_relajadas_tiempos_reales.xlsx"
    output_dir = "archivos/db_dev/output/google-or"

    modo_debug = True

    sol_tareas, timeline, df_capac = planificar_linea_produccion(ruta_archivo_base, modo_debug)

    mostrar_resultados(ruta_archivo_base,
                        df_capac,
                        tareas=sol_tareas,
                        timeline=timeline,
                        imprimir=False,
                        exportar=True,
                        output_dir=output_dir,
                        generar_gantt=False,
                        guardar_raw=True)