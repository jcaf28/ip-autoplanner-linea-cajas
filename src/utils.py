# PATH: src/utils.py

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
    df_capacidades = pd.read_excel(xls, sheet_name="CAPACIDADES")

    df_entregas["fecha_entrega"] = pd.to_datetime(df_entregas["fecha_entrega"], dayfirst=True)
    df_entregas["fecha_recepcion_materiales"] = pd.to_datetime(df_entregas["fecha_recepcion_materiales"], dayfirst=True)
    df_calend["dia"] = pd.to_datetime(df_calend["dia"]).dt.date

    # Rellenar NaN numéricos en df_tareas
    col_num = ["tiempo_operario", "tiempo_verificado", "num_operarios_max"]
    for c in col_num:
        if c in df_tareas.columns:
            df_tareas[c] = df_tareas[c].fillna(0)

    pedidos = df_entregas["referencia"].unique().tolist()
    tareas = df_tareas["id_interno"].unique().tolist()

    datos = {
        "df_entregas": df_entregas,
        "df_calend": df_calend,
        "df_tareas": df_tareas,
        "df_capacidades": df_capacidades,
        "pedidos": pedidos,
        "tareas": tareas
    }
    return datos

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
        capacity_per_interval.append(cap)
        acumulado += dur_min

    def fn_comprimir(dt_real):
        if not intervals:
            return 0
        if dt_real < intervals[0]["dt_inicio"]:
            return 0
        for itv in intervals:
            if itv["dt_inicio"] <= dt_real <= itv["dt_fin"]:
                delta_secs = (dt_real - itv["dt_inicio"]).total_seconds()
                delta_min = int(round(delta_secs / 60.0))
                return itv["comp_start"] + delta_min
            elif dt_real < itv["dt_inicio"]:
                return itv["comp_start"]
        return intervals[-1]["comp_end"]

    def fn_descomprimir(comp_t):
        if not intervals:
            return datetime(2025, 3, 1)
        if comp_t <= intervals[0]["comp_start"]:
            return intervals[0]["dt_inicio"]
        for itv in intervals:
            if itv["comp_start"] <= comp_t <= itv["comp_end"]:
                delta_m = comp_t - itv["comp_start"]
                return itv["dt_inicio"] + timedelta(minutes=delta_m)
        return intervals[-1]["dt_fin"]

    total_m = intervals[-1]["comp_end"] if intervals else 0
    return intervals, fn_comprimir, fn_descomprimir, total_m, capacity_per_interval

def imprimir_solucion(sol, makespan):
    print("=== SOLUCIÓN ===")
    print(f"Makespan: {makespan}")
    for (pedido, t_idx, st, en, m, d) in sol:
        print(f" Tarea de {pedido} idx={t_idx} Maq={m} start={st} end={en} dur={d}")
    print("=== FIN SOLUCIÓN ===")