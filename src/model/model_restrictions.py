# PATH: src/model/model_restrictions.py

from ortools.sat.python import cp_model

from src.model.time_management import comprimir_tiempo

def add_precedences(model, all_vars, precedences):
    """
    each (idxA, idxB) => startB >= endA
    """
    for pedido, prec_list in precedences.items():
        for (idxA, idxB) in prec_list:
            model.Add(all_vars[(pedido, idxB)]["start"] >= all_vars[(pedido, idxA)]["end"])

def add_machine_capacity(model, machine_to_intervals, machine_capacity):
    """
    AddCumulative para cada máquina con su capacity
    """
    for mach, interval_list in machine_to_intervals.items():
        ivars = [iv for (iv, d) in interval_list]
        demands = [d for (iv, d) in interval_list]
        cap = machine_capacity.get(mach, 1)
        model.AddCumulative(ivars, demands, cap)

def add_operarios_capacity(model, all_vars, intervals, capacity_per_interval):
    """
    Suma la capacity por intervalo segun df_calend (comp_start, comp_end)
    y se hace un OptionalIntervalVar para cada overlapping con x_op.
    """
    for i, seg in enumerate(intervals):
        cini = seg["comp_start"]
        cfin = seg["comp_end"]
        cap_i = capacity_per_interval[i]

        interval_list = []
        demands = []

        for (pedido, t_idx), varset in all_vars.items():
            xop = varset["x_op"]
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

def add_material_reception_limits(model, all_vars, job_dict, precedences, df_calend, ent_dict):
    """
    No iniciar las tareas sin predecesoras antes de la fecha_recepcion_materiales
    """
    for pedido, tasks in job_dict.items():
        fecha_recep = ent_dict[pedido]["fecha_recepcion"]
        recep_min = comprimir_tiempo(fecha_recep, df_calend)

        precs_pedido = precedences.get(pedido, [])
        indices_con_predecesor = set(idxB for (idxA, idxB) in precs_pedido)

        for t_idx in range(len(tasks)):
            if t_idx not in indices_con_predecesor:
                st_var = all_vars[(pedido, t_idx)]["start"]
                model.Add(st_var >= recep_min)

def add_no_solapamiento_distinto_tipo(model, all_vars, job_dict):
    """
    Restringir que en la misma machine_id no haya tareas de distinto tipo superpuestas.
    disyuntiva: start_i >= end_j OR start_j >= end_i
    """
    import collections

    machine_tasks = collections.defaultdict(list)
    for pedido, tasks in job_dict.items():
        for t_idx, (tid, machine_id, _, _, _, tipo) in enumerate(tasks):
            machine_tasks[machine_id].append((pedido, t_idx, tipo))

    for m_id, lista in machine_tasks.items():
        n = len(lista)
        for i in range(n):
            ped_i, idx_i, tipo_i = lista[i]
            s_i = all_vars[(ped_i, idx_i)]["start"]
            e_i = all_vars[(ped_i, idx_i)]["end"]
            for j in range(i+1, n):
                ped_j, idx_j, tipo_j = lista[j]
                if tipo_i != tipo_j:
                    s_j = all_vars[(ped_j, idx_j)]["start"]
                    e_j = all_vars[(ped_j, idx_j)]["end"]

                    b1 = model.NewBoolVar("")
                    b2 = model.NewBoolVar("")
                    model.Add(s_i >= e_j).OnlyEnforceIf(b1)
                    model.Add(s_j >= e_i).OnlyEnforceIf(b2)
                    model.AddBoolOr([b1, b2])

def add_objective_tardiness_makespan(model, all_vars, job_dict, precedences, df_calend, ent_dict, horizon):
    """
    Minimizar 10 * sum_tardiness + makespan
    """
    tardiness_vars = []
    all_ends = []

    import pandas as pd
    fecha_min = pd.Timestamp(df_calend["dia"].min())

    pesos = {}
    for ref, val in ent_dict.items():
        dias_restantes = (val["fecha_entrega"] - fecha_min).days
        pesos[ref] = max(1, 1000 - dias_restantes)

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

    makespan = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(makespan, all_ends)

    model.Minimize(10 * sum_tardiness + makespan)
