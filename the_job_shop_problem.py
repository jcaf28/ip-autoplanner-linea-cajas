# PATH: the_job_shop_problem.py

import math
import pandas as pd
import collections
from ortools.sat.python import cp_model

from src.utils import leer_datos, comprimir_calendario, construir_estructura_tareas
from src.results_gen.entry import mostrar_resultados

def crear_modelo_cp(job_dict,
                    precedences,
                    machine_capacity,
                    intervals,
                    capacity_per_interval):
    model = cp_model.CpModel()
    all_vars = {}
    horizon = 0
    for pedido, tasks in job_dict.items():
        for (_, _, tiempo_base, _, _, _) in tasks:
            horizon += max(1, tiempo_base)
    if horizon < 1:
        horizon = 1

    machine_to_intervals = collections.defaultdict(list)

    for pedido, tasks in job_dict.items():
        for t_idx, (tid, machine_id, tiempo_base, min_op, max_op, tipo) in enumerate(tasks):
            if min_op == max_op == 0:
                # Tarea de verificado: no consume operarios
                x_op = model.NewIntVar(0, 0, f"xop_{pedido}_{tid}")
                duration_var = model.NewConstant(tiempo_base)
            else:
                x_op = model.NewIntVar(min_op, max_op, f"xop_{pedido}_{tid}")
                # Calculamos las duraciones posibles en función de x_op
                # NOTA: si x_op parte de 1, usamos ese valor; si se requiere un ajuste por min_op, habría que desplazar el índice
                dur_x = []
                for x in range(min_op, max_op + 1):
                    if tiempo_base > 0:
                        val = math.ceil(tiempo_base / x)
                    else:
                        val = tiempo_base
                    dur_x.append(val)
                dur_min = min(dur_x) if dur_x else 0
                dur_max = max(dur_x) if dur_x else 0
                duration_var = model.NewIntVar(dur_min, dur_max, f"dur_{pedido}_{tid}")
                # Ajustamos el índice en AddElement: si x_op parte de min_op, se usa (x_op - min_op)
                model.AddElement(x_op - min_op, dur_x, duration_var)

            start_var = model.NewIntVar(0, horizon, f"start_{pedido}_{tid}")
            end_var   = model.NewIntVar(0, horizon, f"end_{pedido}_{tid}")
            interval_var = model.NewIntervalVar(start_var, duration_var, end_var,
                                                f"interval_{pedido}_{tid}")
            all_vars[(pedido, t_idx)] = {
                "start": start_var,
                "end": end_var,
                "interval": interval_var,
                "x_op": x_op,
                "duration": duration_var,
                "machine": machine_id
            }
            machine_to_intervals[machine_id].append((interval_var, 1))  # 1 es la "demanda" de la máquina

    # Precedencias
    for pedido, prec_list in precedences.items():
        for (idxA, idxB) in prec_list:
            model.Add(all_vars[(pedido, idxB)]["start"] >= all_vars[(pedido, idxA)]["end"])

    # Restricción: capacidad en cada máquina
    for mach, interval_list in machine_to_intervals.items():
        ivars = [iv for (iv, d) in interval_list]
        demands = [d for (iv, d) in interval_list]
        cap = machine_capacity.get(mach, 1)
        model.AddCumulative(ivars, demands, cap)

    # ==========================================
    # NUEVO: Restricción por turnos - Operarios
    # ==========================================
    for i, seg in enumerate(intervals):
        cini = seg["comp_start"]
        cfin = seg["comp_end"]
        cap_i = capacity_per_interval[i]

        interval_list = []
        demands = []

        for (pedido, t_idx), varset in all_vars.items():
            xop = varset["x_op"]
            interval_var = varset["interval"]
            st = varset["start"]
            en = varset["end"]

            # Creamos una booleana: la tarea está dentro del intervalo de turno
            ov = model.NewBoolVar(f"op_overlap_{i}_{pedido}_{t_idx}")
            model.Add(st < cfin).OnlyEnforceIf(ov)
            model.Add(en > cini).OnlyEnforceIf(ov)
            b1 = model.NewBoolVar("")
            b2 = model.NewBoolVar("")
            model.Add(st >= cfin).OnlyEnforceIf(b1)
            model.Add(en <= cini).OnlyEnforceIf(b2)
            model.AddBoolOr([b1, b2]).OnlyEnforceIf(ov.Not())

            # Solo añadimos tareas que pueden solaparse
            interval_active = model.NewOptionalIntervalVar(
                varset["start"],
                varset["duration"],
                varset["end"],
                ov,
                f"op_interval_{i}_{pedido}_{t_idx}"
            )

            interval_list.append(interval_active)
            demands.append(xop)

        model.AddCumulative(interval_list, demands, cap_i)

    # Makespan: max de todos los end
    ends = []
    for (pedido, tasks) in job_dict.items():
        for t_idx in range(len(tasks)):
            ends.append(all_vars[(pedido, t_idx)]["end"])
    obj_var = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(obj_var, ends)
    model.Minimize(obj_var)

    return model, all_vars

