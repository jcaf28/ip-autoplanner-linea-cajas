# PATH: src/utils.py

import math
import pandas as pd
from datetime import datetime
from ortools.sat.python import cp_model

# ==================================================
# 1) UTILIDADES DE LECTURA Y CALENDARIO
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
            base_op = rowt["tiempo_operario"]  # en horas
            t_verif = rowt["tiempo_verificado"]
            nmax = int(rowt["num_operarios_max"])

            if tipo == "OPERATIVA":
                # Para tareas operativas, requerimos al menos 1 operario
                tiempo_base = math.ceil(base_op * 60)
                min_op = 1
                max_op = nmax
            elif tipo == "VERIFICADO":
                # Para tareas de verificado, no se necesitan operarios
                tiempo_base = math.ceil(t_verif * 60)
                min_op = 0
                max_op = 0
            else:
                tiempo_base = 0
                min_op = 0
                max_op = 0

            # Ahora agregamos 6 elementos en el tuple
            job_dict[pedido].append((tid, loc, tiempo_base, min_op, max_op, tipo))

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