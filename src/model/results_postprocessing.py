# PATH: src/model/results_postprocessing.py

import pandas as pd
from ortools.sat.python import cp_model
import datetime
from src.model.time_management import ( descomprimir_tiempo, 
                                        construir_timeline_detallado, 
                                        calcular_dias_laborables,
                                        calcular_promedio_horas_laborables_por_dia)

def extraer_solucion( solver, 
                      status, 
                      all_vars, 
                      intervals, 
                      capacity_per_interval, 
                      df_calend,
                      df_entregas):
    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        print("⚠️ No se encontró solución factible u óptima")
        return [], [], None

    sol_tareas = []
    for (pedido, t_idx), varset in all_vars.items():
        st  = solver.Value(varset["start"])
        en  = solver.Value(varset["end"])
        xop = solver.Value(varset["x_op"])
        dur = solver.Value(varset["duration"])
        ts_ini = descomprimir_tiempo(st, df_calend, modo="ini")
        ts_fin = descomprimir_tiempo(en, df_calend, modo="fin")

        sol_tareas.append({
            "pedido": pedido,
            "t_idx": t_idx,
            "start": st,
            "end": en,
            "x_op": xop,
            "duration": dur,
            "machine": varset["machine"],
            "timestamp_ini": ts_ini,
            "timestamp_fin": ts_fin
        })

    sol_tareas.sort(key=lambda x: x["start"])

    timeline = construir_timeline_detallado(sol_tareas, intervals, capacity_per_interval)
    for tramo in timeline:
        tramo["timestamp_ini"] = descomprimir_tiempo(tramo["t_ini"], df_calend, modo="ini")
        tramo["timestamp_fin"] = descomprimir_tiempo(tramo["t_fin"], df_calend, modo="fin")

    df_ent = df_entregas.copy()
    df_ent = df_ent.rename(columns={
        "referencia": "pedido",
        "fecha_entrega": "fecha_entrega_req",
        "fecha_recepcion_materiales": "fecha_mat"
    })

    ############################################
    # 1) Convertir las columnas del df_ent a Timestamp
    df_ent["fecha_entrega_req"] = pd.to_datetime(df_ent["fecha_entrega_req"], errors="coerce")
    df_ent["fecha_mat"]         = pd.to_datetime(df_ent["fecha_mat"],         errors="coerce")

    info_pedidos = {}
    pedidos_en_sol = set([t["pedido"] for t in sol_tareas])
    for ped in pedidos_en_sol:
        info_pedidos[ped] = {
            "fecha_final":      None,
            "fecha_requerida":  None,
            "fecha_materiales": None,
            "delta_entrega_laboral": 0.0,
            "leadtime_laboral": 0.0
        }

    for _, row in df_ent.iterrows():
        ped = row["pedido"]
        if ped in info_pedidos:
            info_pedidos[ped]["fecha_requerida"]  = row["fecha_entrega_req"]  # Timestamp (o NaT)
            info_pedidos[ped]["fecha_materiales"] = row["fecha_mat"]          # Timestamp (o NaT)

    ############################################
    # 2) Armar max_fin_by_pedido
    from collections import defaultdict
    max_fin_by_pedido = defaultdict(lambda: None)
    for t in sol_tareas:
        p = t["pedido"]
        tsf = t["timestamp_fin"]
        # Si tsf es un datetime.datetime en vez de pd.Timestamp => convertir
        if isinstance(tsf, datetime.datetime) and not isinstance(tsf, pd.Timestamp):
            tsf = pd.Timestamp(tsf)
            t["timestamp_fin"] = tsf

        if tsf is not None:
            if max_fin_by_pedido[p] is None or tsf > max_fin_by_pedido[p]:
                max_fin_by_pedido[p] = tsf

    ############################################
    # 3) Calcular retraso/adelanto y lead time
    for ped in info_pedidos:
        fin = max_fin_by_pedido.get(ped)
        info_pedidos[ped]["fecha_final"] = fin

        fecha_req = info_pedidos[ped].get("fecha_requerida")   # pd.Timestamp o NaT
        fecha_mat = info_pedidos[ped].get("fecha_materiales")  # pd.Timestamp o NaT

        if pd.notnull(fecha_req) and pd.notnull(fin):
            # fin < req => adelanto, fin > req => retraso
            if fin < fecha_req:
                dias_laborales = calcular_dias_laborables(fin, fecha_req, df_calend)
                dias_diff = dias_laborales[0] if isinstance(dias_laborales, tuple) else dias_laborales
                info_pedidos[ped]["delta_entrega_laboral"] = -round(dias_diff, 2)
            else:
                dias_laborales = calcular_dias_laborables(fecha_req, fin, df_calend)
                dias_diff = dias_laborales[0] if isinstance(dias_laborales, tuple) else dias_laborales
                info_pedidos[ped]["delta_entrega_laboral"] = round(dias_diff, 2)

        if pd.notnull(fecha_mat) and pd.notnull(fin):
            lt_val = calcular_dias_laborables(fecha_mat, fin, df_calend)
            if isinstance(lt_val, tuple):
                lt_val = lt_val[0]
            info_pedidos[ped]["leadtime_laboral"] = round(lt_val, 2)

    ############################################
    # 4) Inyectar estos datos en sol_tareas
    for t in sol_tareas:
        ped = t["pedido"]
        info = info_pedidos[ped]
        t["fecha_entrega_requerida"]       = info["fecha_requerida"]
        t["fecha_entrega_estimada"]        = info["fecha_final"]
        t["delta_entrega_dias_laborales"]  = info["delta_entrega_laboral"]
        t["leadtime_dias_laborales"]       = info["leadtime_laboral"]
    retrasos = []
    leadtimes = []
    fechas_fin = []
    for ped, vals in info_pedidos.items():
        delta = vals["delta_entrega_laboral"]
        if delta > 0:
            retrasos.append(delta)
        leadtimes.append(vals["leadtime_laboral"])
        if vals["fecha_final"] is not None:
            fechas_fin.append(vals["fecha_final"])

    retraso_medio = sum(retrasos)/len(retrasos) if len(retrasos) > 0 else 0.0
    leadtime_medio = sum(leadtimes)/len(leadtimes) if len(leadtimes) > 0 else 0.0

    fechas_fin.sort()
    if len(fechas_fin) <= 1:
        dias_entre_entregas_prom = 0.0
    else:
        diffs = []
        for i in range(len(fechas_fin)-1):
            dd = calcular_dias_laborables(fechas_fin[i], fechas_fin[i+1], df_calend)
            if isinstance(dd, tuple):
                dd = dd[0]
            diffs.append(dd)
        dias_entre_entregas_prom = sum(diffs)/len(diffs)

    horas_x_dia = calcular_promedio_horas_laborables_por_dia(df_calend)

    resumen_metr = {
        "retraso_medio_dias": round(retraso_medio, 2),
        "leadtime_medio_dias": round(leadtime_medio, 2),
        "dias_entre_entregas_prom": round(dias_entre_entregas_prom, 2),
        "horas_laborables_por_dia": horas_x_dia
    }

    df_pedidos = pd.DataFrame.from_dict(info_pedidos, orient="index")

    return sol_tareas, timeline, (resumen_metr, df_pedidos)