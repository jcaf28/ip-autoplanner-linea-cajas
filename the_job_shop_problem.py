# ==================================================
# Archivo único: planificacion_cajas.py
# ==================================================

import math
import pandas as pd
import collections
from ortools.sat.python import cp_model
from datetime import datetime, timedelta

# ==================================================
# 1) LECTURA DE DATOS Y COMPRIMIR CALENDARIO
# ==================================================

def leer_datos(ruta_excel):
    xls = pd.ExcelFile(ruta_excel)
    df_entregas = pd.read_excel(xls, sheet_name="ENTREGAS")
    df_calend   = pd.read_excel(xls, sheet_name="CALENDARIO")
    df_tareas   = pd.read_excel(xls, sheet_name="TAREAS")
    df_capac    = pd.read_excel(xls, sheet_name="CAPACIDADES")

    df_entregas["fecha_entrega"] = pd.to_datetime(df_entregas["fecha_entrega"], dayfirst=True)
    df_entregas["fecha_recepcion_materiales"] = pd.to_datetime(df_entregas["fecha_recepcion_materiales"], dayfirst=True)
    df_calend["dia"] = pd.to_datetime(df_calend["dia"]).dt.date

    # Rellenar NaN numéricos en df_tareas
    for c in ["tiempo_operario", "tiempo_verificado", "num_operarios_max"]:
        if c in df_tareas.columns:
            df_tareas[c] = df_tareas[c].fillna(0)

    return {
        "df_entregas": df_entregas,
        "df_calend": df_calend,
        "df_tareas": df_tareas,
        "df_capac": df_capac
    }

def comprimir_calendario(df_calend):
    df_calend = df_calend.copy()
    df_calend = df_calend.sort_values(by=["dia", "hora_inicio"])
    intervals = []
    capacity_per_interval = []
    acumulado = 0

    for _, row in df_calend.iterrows():
        dia = row["dia"]
        hi = row["hora_inicio"]
        hf = row["hora_fin"]
        cap = row["cant_operarios"]

        if isinstance(hi, str):
            hi = datetime.strptime(hi, "%H:%M:%S").time()
        if isinstance(hf, str):
            hf = datetime.strptime(hf, "%H:%M:%S").time()

        dt_ini = datetime(dia.year, dia.month, dia.day, hi.hour, hi.minute, hi.second)
        dt_fin = datetime(dia.year, dia.month, dia.day, hf.hour, hf.minute, hf.second)
        dur_secs = (dt_fin - dt_ini).total_seconds()
        dur_min = int(round(dur_secs / 60.0))
        if dur_min <= 0:
            continue

        comp_start = acumulado
        comp_end = acumulado + dur_min
        intervals.append({
            "dt_inicio": dt_ini,
            "dt_fin": dt_fin,
            "comp_start": comp_start,
            "comp_end": comp_end
        })
        capacity_per_interval.append(int(cap))
        acumulado += dur_min

    return intervals, capacity_per_interval

# ==================================================
# 2) ESTRUCTURA DE TAREAS Y PRECEDENCIAS
# ==================================================