def resolver_modelo(model):
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    return solver, status

def extraer_solucion(solver, status, all_vars, intervals, capacity_per_interval):
    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        return [], [], []

    sol_tareas = []
    for (pedido, t_idx), varset in all_vars.items():
        st = solver.Value(varset["start"])
        en = solver.Value(varset["end"])
        xop = solver.Value(varset["x_op"])
        dur = solver.Value(varset["duration"])
        sol_tareas.append({
            "pedido": pedido,
            "t_idx": t_idx,
            "start": st,
            "end": en,
            "x_op": xop,
            "duration": dur,
            "machine": varset["machine"]
        })

    sol_tareas.sort(key=lambda x: x["start"])

    # Nuevo timeline detallado
    timeline = construir_timeline_detallado(sol_tareas, intervals, capacity_per_interval)

    return sol_tareas, timeline

def planificar(ruta_excel):
    datos = leer_datos(ruta_excel)
    df_tareas = datos["df_tareas"]
    df_capac = datos["df_capac"]
    df_calend = datos["df_calend"]

    intervals, cap_int = comprimir_calendario(df_calend)
    job_dict, precedences, machine_cap = construir_estructura_tareas(df_tareas, df_capac)

    model, all_vars = crear_modelo_cp(job_dict,
                                      precedences,
                                      machine_cap,
                                      intervals,
                                      cap_int)

    solver, status = resolver_modelo(model)
    sol_tareas, timeline = extraer_solucion(solver, status, all_vars, intervals, cap_int)

    return sol_tareas, timeline, df_capac

def construir_timeline_detallado(tareas, intervals, capacity_per_interval):
    """
    Devuelve una lista de diccionarios, cada uno con:
      t_ini, t_fin, ocupacion, operarios_turno, %ocup
    contemplando cambios simultáneos en ocupación y límites de turnos.
    """

    def turno_idx_de_tiempo(t):
        for i, seg in enumerate(intervals):
            if seg["comp_start"] <= t < seg["comp_end"]:
                return i
        return -1

    # 1) Generar eventos: +x_op en start, -x_op en end
    #    + también añadimos los límites de turnos con delta_op=0
    eventos = []
    for tarea in tareas:
        xop = tarea["x_op"]
        if xop > 0:
            eventos.append((tarea["start"], +xop))
            eventos.append((tarea["end"],   -xop))
    for i, seg in enumerate(intervals):
        eventos.append((seg["comp_start"], 0))
        eventos.append((seg["comp_end"],   0))

    # 2) Ordenar eventos: primero por tiempo, si empatan
    #    primero las entradas (+) y después las salidas (-)
    eventos.sort(key=lambda e: (e[0], -e[1]))

    # 3) Recorremos eventos para crear tramos [tiempo_i, tiempo_(i+1))
    #    y en cada tramo calculamos la ocupación (acumulada) y
    #    partimos dicho tramo según los límites de los turnos.
    timeline = []
    ocupacion_actual = 0

    for i in range(len(eventos) - 1):
        t0, delta_op = eventos[i]
        # Actualizar ocupacion con el evento actual
        ocupacion_actual += delta_op

        t1 = eventos[i + 1][0]
        if t1 > t0:
            # Recorremos este rango [t0, t1) y lo partimos
            # si cruza varios turnos
            t_ini_segmento = t0
            while t_ini_segmento < t1:
                idx_turno = turno_idx_de_tiempo(t_ini_segmento)
                if idx_turno == -1:
                    break  # fuera de todos los turnos

                fin_turno = intervals[idx_turno]["comp_end"]
                t_fin_segmento = min(fin_turno, t1)
                cap_turno = capacity_per_interval[idx_turno]

                if cap_turno > 0:
                    p_ocup = round(100 * ocupacion_actual / cap_turno, 2)
                else:
                    p_ocup = 0

                timeline.append({
                    "t_ini": t_ini_segmento,
                    "t_fin": t_fin_segmento,
                    "ocupacion": ocupacion_actual,
                    "operarios_turno": cap_turno,
                    "%ocup": p_ocup
                })

                t_ini_segmento = t_fin_segmento

    return timeline


if __name__ == "__main__":
    ruta_archivo_base = "archivos/db_dev/Datos_entrada_v10_fechas_relajadas_toy.xlsx"
    output_dir = "archivos/db_dev/output/google-or"

    sol_tareas, timeline, df_capac = planificar(ruta_archivo_base)

    mostrar_resultados(ruta_archivo_base,
                        df_capac,
                        tareas=sol_tareas,
                        timeline=timeline,
                        imprimir=True,
                        exportar=True,
                        output_dir=output_dir,
                        generar_gantt=False,
                        guardar_raw=True,  
                      )