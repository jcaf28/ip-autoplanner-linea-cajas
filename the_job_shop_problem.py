# ==================================================
# Archivo único: planificacion_cajas.py
# ==================================================

import math
import pandas as pd
import collections
from ortools.sat.python import cp_model

from src.utils import (comprimir_calendario,
                      imprimir_solucion, 
                      leer_datos)


# ==================================================
# 2) CONSTRUCCIÓN DE ESTRUCTURAS PARA EL MODELO
# ==================================================

def construir_estructura_tareas(df_tareas, df_capac):
    """
    Devuelve:
      - job_dict: { pedido: [ (task_id, machine_id, duration), ... ] }
      - precedences: { pedido: [ (taskA_idx, taskB_idx), ... ] }  # B depende de A
      - machine_capacity: { machine_id: capacidad }
      - task_index_map: dict auxiliar para indexar las tareas por pedido
    """
    # Mapa de capacidad de cada máquina (ubicación)
    machine_capacity = {}
    for _, rowc in df_capac.iterrows():
        ub = int(rowc["ubicación"])
        machine_capacity[ub] = int(rowc["capacidad"])

    # Ordenamos las tareas por "material_padre" (equivale a pedido)
    job_dict = {}
    precedences = {}
    task_index_map = {}

    df_tareas = df_tareas.sort_values(by=["material_padre", "id_interno"])
    for pedido, grupo in df_tareas.groupby("material_padre"):
        job_dict[pedido] = []
        precedences[pedido] = []
        # Construimos una lista interna para indexar tareas
        # y poder luego mapear id_interno -> índice
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

        # Ahora procesamos precedencias
        for _, rowt in grupo.iterrows():
            current_id = rowt["id_interno"]
            preds_str = rowt["predecesora"]
            if pd.isna(preds_str) or preds_str == "":
                continue
            # Caso multiple: "9;10"
            parts = str(preds_str).split(";")
            for pstr in parts:
                p = pstr.strip()
                if p == "":
                    continue
                p = int(p)
                # task_index en la lista
                idxA = lista_tareas.index(p)
                idxB = lista_tareas.index(current_id)
                precedences[pedido].append((idxA, idxB))

    return job_dict, precedences, machine_capacity, task_index_map

# ==================================================
# 3) CREACIÓN DEL MODELO CP-SAT
# ==================================================

def crear_modelo_cp(job_dict, precedences, machine_capacity):
    """
    job_dict: { pedido: [ (id_interno, machine_id, duration), ... ] }
    precedences: { pedido: [ (idxA, idxB), ... ] }
    machine_capacity: { machine_id: cap }
    Devuelve:
      - model (CpModel)
      - all_tasks: dict  (pedido, task_idx) -> (start, end, interval, machine, duration)
    """
    model = cp_model.CpModel()
    all_tasks = {}
    # Calculamos un horizonte simple como la suma total de duraciones
    horizon = 0
    for pedido, tasks in job_dict.items():
        for (_, _, dur) in tasks:
            horizon += dur
    if horizon == 0:
        horizon = 1

    # Creamos una lista de intervals y demands para cada máquina
    # machine_to_intervals[machine_id] = [(interval_var, demand=1), ...]
    machine_to_intervals = collections.defaultdict(list)

    for pedido, tasks in job_dict.items():
        for t_idx, (t_internal, mach, dur) in enumerate(tasks):
            start_var = model.NewIntVar(0, horizon, f"start_{pedido}_{t_internal}")
            end_var = model.NewIntVar(0, horizon, f"end_{pedido}_{t_internal}")
            interval_var = model.NewIntervalVar(start_var, dur, end_var, f"interval_{pedido}_{t_internal}")
            all_tasks[(pedido, t_idx)] = (start_var, end_var, interval_var, mach, dur)
            machine_to_intervals[mach].append((interval_var, 1))

    # Restringimos precedencias
    for pedido, list_precs in precedences.items():
        for (idxA, idxB) in list_precs:
            startB = all_tasks[(pedido, idxB)][0]
            endA = all_tasks[(pedido, idxA)][1]
            model.Add(startB >= endA)

    # Para cada máquina, añadimos constraint Cumulative(capacidad)
    for mach, interval_list in machine_to_intervals.items():
        intervals_vars = []
        demands = []
        for (itv, d) in interval_list:
            intervals_vars.append(itv)
            demands.append(d)
        cap = machine_capacity.get(mach, 1)
        model.AddCumulative(intervals_vars, demands, cap)

    # Definimos el makespan: la variable a minimizar
    obj_var = model.NewIntVar(0, horizon, "makespan")
    ends = []
    for pedido, tasks in job_dict.items():
        # El "end" de la última tarea de un pedido se busca sabiendo cuál es la de mayor end
        # (pues pueden tener convergencias)
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
        print("No se encontró solución (status={}).".format(status))
    return solver, status

