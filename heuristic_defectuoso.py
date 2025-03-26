# PATH: heuristic_defectuoso.py

from src.utils import leer_datos, comprimir_calendario, construir_estructura_tareas, comprimir_tiempo, descomprimir_tiempo, construir_timeline_detallado
from src.results_gen.entry import mostrar_resultados

def planificar_heuristico(ruta_excel, debug=False):

    datos = leer_datos(ruta_excel)
    df_tareas   = datos["df_tareas"]
    df_capac    = datos["df_capac"]
    df_calend   = datos["df_calend"]
    df_entregas = datos["df_entregas"]

    intervals, cap_int = comprimir_calendario(df_calend)
    job_dict, precedences, machine_cap = construir_estructura_tareas(df_tareas, df_capac)

    tareas_pendientes = []
    for pedido, tareas in job_dict.items():
        entrega = df_entregas.loc[df_entregas["referencia"] == pedido, "fecha_entrega"].values[0]
        for idx, (tid, machine_id, tiempo_base, min_op, max_op, tipo) in enumerate(tareas):
            tareas_pendientes.append({
                "pedido": pedido,
                "t_idx": idx,
                "tid": tid,
                "machine": machine_id,
                "duracion": tiempo_base,
                "min_op": min_op,
                "max_op": max_op,
                "tipo": tipo,
                "fecha_entrega": entrega
            })

    tareas_pendientes.sort(key=lambda x: x["fecha_entrega"])

    calendario_maquina = {mach: 0 for mach in machine_cap}
    calendario_operarios = [cap for cap in cap_int]

    solucion = []

    for tarea in tareas_pendientes:
        mach = tarea["machine"]
        duracion = tarea["duracion"]
        max_op = tarea["max_op"]

        tiempo_ini = calendario_maquina[mach]

        while duracion > 0:
            for i, intervalo in enumerate(intervals):
                if intervalo["comp_end"] <= tiempo_ini:
                    continue

                capacidad_disponible = calendario_operarios[i]
                if capacidad_disponible == 0:
                    continue

                operarios_asignados = min(max_op, capacidad_disponible)
                duracion_bloque = min(duracion, intervalo["comp_end"] - tiempo_ini)

                solucion.append({
                    "pedido": tarea["pedido"],
                    "t_idx": tarea["t_idx"],
                    "start": tiempo_ini,
                    "end": tiempo_ini + duracion_bloque,
                    "x_op": operarios_asignados,
                    "duration": duracion_bloque,
                    "machine": mach,
                    "timestamp_ini": descomprimir_tiempo(tiempo_ini, df_calend),
                    "timestamp_fin": descomprimir_tiempo(tiempo_ini + duracion_bloque, df_calend)
                })

                calendario_operarios[i] -= operarios_asignados
                duracion -= duracion_bloque
                tiempo_ini += duracion_bloque

                if duracion == 0:
                    break

        calendario_maquina[mach] = tiempo_ini

    timeline = construir_timeline_detallado(solucion, intervals, cap_int)

    for tramo in timeline:
        tramo["timestamp_ini"] = descomprimir_tiempo(tramo["t_ini"], df_calend, modo="ini")
        tramo["timestamp_fin"] = descomprimir_tiempo(tramo["t_fin"], df_calend, modo="fin")

    return solucion, timeline, df_capac


# Ejemplo de uso
if __name__ == "__main__":
    ruta_archivo_base = "archivos/db_dev/Datos_entrada_v15_fechas_relajadas.xlsx"
    output_dir = "archivos/db_dev/output/heuristico"

    sol_tareas, timeline, df_capac = planificar_heuristico(ruta_archivo_base, debug=True)

    mostrar_resultados(ruta_archivo_base,
                        df_capac,
                        tareas=sol_tareas,
                        timeline=timeline,
                        imprimir=True,
                        exportar=True,
                        output_dir=output_dir,
                        generar_gantt=False,
                        guardar_raw=True)