def construir_estructura_tareas(df_tareas, df_capac):
    machine_capacity = {}
    for _, rowc in df_capac.iterrows():
        ub = int(rowc["ubicación"])
        machine_capacity[ub] = int(rowc["capacidad"])

    job_dict = {}
    precedences = {}
    df_tareas = df_tareas.sort_values(by=["material_padre", "id_interno"])

    for pedido, grupo in df_tareas.groupby("material_padre"):
        job_dict[pedido] = []
        precedences[pedido] = []

        lista_tareas = list(grupo["id_interno"])
        for _, rowt in grupo.iterrows():
            tid = rowt["id_interno"]
            loc = int(rowt["ubicación"])
            tipo = str(rowt["tipo_tarea"])
            base_op = rowt["tiempo_operario"]  # en horas o lo que corresponda
            t_verif = rowt["tiempo_verificado"]
            nmax = int(rowt["num_operarios_max"])

            # Usaremos "tiempo_base" solo para OPERATIVA
            # Para VERIFICADO (o cualquier otra) aquí un ejemplo simplificado.
            # Lo normal es que verificado no necesite 'x_t' operarios. Ajusta según tu caso real.
            if tipo == "OPERATIVA":
                # Convertimos a minutos
                tiempo_base = math.ceil(base_op * 60)
            elif tipo == "VERIFICADO":
                # Supongamos verificado no cambia con #operarios, forzamos x_t=1 y dur fijo
                tiempo_base = math.ceil(t_verif * 60)
                nmax = 1
            else:
                tiempo_base = 0
                nmax = 1

            job_dict[pedido].append((tid, loc, tiempo_base, nmax, tipo))

        for _, rowt in grupo.iterrows():
            current_id = rowt["id_interno"]
            preds_str = rowt["predecesora"]
            if pd.isna(preds_str) or preds_str == "":
                continue
            for p in str(preds_str).split(";"):
                p = p.strip()
                if p:
                    idxA = lista_tareas.index(int(p))
                    idxB = lista_tareas.index(int(current_id))
                    precedences[pedido].append((idxA, idxB))

    return job_dict, precedences, machine_capacity

# ==================================================
# 3) CREACIÓN DEL MODELO CP-SAT
# ==================================================

def crear_modelo_cp(job_dict,
                    precedences,
                    machine_capacity,
                    intervals,
                    capacity_per_interval):
    model = cp_model.CpModel()
    all_vars = {}
    # Estructura:
    # all_vars[(pedido, t_idx)] = {
    #    "start": start_var,
    #    "end": end_var,
    #    "interval": interval_var,
    #    "x_op": x_t,  (n operarios asignados)
    #    "duration": duration_var,
    #    "machine": machine_id
    # }

    horizon = 0
    for pedido, tasks in job_dict.items():
        for (_, _, tiempo_base, _, _) in tasks:
            horizon += max(1, tiempo_base)

    if horizon < 1:
        horizon = 1

    machine_to_intervals = collections.defaultdict(list)

    for pedido, tasks in job_dict.items():
        for t_idx, (tid, machine_id, tiempo_base, nmax, tipo) in enumerate(tasks):
            # Definimos la variable x_op en [1..nmax]
            x_op = model.NewIntVar(1, nmax, f"xop_{pedido}_{tid}")

            # Calculamos las duraciones posibles en función de x_op
            # dur_x[x - 1] = ceil(tiempo_base / x)
            dur_x = []
            for x in range(1, nmax+1):
                if tiempo_base > 0:
                    val = math.ceil(tiempo_base / x)
                else:
                    val = tiempo_base
                dur_x.append(val)

            # Definimos la variable de duración real
            dur_min = min(dur_x) if dur_x else 0
            dur_max = max(dur_x) if dur_x else 0
            duration_var = model.NewIntVar(dur_min, dur_max, f"dur_{pedido}_{tid}")

            # Vinculamos duration_var a x_op mediante constraint AddElement
            # AddElement(index, array, target)
            # index = x_op - 1 (porque x_op va de 1..nmax)
            # array = dur_x
            # target = duration_var
            model.AddElement(x_op - 1, dur_x, duration_var)

            # Definimos start, end e interval
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

    # Restricción: capacidad global de operarios por intervalo
    # Para cada segmento i, sum(x_t) de las tareas que solapan no excede capacity_per_interval[i]
    occupied_operators = []
    for i, seg in enumerate(intervals):
        cini = seg["comp_start"]
        cfin = seg["comp_end"]
        cap_i = capacity_per_interval[i]
        occ_var = model.NewIntVar(0, cap_i, f"occupied_{i}")
        occupied_operators.append(occ_var)

        # Creamos una lista para x_op de las tareas que se solapan con el segmento i
        # Pero en CP-SAT necesitamos reificar "tarea t solapa con i" -> booleana "overlap_i_t"
        overlap_sum = []
        for (pedido, t_idx), varset in all_vars.items():
            st = varset["start"]
            en = varset["end"]
            xop = varset["x_op"]

            # overlap_i_t = 1 => la tarea se solapa con [cini, cfin)
            ov = model.NewBoolVar(f"ov_{i}_{pedido}_{t_idx}")
            # Si ov=1 => (st < cfin) AND (en > cini)
            model.Add(st < cfin).OnlyEnforceIf(ov)
            model.Add(en > cini).OnlyEnforceIf(ov)
            # Si ov=0 => st >= cfin OR en <= cini
            b1 = model.NewBoolVar("")
            b2 = model.NewBoolVar("")
            model.Add(st >= cfin).OnlyEnforceIf(b1)
            model.Add(en <= cini).OnlyEnforceIf(b2)
            model.AddBoolOr([b1, b2]).OnlyEnforceIf(ov.Not())

            # Queremos "overlap_i_t * x_op" en la suma.
            # CP-SAT no multiplica directamente bool * intvar, lo hacemos con:
            #   z = model.NewIntVar(0, cap_i, "")
            #   z >= x_op - (1 - ov)*M  (M grande)
            #   z <= x_op
            #   z <= ov*M
            # Este "z" será x_op si ov=1, o 0 si ov=0.
            z = model.NewIntVar(0, cap_i, f"z_{i}_{pedido}_{t_idx}")
            bigM = cap_i + 10  # un número que sea >= x_op máximo
            model.Add(z >= xop - (1 - ov)*bigM)
            model.Add(z <= xop)
            model.Add(z <= ov*bigM)
            overlap_sum.append(z)

        # Sum de overlap_sum = occ_var
        model.Add(occ_var == sum(overlap_sum))
        # Y occ_var <= capacidad del intervalo i
        model.Add(occ_var <= cap_i)

    # Makespan: max de todos los end
    ends = []
    for (pedido, tasks) in job_dict.items():
        for t_idx in range(len(tasks)):
            ends.append(all_vars[(pedido, t_idx)]["end"])
    obj_var = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(obj_var, ends)
    model.Minimize(obj_var)

    return model, all_vars, occupied_operators

