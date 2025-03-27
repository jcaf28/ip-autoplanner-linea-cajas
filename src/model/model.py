# PATH: src/model/model.py

from ortools.sat.python import cp_model
import collections
import math
import pandas as pd

from src.model.time_management import comprimir_tiempo

def crear_modelo_cp(job_dict,
                    precedences,
                    machine_capacity,
                    intervals,
                    capacity_per_interval,
                    df_entregas,   
                    df_calend):    

    model = cp_model.CpModel()
    all_vars = {}
    horizon = 0
    for pedido, tasks in job_dict.items():
        for (_, _, tiempo_base, _, _, _) in tasks:
            horizon += max(1, tiempo_base)
    if horizon < 1:
        horizon = 1

    machine_to_intervals = collections.defaultdict(list)

    # Preparamos acceso rápido a fechas de entrega y recepción
    ent_dict = {}
    for _, row in df_entregas.iterrows():
        ref = str(row["referencia"])
        ent_dict[ref] = {
            "fecha_recepcion": row["fecha_recepcion_materiales"],
            "fecha_entrega":   row["fecha_entrega"]
        }

    for pedido, tasks in job_dict.items():
        for t_idx, (tid, machine_id, tiempo_base, min_op, max_op, tipo) in enumerate(tasks):
            if min_op == max_op == 0:
                x_op = model.NewIntVar(0, 0, f"xop_{pedido}_{tid}")
                duration_var = model.NewConstant(tiempo_base)
            else:
                x_op = model.NewIntVar(min_op, max_op, f"xop_{pedido}_{tid}")
                dur_x = []
                for x in range(min_op, max_op + 1):
                    val = math.ceil(tiempo_base / x) if tiempo_base > 0 else 0
                    dur_x.append(val)
                dur_min = min(dur_x)
                dur_max = max(dur_x)
                duration_var = model.NewIntVar(dur_min, dur_max, f"dur_{pedido}_{tid}")
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
            machine_to_intervals[machine_id].append((interval_var, 1))

    # Precedencias
    for pedido, prec_list in precedences.items():
        for (idxA, idxB) in prec_list:
            model.Add(all_vars[(pedido, idxB)]["start"] >= all_vars[(pedido, idxA)]["end"])

    # Capacidad de máquinas
    for mach, interval_list in machine_to_intervals.items():
        ivars = [iv for (iv, d) in interval_list]
        demands = [d for (iv, d) in interval_list]
        cap = machine_capacity.get(mach, 1)
        model.AddCumulative(ivars, demands, cap)

    # Capacidad por turnos (operarios)
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

            ov = model.NewBoolVar(f"op_overlap_{i}_{pedido}_{t_idx}")
            model.Add(st < cfin).OnlyEnforceIf(ov)
            model.Add(en > cini).OnlyEnforceIf(ov)
            b1 = model.NewBoolVar("")
            b2 = model.NewBoolVar("")
            model.Add(st >= cfin).OnlyEnforceIf(b1)
            model.Add(en <= cini).OnlyEnforceIf(b2)
            model.AddBoolOr([b1, b2]).OnlyEnforceIf(ov.Not())

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

    # RESTRICCIÓN: No iniciar tareas sin predecesoras antes de recibir materiales
    for pedido, tasks in job_dict.items():
        fecha_recep = ent_dict[pedido]["fecha_recepcion"]
        recep_min = comprimir_tiempo(fecha_recep, df_calend)

        precs_pedido = precedences.get(pedido, [])
        indices_con_predecesor = set(idxB for (idxA, idxB) in precs_pedido)
        for t_idx in range(len(tasks)):
            if t_idx not in indices_con_predecesor:
                st_var = all_vars[(pedido, t_idx)]["start"]
                model.Add(st_var >= recep_min)

    # PENALIZACIÓN POR RETRASO DE ENTREGA (ponderada)
    tardiness_vars = []
    all_ends = []

    pesos = {}
    fecha_min = pd.Timestamp(df_calend["dia"].min())  # <--- AQUÍ EL CAMBIO
    for pedido in df_entregas["referencia"]:
        fecha = ent_dict[pedido]["fecha_entrega"]
        dias_restantes = (fecha - fecha_min).days
        pesos[pedido] = max(1, 1000 - dias_restantes)

    for pedido, tasks in job_dict.items():
        precs_pedido = precedences.get(pedido, [])
        indices_con_sucesor = set(idxA for (idxA, idxB) in precs_pedido)
        indices_finales = [i for i in range(len(tasks)) if i not in indices_con_sucesor]
        if not indices_finales:
            indices_finales = list(range(len(tasks)))

        ends_pedido = [all_vars[(pedido, i)]["end"] for i in indices_finales]
        pedido_end_var = model.NewIntVar(0, horizon, f"end_pedido_{pedido}")
        model.AddMaxEquality(pedido_end_var, ends_pedido)

        all_ends += ends_pedido

        due_date = ent_dict[pedido]["fecha_entrega"]
        due_min = comprimir_tiempo(due_date, df_calend)

        tardiness = model.NewIntVar(0, 10_000_000, f"tardiness_{pedido}")
        model.Add(tardiness >= pedido_end_var - due_min)

        weighted = model.NewIntVar(0, 100_000_000, f"weighted_tardiness_{pedido}")
        model.AddMultiplicationEquality(weighted, [tardiness, pesos[pedido]])
        tardiness_vars.append(weighted)

    sum_tardiness = model.NewIntVar(0, 1_000_000_000, "sum_tardiness")
    model.Add(sum_tardiness == cp_model.LinearExpr.Sum(tardiness_vars))

    # Makespan (opcional, como criterio secundario)
    makespan = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(makespan, all_ends)

    # Función objetivo combinada
    model.Minimize(10 * sum_tardiness + makespan)

    return model, all_vars

