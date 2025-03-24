#!/usr/bin/env python
# -*- coding: utf-8 -*-

from ortools.sat.python import cp_model
from datetime import datetime, timedelta
import collections
import pandas as pd
import numpy as np
import os

# Importamos las funciones auxiliares que diste
from src.utils import (
    leer_datos,
    check_situacion_inicial,
    comprimir_calendario
)

# Pequeña clase/nametuple para imprimir la asignación final al estilo "job_x_task_y"
from collections import namedtuple
AssignedTask = namedtuple("AssignedTask", ["start", "material", "task_id", "duration"])

def armar_modelo_subintervalos(datos):
    """
    Crea el modelo CP-SAT con sub-intervalos por cada tarea en cada turno,
    usando AddCumulative nativa para respetar la capacidad, y permitiendo retrasos suaves
    en la fecha de entrega.
    """
    model = cp_model.CpModel()

    # Normalizar strings
    datos["df_tareas"]["material_padre"]   = datos["df_tareas"]["material_padre"].astype(str).str.strip()
    datos["df_entregas"]["referencia"]     = datos["df_entregas"]["referencia"].astype(str).str.strip()

    df_calend   = datos["df_calend"]
    df_tareas   = datos["df_tareas"]
    df_entregas = datos["df_entregas"]
    intervals   = datos["intervals"]
    capacity    = datos["capacity_per_interval"]
    fn_comprimir= datos["fn_comprimir"]
    total_m     = datos["total_m"]

    # 1) Creamos variable de retraso p/ cada pedido => end_task <= deadline + retraso
    pedidos = df_entregas["referencia"].unique().tolist()
    retraso = {}
    for p in pedidos:
        retraso[p] = model.NewIntVar(0, 2*total_m, f"retraso_{p}")

    # 2) Calculamos durTask (en minutos) p/ cada tarea
    durTask = {}
    all_tasks = []
    for _, row in df_tareas.iterrows():
        mat  = row["material_padre"]
        t_id = row["id_interno"]
        all_tasks.append((mat, t_id))

    for (mat, t_id) in all_tasks:
        row = df_tareas[(df_tareas["material_padre"]==mat)&(df_tareas["id_interno"]==t_id)].iloc[0]
        pct = row.get("completada_porcentaje",0.0) or 0.0
        if pct>1: pct=1
        t_op    = (row.get("tiempo_operario",0)   or 0)*60*(1-pct)
        t_robot = (row.get("tiempo_robot",0)      or 0)*60*(1-pct)
        t_verif = (row.get("tiempo_verificado",0) or 0)*60*(1-pct)
        dur = max(t_op, t_robot, t_verif)
        durTask[(mat,t_id)] = int(round(dur))

    # 3) Crear sub-intervalos (mat, t_id) X turn i
    pres_sub   = {}
    start_sub  = {}
    dur_sub_   = {}
    end_sub    = {}
    intervals_sub = {}

    n_turnos = len(intervals)
    for (mat, t_id) in all_tasks:
        for i, itv in enumerate(intervals):
            s_i = itv["comp_start"]
            e_i = itv["comp_end"]
            pvar = model.NewBoolVar(f"pres_{mat}_{t_id}_turn{i}")
            svar = model.NewIntVar(s_i, e_i, f"start_{mat}_{t_id}_turn{i}")
            dvar = model.NewIntVar(0, e_i - s_i, f"dur_{mat}_{t_id}_turn{i}")
            evar = model.NewIntVar(s_i, e_i, f"end_{mat}_{t_id}_turn{i}")

            intervalVar = model.NewOptionalIntervalVar(svar, dvar, evar, pvar,
                                                       f"interval_{mat}_{t_id}_turn{i}")

            pres_sub[(mat,t_id,i)]  = pvar
            start_sub[(mat,t_id,i)] = svar
            dur_sub_[(mat,t_id,i)]  = dvar
            end_sub[(mat,t_id,i)]   = evar
            intervals_sub[(mat,t_id,i)] = intervalVar

            # Si no se usa => dur=0
            model.Add(dvar==0).OnlyEnforceIf(pvar.Not())

    # 4) sum(dur_sub) >= durTask
    for (mat, t_id) in all_tasks:
        needed = durTask[(mat,t_id)]
        model.Add(
            sum(dur_sub_[(mat,t_id,i)] for i in range(n_turnos)) >= needed
        )

    # 5) AddCumulative nativa p/ cada turno
    for i, itv in enumerate(intervals):
        cap_i = capacity[i]
        interval_list = []
        demand_list   = []
        for (mat, t_id) in all_tasks:
            row_ = df_tareas[(df_tareas["material_padre"]==mat)&(df_tareas["id_interno"]==t_id)].iloc[0]
            max_ops = int(row_.get("num_operarios_max",1) or 1)
            interval_list.append(intervals_sub[(mat,t_id,i)])
            demand_list.append(max_ops)
        model.AddCumulative(interval_list, demand_list, cap_i)

    # 6) end_task => max end_sub
    end_task = {}
    for (mat,t_id) in all_tasks:
        eT = model.NewIntVar(0, total_m+2000, f"endTask_{mat}_{t_id}")
        for i in range(n_turnos):
            model.Add(eT >= end_sub[(mat,t_id,i)])
        end_task[(mat,t_id)] = eT

    # 7) Fechas de entrega => end_task <= deadline + retraso
    for ref in pedidos:
        dl = df_entregas.loc[df_entregas["referencia"]==ref,"fecha_entrega"].iloc[0]
        dl_m = fn_comprimir(dl)
        df_mat = df_tareas[df_tareas["material_padre"]==ref]
        for _, row_ in df_mat.iterrows():
            t_id = row_["id_interno"]
            mat_ = row_["material_padre"]
            model.Add(end_task[(mat_, t_id)] <= dl_m + retraso[ref])

    # 8) Precedencias => end_task(A) <= start_sub(B,i)
    for _, row_ in df_tareas.iterrows():
        mat_ = row_["material_padre"]
        t_id= row_["id_interno"]
        preds = row_["predecesora"]
        if not pd.isnull(preds):
            preds_ids = [int(x.strip()) for x in str(preds).split(";")]
            for p_id in preds_ids:
                for i in range(n_turnos):
                    model.Add(end_task[(mat_, p_id)] <= start_sub[(mat_, t_id, i)]).OnlyEnforceIf(pres_sub[(mat_, t_id, i)])

    # 9) Tareas parciales => si 0<pct<1 => no iniciar antes de recep
    for _, row_ in df_tareas.iterrows():
        mat_ = row_["material_padre"]
        t_id= row_["id_interno"]
        pct = row_.get("completada_porcentaje",0.0)
        if 0<pct<1:
            fecha_rec = df_entregas.loc[df_entregas["referencia"]==mat_,"fecha_recepcion_materiales"].iloc[0]
            rec_m = fn_comprimir(fecha_rec)
            for i in range(n_turnos):
                model.Add(start_sub[(mat_,t_id,i)] >= rec_m).OnlyEnforceIf(pres_sub[(mat_,t_id,i)])

    # 10) Minimizar la suma de retrasos
    model.Minimize(sum(retraso[p] for p in pedidos))

    return model, intervals_sub, pres_sub, start_sub, dur_sub_, end_sub, end_task, retraso