# ==================================================
# 4) RESOLUCIÓN Y SALIDA
# ==================================================

def resolver_modelo(model):
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    return solver, status

def extraer_solucion(solver, status, all_vars, intervals, occupied_operators):
    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        return [], []

    # Tareas
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

    # Ocupación de operarios en cada intervalo
    sol_intervals = []
    for i, seg in enumerate(intervals):
        occ_val = solver.Value(occupied_operators[i])
        real_ini = seg["comp_start"]
        real_fin = seg["comp_end"]
        sol_intervals.append({
            "interval_id": i,
            "comp_start": real_ini,
            "comp_end": real_fin,
            "operarios_ocupados": occ_val
        })

    return sol_tareas, sol_intervals

def imprimir_solucion(tareas, intervals):
    if not tareas:
        print("No hay solución factible.")
        return
    makespan = max(x["end"] for x in tareas)
    print(f"\nSOLUCIÓN Factible - Makespan = {makespan}")
    for t in tareas:
        print(f"Pedido={t['pedido']} t_idx={t['t_idx']}, Maq={t['machine']}, "
              f"start={t['start']}, end={t['end']}, x_op={t['x_op']} (dur={t['duration']})")

    print("\nDetalle ocupación de operarios por intervalo comprimido:")
    for iv in intervals:
        print(f" Interval {iv['interval_id']} [{iv['comp_start']},{iv['comp_end']}): "
              f"{iv['operarios_ocupados']} operarios simultáneos")

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

    model, all_vars, occupied_ops = crear_modelo_cp(job_dict,
                                                    precedences,
                                                    machine_cap,
                                                    intervals,
                                                    cap_int)

    solver, status = resolver_modelo(model)
    sol_tareas, sol_intervals = extraer_solucion(solver, status, all_vars, intervals, occupied_ops)

    imprimir_solucion(sol_tareas, sol_intervals)
    return sol_tareas, sol_intervals

# ==================================================
# EJEMPLO DE USO
# ==================================================
if __name__ == "__main__":
    ruta = "archivos/db_dev/Datos_entrada_v10_fechas_relajadas_toy.xlsx"
    planificar(ruta)