def extraer_solucion(solver, status, all_tasks):
    """
    Retorna una lista con (pedido, task_index, start, end, machine, dur)
    para cada tarea, ordenada por start.
    """
    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        return []
    sol = []
    for (pedido, t_idx), (s, e, itv, m, d) in all_tasks.items():
        st = solver.Value(s)
        en = solver.Value(e)
        sol.append((pedido, t_idx, st, en, m, d))
    sol.sort(key=lambda x: x[2])  # Orden por start
    return sol

def construir_asignacion_turnos(sol, intervals, fn_descomprimir):
    """
    Dado el listado sol (en tiempo comprimido),
    generamos algo "turno a turno y máquina a máquina" en tiempo real aproximado.
    """
    turnos_resultado = []
    for idx, itv in enumerate(intervals):
        cini = itv["comp_start"]
        cfin = itv["comp_end"]
        real_ini = itv["dt_inicio"].strftime("%Y-%m-%d %H:%M")
        real_fin = itv["dt_fin"].strftime("%Y-%m-%d %H:%M")
        # Buscamos tareas que tengan al menos algo de solapamiento
        # con [cini, cfin)
        tareas_en_turno = []
        for (pedido, t_i, st, en, m, d) in sol:
            if en > cini and st < cfin:
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

    # 5.1) Comprimimos calendario (solo para mostrar turnos al final)
    intervals, fn_c, fn_d, total_m, cap_int = comprimir_calendario(datos["df_calend"])

    # 5.2) Construimos estructura de tareas y precedencias
    job_dict, precedences, machine_cap, _ = construir_estructura_tareas(df_tareas, df_capac)

    # 5.3) Creamos y resolvemos modelo
    model, all_tasks = crear_modelo_cp(job_dict, precedences, machine_cap)
    solver, status = resolver_modelo(model, all_tasks)

    # 5.4) Extraemos solución y la mostramos
    sol = extraer_solucion(solver, status, all_tasks)
    makespan = 0
    if sol:
        makespan = max(t[3] for t in sol)  # end máximo
    imprimir_solucion(sol, makespan)

    # 5.5) Preparamos un "turno a turno" para ver qué se hace
    turnos_resultado = construir_asignacion_turnos(sol, intervals, fn_d)
    print("=== Resumen Turno a Turno (tiempo real) ===")
    for tdata in turnos_resultado:
        turno_idx = tdata["turno_idx"]
        horario = tdata["horario_real"]
        tareas = tdata["tareas"]
        if not tareas:
            continue
        print(f" Turno {turno_idx} ({horario}):")
        for (ped, tx, st, en, m) in tareas:
            print(f"   - {ped}, tarea_idx={tx}, Maq={m}, "
                  f"startC={st}, endC={en} (comprimido)")

    return sol

# ==================================================
# EJEMPLO DE USO
# ==================================================
if __name__ == "__main__":
    # Cambia 'mi_archivo.xlsx' por la ruta real a tus datos
    ruta = "archivos/db_dev/Datos_entrada_v10_fechas_relajadas_toy.xlsx"
    planificar(ruta)