def main():
    print("1) Leyendo datos...")
    ruta_excel = "archivos/db_dev/Datos_entrada_v10_fechas_relajadas.xlsx"
    datos = leer_datos(ruta_excel)

    print("2) Chequeando situación inicial...")
    check_situacion_inicial(datos["df_tareas"], datos["df_capacidades"], verbose=True)

    print("3) Comprimiendo calendario...")
    intervals, fn_comp, fn_decomp, total_m, capacity = comprimir_calendario(datos["df_calend"])
    datos["intervals"] = intervals
    datos["capacity_per_interval"] = capacity
    datos["fn_comprimir"]   = fn_comp
    datos["fn_descomprimir"] = fn_decomp
    datos["total_m"] = total_m

    print("4) Creando modelo con sub-intervalos + AddCumulative + retraso suave...")
    model, intervals_sub, pres_sub, start_sub, dur_sub_, end_sub, end_task, retraso = armar_modelo_subintervalos(datos)

    print("5) Resolviendo con CP-SAT...")
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    print("   => Estado:", solver.StatusName(status))

    # Si hay solución, la imprimimos al "estilo snippet"
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        print("Solution found:")

        # Construimos una estructura "assigned_tasks" indexada por "turno"
        assigned_tasks_by_turn = collections.defaultdict(list)

        # Recorremos sub-intervalos activos
        for (mat, t_id, i), intervalObj in intervals_sub.items():
            if solver.Value(pres_sub[(mat,t_id,i)]) == 1:
                start = solver.Value(start_sub[(mat,t_id,i)])
                dur = solver.Value(dur_sub_[(mat,t_id,i)])
                if dur>0:
                    # Creamos un AssignedTask con la info
                    assigned = AssignedTask(start=start, material=mat, task_id=t_id, duration=dur)
                    assigned_tasks_by_turn[i].append(assigned)

        # Ordenar y volcar la info
        # ("turno" hace el papel de "Machine" en el snippet)
        output = ""
        for turn_i in sorted(assigned_tasks_by_turn.keys()):
            tasks_list = assigned_tasks_by_turn[turn_i]
            # Orden por start
            tasks_list.sort(key=lambda x: x.start)

            sol_line_tasks = f"Turn {turn_i}: "
            sol_line = "          "

            for atask in tasks_list:
                name = f"{atask.material}_task_{atask.task_id}"
                sol_line_tasks += f"{name:25}"

                start_ = atask.start
                end_   = start_ + atask.duration
                interval_str = f"[{start_},{end_}]"
                sol_line += f"{interval_str:25}"

            sol_line += "\n"
            sol_line_tasks += "\n"
            output += sol_line_tasks + sol_line

        print("Suma de retrasos =", solver.ObjectiveValue())
        print(output)

    else:
        print("No solution found.")

    print("Fin.")

if __name__ == "__main__":
    main()
