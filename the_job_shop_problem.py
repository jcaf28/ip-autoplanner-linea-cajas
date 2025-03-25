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

def calcular_ocupacion_turnos(tareas, intervals, capacity_per_interval):
    # Esta función devolverá:
    # 1) timeline: lista de (tiempo, ocupacion_acum, 'X/Y')
    # 2) turnos: intervals enriquecido con ocupacion_media (%)

    # Primero creamos los eventos
    eventos = calcular_eventos_tareas(tareas)
    if not eventos:
        # Si no hay tareas con operarios, retornamos ocupación 0% en cada turno
        out_turnos = []
        for i, seg in enumerate(intervals):
            cap_i = capacity_per_interval[i]
            out_turnos.append({
                "turno_id": i,
                "comp_start": seg["comp_start"],
                "comp_end": seg["comp_end"],
                "capacidad": cap_i,
                "ocupacion_media_%": 0
            })
        return [], out_turnos

    # Timeline de cambios
    timeline = []
    ocupacion_actual = 0
    tiempo_anterior = eventos[0][0]

    # Para acumular ocupacion * tiempo en cada turno
    # "uso_turno[i]" será la suma de (ocupacion * delta_tiempo) dentro del turno i
    # "dur_turno[i]" será la duración total en minutos de ese turno i
    uso_turno = [0]*len(intervals)
    for i, seg in enumerate(intervals):
        dur = seg["comp_end"] - seg["comp_start"]
        uso_turno[i] = 0
    # El puntero 'i_turno' lo usaremos para buscar qué turno corresponde a un cierto tiempo
    # aunque veremos que a veces los eventos cruzan un turno parcial y hay que "partir" tiempos

    def turno_de_tiempo(t):
        # Devuelve el índice de turno en el que cae el tiempo 't', o -1 si está fuera de rango
        for i, seg in enumerate(intervals):
            if seg["comp_start"] <= t < seg["comp_end"]:
                return i
        return -1

    idx_actual = turno_de_tiempo(tiempo_anterior)

    for (tiempo_evento, delta_op) in eventos:
        if tiempo_evento > tiempo_anterior:
            # Del tiempo_anterior al tiempo_evento, la ocupacion_actual se mantiene fija
            # Repartimos este tramo entre tantos turnos como se crucen
            t_restante = tiempo_evento
            while idx_actual != -1 and tiempo_anterior < t_restante:
                fin_turno = intervals[idx_actual]["comp_end"]
                tramo_fin = min(fin_turno, t_restante)
                delta_t = tramo_fin - tiempo_anterior
                if delta_t > 0:
                    uso_turno[idx_actual] += (ocupacion_actual * delta_t)
                    tiempo_anterior = tramo_fin
                if tiempo_anterior >= fin_turno:
                    idx_actual += 1
                    if idx_actual >= len(intervals):
                        idx_actual = -1
                else:
                    break

        # Ajustamos la ocupación actual tras el evento
        ocupacion_actual += delta_op
        tiempo_anterior = tiempo_evento

        # Guardamos el evento en timeline
        idx_evt = turno_de_tiempo(tiempo_evento)
        cap_evt = 0 if idx_evt == -1 else capacity_per_interval[idx_evt]
        texto_cap = f"{ocupacion_actual}/{cap_evt}" if cap_evt > 0 else f"{ocupacion_actual}/-"
        timeline.append((tiempo_evento, ocupacion_actual, texto_cap))

        # Aseguramos que el índice actual de turno se actualice
        idx_actual = idx_evt

    # Si queda tiempo al final que no tuvo más eventos, se podría acumular en el turno correspondiente
    # (ej: si la última tarea termina antes de que finalice su turno).
    # Pero solemos no necesitarlo, salvo que quieras ver la ocupación "hasta final de turnos".

    # Ahora calculamos la ocupación media en cada turno
    # uso_turno[i] son "operarios * minutos" acumulados
    # la capacidad total es capacity_per_interval[i]
    # la duración total del turno es intervals[i]["comp_end"] - intervals[i]["comp_start"]
    out_turnos = []
    for i, seg in enumerate(intervals):
        dur = seg["comp_end"] - seg["comp_start"]
        cap_i = capacity_per_interval[i]
        if dur > 0 and cap_i > 0:
            # Promedio de ocupación real = (uso_turno[i]/dur) / cap_i
            # en porcentaje => *100
            ocupacion_media = (uso_turno[i] / dur) / cap_i
        else:
            ocupacion_media = 0
        out_turnos.append({
            "turno_id": i,
            "comp_start": seg["comp_start"],
            "comp_end": seg["comp_end"],
            "capacidad": cap_i,
            "ocupacion_media_%": round(100*ocupacion_media, 2)
        })

    return timeline, out_turnos

def calcular_eventos_tareas(tareas):
    eventos = []
    for t in tareas:
        xop = t["x_op"]
        if xop > 0:
            eventos.append((t["start"], +xop))  # Evento de inicio: + xop
            eventos.append((t["end"], -xop))   # Evento de fin:    - xop
    eventos.sort(key=lambda x: x[0])
    return eventos

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

    # Ordenamos las tareas por tiempo de inicio
    sol_tareas.sort(key=lambda x: x["start"])

    # Construimos la línea de eventos y la ocupación de turnos
    timeline, turnos_ocupacion = calcular_ocupacion_turnos(sol_tareas, intervals, capacity_per_interval)

    return sol_tareas, timeline, turnos_ocupacion

# ==================================================
# 5) FUNCIÓN PRINCIPAL
# ==================================================

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
    sol_tareas, timeline, turnos_ocupacion = extraer_solucion(solver, status, all_vars, intervals, cap_int)

    return sol_tareas, timeline, turnos_ocupacion

# ==================================================
# EJEMPLO DE USO
# ==================================================

if __name__ == "__main__":
    ruta = "archivos/db_dev/Datos_entrada_v10_fechas_relajadas_toy.xlsx"
    output_dir = "archivos/db_dev/output/google-or"

    sol_tareas, timeline, turnos_ocupacion = planificar(ruta)

    mostrar_resultados(
        tareas=sol_tareas,
        timeline=timeline,
        turnos_ocupacion=turnos_ocupacion,
        imprimir=True,
        exportar=False,
        output_dir=output_dir,
        generar_gantt=True
    )



    

