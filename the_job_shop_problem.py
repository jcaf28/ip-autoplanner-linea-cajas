# ==================================================
# Archivo único: planificacion_cajas.py
# ==================================================

import math
import pandas as pd
import collections
from ortools.sat.python import cp_model

from src.utils import (
    comprimir_calendario,
    imprimir_solucion,
    leer_datos
)

# ==================================================
# 2) CONSTRUCCIÓN DE ESTRUCTURAS PARA EL MODELO
# ==================================================

def construir_estructura_tareas(df_tareas, df_capac):
    machine_capacity = {}
    for _, rowc in df_capac.iterrows():
        ub = int(rowc["ubicación"])
        machine_capacity[ub] = int(rowc["capacidad"])

    job_dict = {}
    precedences = {}
    task_index_map = {}

    df_tareas = df_tareas.sort_values(by=["material_padre", "id_interno"])
    for pedido, grupo in df_tareas.groupby("material_padre"):
        job_dict[pedido] = []
        precedences[pedido] = []
        lista_tareas = list(grupo["id_interno"])
        task_index_map[pedido] = lista_tareas

        for _, rowt in grupo.iterrows():
            tid = rowt["id_interno"]
            loc = int(rowt["ubicación"])
            tarea_tipo = rowt["tipo_tarea"]
            t_oper = rowt["tiempo_operario"]
            t_verif = rowt["tiempo_verificado"]
            if tarea_tipo == "OPERATIVA":
                dur = math.ceil(t_oper * 60)
            elif tarea_tipo == "VERIFICADO":
                dur = math.ceil(t_verif * 60)
            else:
                dur = 0
            job_dict[pedido].append((tid, loc, dur))

        for _, rowt in grupo.iterrows():
            current_id = rowt["id_interno"]
            preds_str = rowt["predecesora"]
            if pd.isna(preds_str) or preds_str == "":
                continue
            parts = str(preds_str).split(";")
            for pstr in parts:
                p = pstr.strip()
                if p == "":
                    continue
                p = int(p)
                idxA = lista_tareas.index(p)
                idxB = lista_tareas.index(current_id)
                precedences[pedido].append((idxA, idxB))

    return job_dict, precedences, machine_capacity, task_index_map


# ==================================================
# 3) CREACIÓN DEL MODELO CP-SAT
# ==================================================

def aplicar_recurso_global_operarios(model,
                                     all_tasks,
                                     intervals,
                                     capacity_per_interval):
    """
    Añade una restricción global de 'operarios' por turno/segmento:
    - intervals: lista de diccionarios con comp_start, comp_end
    - capacity_per_interval: lista con la capacidad de operarios en cada segmento
    - all_tasks: (pedido, t_idx) -> (start, end, interval_var, machine, dur)
    Creamos overlap[i, (pedido,t_idx)] = bool que indica si la tarea se solapa
    con el segmento i. Sum(overlap) <= capacity_i.
    """

    # "horizon" para usarlo en big-M (si hiciera falta).
    # Realmente no es esencial si usamos reificación pura con OnlyEnforceIf.
    horizon = 0
    for (start_var, end_var, _, _, dur) in all_tasks.values():
        horizon += dur

    for i, seg in enumerate(intervals):
        cini = seg["comp_start"]
        cfin = seg["comp_end"]
        cap = capacity_per_interval[i]
        if cfin <= cini:
            continue

        # Lista de booleans de solapamiento
        overlaps_segment = []
        for (pedido, t_idx), (start_var, end_var, _, _, _) in all_tasks.items():
            # Creamos variable booleana
            ov = model.NewBoolVar(f"overlap_{i}_{pedido}_{t_idx}")
            overlaps_segment.append(ov)

            # Restricciones:
            # 1) Si ov=1 => la tarea se solapa con [cini, cfin).
            #    => start_var < cfin AND end_var > cini
            model.Add(start_var < cfin).OnlyEnforceIf(ov)
            model.Add(end_var > cini).OnlyEnforceIf(ov)

            # 2) Si ov=0 => no hay solape => start_var >= cfin OR end_var <= cini
            #    Esto se hace con un "OR" reificado: (st >= cfin) or (en <= cini).
            #    Creamos dos sub-booleans para st>=cfin y en<=cini
            b1 = model.NewBoolVar("")
            b2 = model.NewBoolVar("")
            # st >= cfin => b1=1
            model.Add(start_var >= cfin).OnlyEnforceIf(b1)
            # en <= cini => b2=1
            model.Add(end_var <= cini).OnlyEnforceIf(b2)
            # overlap=0 => b1 OR b2
            model.AddBoolOr([b1, b2]).OnlyEnforceIf(ov.Not())

        # Finalmente, sum(overlaps_segment) <= cap
        model.Add(sum(overlaps_segment) <= cap)


