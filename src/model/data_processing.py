# PATH: src/model/data_processing.py

import math
import pandas as pd
from ortools.sat.python import cp_model
from src.model.time_management import ( descomprimir_tiempo, 
                                        construir_timeline_detallado, 
                                        calcular_dias_laborables,
                                        calcular_promedio_horas_laborables_por_dia)


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


def extraer_solucion( solver, 
                      status, 
                      all_vars, 
                      intervals, 
                      capacity_per_interval, 
                      df_calend,
                      df_entregas):
    from ortools.sat.python import cp_model
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

    # Estructura por pedido
    info_pedidos = {}
    pedidos_en_sol = set([t["pedido"] for t in sol_tareas])
    for ped in pedidos_en_sol:
        info_pedidos[ped] = {
            "fecha_final":      None,
            "fecha_requerida":  None,
            "fecha_materiales": None,
            "delta_entrega_laboral": 0.0,  # (+) => retraso, (-) => adelanto
            "leadtime_laboral": 0.0
        }

    # Rellenar info de df_ent
    for _, row in df_ent.iterrows():
        ped = row["pedido"]
        if ped in info_pedidos:
            info_pedidos[ped]["fecha_requerida"]  = row["fecha_entrega_req"]
            info_pedidos[ped]["fecha_materiales"] = row["fecha_mat"]

    # Calcular fecha_final real por pedido
    from collections import defaultdict
    max_fin_by_pedido = defaultdict(lambda: None)
    for t in sol_tareas:
        p = t["pedido"]
        tsf = t["timestamp_fin"]
        if max_fin_by_pedido[p] is None or tsf > max_fin_by_pedido[p]:
            max_fin_by_pedido[p] = tsf

    # Para cada pedido, calculamos delta_entrega_laboral (pos o neg)
    for ped in info_pedidos:
        fin = max_fin_by_pedido[ped]
        info_pedidos[ped]["fecha_final"] = fin

        fecha_req = info_pedidos[ped]["fecha_requerida"]
        if fecha_req and fin:
            # días_laborables_req -> fin
            # si => delta > 0 => retraso, < 0 => adelanto
            if fin < fecha_req:
                dias_laborales = calcular_dias_laborables(fin, fecha_req, df_calend)
                dias_diff = dias_laborales[0] if isinstance(dias_laborales, tuple) else dias_laborales
                info_pedidos[ped]["delta_entrega_laboral"] = -round(dias_diff, 2)  # Adelanto → negativo
            else:
                dias_laborales = calcular_dias_laborables(fecha_req, fin, df_calend)
                dias_diff = dias_laborales[0] if isinstance(dias_laborales, tuple) else dias_laborales
                info_pedidos[ped]["delta_entrega_laboral"] = round(dias_diff, 2)   # Retraso → positivo

        # lead time => (fecha_mat -> fin)
        fecha_mat = info_pedidos[ped]["fecha_materiales"]
        if fecha_mat and fin:
            lt_val = calcular_dias_laborables(fecha_mat, fin, df_calend)
            if isinstance(lt_val, tuple):
                lt_val = lt_val[0]
            info_pedidos[ped]["leadtime_laboral"] = round(lt_val, 2)

    # Inyectar estos datos en sol_tareas
    for t in sol_tareas:
        ped = t["pedido"]
        info = info_pedidos[ped]
        t["fecha_entrega_requerida"]     = info["fecha_requerida"]
        t["fecha_entrega_estimada"]      = info["fecha_final"]
        t["delta_entrega_dias_laborales"] = info["delta_entrega_laboral"]   # (+) => retraso, (-) => adelanto
        t["leadtime_dias_laborales"]     = info["leadtime_laboral"]

    # Agregar métricas globales
    retrasos = []
    leadtimes = []
    fechas_fin = []
    for ped, vals in info_pedidos.items():
        delta = vals["delta_entrega_laboral"]
        # si delta > 0 => retraso
        if delta > 0:
            retrasos.append(delta)
        leadtimes.append(vals["leadtime_laboral"])
        if vals["fecha_final"] is not None:
            fechas_fin.append(vals["fecha_final"])

    # Retraso medio
    if len(retrasos) > 0:
        retraso_medio = sum(retrasos)/len(retrasos)
    else:
        retraso_medio = 0.0

    # Lead time medio
    if len(leadtimes) > 0:
        leadtime_medio = sum(leadtimes)/len(leadtimes)
    else:
        leadtime_medio = 0.0

    # Días entre entregas
    fechas_fin.sort()
    if len(fechas_fin) <= 1:
        dias_entre_entregas_prom = 0.0
    else:
        diffs = []
        for i in range(len(fechas_fin)-1):
            dd = calcular_dias_laborables(fechas_fin[i], fechas_fin[i+1], df_calend)
            # dd puede ser float o (float, hxdia)
            if isinstance(dd, tuple):
                dd = dd[0]
            diffs.append(dd)
        dias_entre_entregas_prom = sum(diffs)/len(diffs)

    # Horas laborables por día
    horas_x_dia = calcular_promedio_horas_laborables_por_dia(df_calend)

    resumen_metr = {
        "retraso_medio_dias": round(retraso_medio, 2),
        "leadtime_medio_dias": round(leadtime_medio, 2),
        "dias_entre_entregas_prom": round(dias_entre_entregas_prom, 2),
        "horas_laborables_por_dia": horas_x_dia    # lo mostramos en el Gantt
    }

    # DataFrame final
    df_pedidos = pd.DataFrame.from_dict(info_pedidos, orient="index")

    return sol_tareas, timeline, (resumen_metr, df_pedidos)