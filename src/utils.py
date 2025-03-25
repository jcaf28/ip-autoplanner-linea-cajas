# PATH: src/utils.py

import math
import pandas as pd
from datetime import datetime, timedelta

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