def crear_modelo_cp(job_dict,
                    precedences,
                    machine_capacity,
                    intervals,
                    capacity_per_interval):
    model = cp_model.CpModel()
    all_tasks = {}
    horizon = 0
    for pedido, tasks in job_dict.items():
        for (_, _, dur) in tasks:
            horizon += dur
    if horizon <= 0:
        horizon = 1

    # Intervals por máquina
    machine_to_intervals = collections.defaultdict(list)

    for pedido, tasks in job_dict.items():
        for t_idx, (t_internal, mach, dur) in enumerate(tasks):
            start_var = model.NewIntVar(0, horizon, f"start_{pedido}_{t_internal}")
            end_var   = model.NewIntVar(0, horizon, f"end_{pedido}_{t_internal}")
            interval_var = model.NewIntervalVar(start_var, dur, end_var,
                                                f"interval_{pedido}_{t_internal}")
            all_tasks[(pedido, t_idx)] = (start_var, end_var, interval_var, mach, dur)
            machine_to_intervals[mach].append((interval_var, 1))

    # Precedencias
    for pedido, list_precs in precedences.items():
        for (idxA, idxB) in list_precs:
            startB = all_tasks[(pedido, idxB)][0]
            endA   = all_tasks[(pedido, idxA)][1]
            model.Add(startB >= endA)

    # Restricción capacity en cada máquina
    for mach, interval_list in machine_to_intervals.items():
        model.AddCumulative(
            [itv for (itv, _) in interval_list],
            [d for (_, d) in interval_list],
            machine_capacity.get(mach, 1)
        )

    # **AÑADIMOS** la restricción global de operarios por turno
    aplicar_recurso_global_operarios(model,
                                     all_tasks,
                                     intervals,
                                     capacity_per_interval)

    # Makespan: max de todos los 'end'
    obj_var = model.NewIntVar(0, horizon, "makespan")
    ends = []
    for pedido, tasks in job_dict.items():
        for t_idx in range(len(tasks)):
            ends.append(all_tasks[(pedido, t_idx)][1])
    model.AddMaxEquality(obj_var, ends)
    model.Minimize(obj_var)

    return model, all_tasks


# ==================================================
# 4) RESOLUCIÓN Y GENERACIÓN DE RESULTADO
# ==================================================

def resolver_modelo(model, all_tasks):
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        print(f"No se encontró solución factible (status={status}).")
    return solver, status


def extraer_solucion(solver, status, all_tasks):
    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        return []
    sol = []
    for (pedido, t_idx), (s, e, itv, m, d) in all_tasks.items():
        st = solver.Value(s)
        en = solver.Value(e)
        sol.append((pedido, t_idx, st, en, m, d))
    sol.sort(key=lambda x: x[2])  # Orden por instante de inicio
    return sol


def construir_asignacion_turnos(sol, intervals, fn_descomprimir):
    turnos_resultado = []
    for idx, itv in enumerate(intervals):
        cini = itv["comp_start"]
        cfin = itv["comp_end"]
        real_ini = itv["dt_inicio"].strftime("%Y-%m-%d %H:%M")
        real_fin = itv["dt_fin"].strftime("%Y-%m-%d %H:%M")
        tareas_en_turno = []
        for (pedido, t_i, st, en, m, d) in sol:
            if (en > cini) and (st < cfin):
                tareas_en_turno.append((pedido, t_i, st, en, m))
        turnos_resultado.append({
            "turno_idx": idx+1,
            "horario_real": f"{real_ini} - {real_fin}",
            "tareas": tareas_en_turno
        })
    return turnos_resultado


# ==================================================
# 5) FUNCIÓN PRINCIPAL DE PLANIFICACIÓN
# ==================================================

def planificar(ruta_excel):
    datos = leer_datos(ruta_excel)
    df_tareas = datos["df_tareas"]
    df_capac = datos["df_capacidades"]
    df_calend = datos["df_calend"]

    # (1) Comprimir calendario
    intervals, fn_c, fn_d, total_m, cap_int = comprimir_calendario(df_calend)

    # (2) Construir estructuras
    job_dict, precedences, machine_cap, _ = construir_estructura_tareas(df_tareas,
                                                                        df_capac)

    # (3) Crear y resolver modelo (ahora con restr. global de operarios)
    model, all_tasks = crear_modelo_cp(job_dict,
                                       precedences,
                                       machine_cap,
                                       intervals,
                                       cap_int)
    solver, status = resolver_modelo(model, all_tasks)

    # (4) Extraer solución e imprimir
    sol = extraer_solucion(solver, status, all_tasks)
    makespan = max([x[3] for x in sol], default=0)
    imprimir_solucion(sol, makespan)

    # (5) Resumen “turno a turno”
    turnos_resultado = construir_asignacion_turnos(sol, intervals, fn_d)
    print("=== Resumen Turno a Turno (tiempo real) ===")
    for tdata in turnos_resultado:
        if not tdata["tareas"]:
            continue
        print(f" Turno {tdata['turno_idx']} ({tdata['horario_real']}):")
        for (ped, tx, st, en, m) in tdata["tareas"]:
            print(f"   - {ped}, tarea_idx={tx}, Maq={m}, startC={st}, endC={en}")

    return sol


# ==================================================
# EJEMPLO DE USO
# ==================================================
if __name__ == "__main__":
    # Cambia la ruta a tu archivo Excel real.
    ruta = "archivos/db_dev/Datos_entrada_v10_fechas_relajadas_toy.xlsx"
    planificar(ruta)
