# PATH: src/model/data_processing.py

import math
import pandas as pd
from ortools.sat.python import cp_model
from src.model.time_management import descomprimir_tiempo, construir_timeline_detallado, calcular_dias_laborables


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
    """
    Modificada para:
      1) Incluir fecha requerida, fecha estimada, retraso/adelanto, lead_time en días laborables.
      2) Calcular retrasos y lead times a nivel de pedido.
      3) Devolver también un mini-df o diccionario con métricas agregadas.
    """

    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        print("⚠️ No se encontró solución factible u óptima")
        return [], [], None  # Retornamos None en las métricas si no hay solución

    sol_tareas = []
    
    # 1. Reconstruimos las tareas (tal como lo hacías antes)
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

    # 2. Construimos el timeline igual que antes
    timeline = construir_timeline_detallado(sol_tareas, intervals, capacity_per_interval)

    # Añadir timestamp_ini y timestamp_fin también al timeline
    for tramo in timeline:
        tramo["timestamp_ini"] = descomprimir_tiempo(tramo["t_ini"], df_calend, modo="ini")
        tramo["timestamp_fin"] = descomprimir_tiempo(tramo["t_fin"], df_calend, modo="fin")

    # 3. Calcular las métricas para cada pedido
    #    - Fecha requerida de entrega (df_entregas["fecha_entrega"])
    #    - Fecha real de entrega (máx de timestamp_fin entre todas las tareas de ese pedido)
    #    - Retraso (solo si > 0) en días laborables
    #    - Lead time (fecha_recepcion_materiales -> fecha real de entrega) en días laborables
    df_entregas = df_entregas.copy()
    df_entregas = df_entregas.rename(columns={
        "referencia": "pedido",
        "fecha_entrega": "fecha_entrega_req",
        "fecha_recepcion_materiales": "fecha_mat"
    })

    # Creamos un diccionario para: pedido -> { final_date, required_date, mat_date, ... }
    info_pedidos = {}
    for ped in set([t["pedido"] for t in sol_tareas]):
        info_pedidos[ped] = {
            "fecha_final": None,
            "fecha_requerida": None,
            "fecha_materiales": None,
            "retraso_laboral": 0,
            "leadtime_laboral": 0
        }

    # Asociamos las fechas de df_entregas (si existe en df_entregas)  
    for _, row in df_entregas.iterrows():
        ped = row["pedido"]
        if ped in info_pedidos:
            info_pedidos[ped]["fecha_requerida"] = row["fecha_entrega_req"]
            info_pedidos[ped]["fecha_materiales"] = row["fecha_mat"]
    
    # Calculamos la fecha final real
    from collections import defaultdict
    max_fin_by_pedido = defaultdict(lambda: None)
    for t in sol_tareas:
        ped = t["pedido"]
        ts_fin = t["timestamp_fin"]
        if max_fin_by_pedido[ped] is None or ts_fin > max_fin_by_pedido[ped]:
            max_fin_by_pedido[ped] = ts_fin

    # Rellenamos la info en info_pedidos
    for ped in info_pedidos:
        fin = max_fin_by_pedido[ped]
        info_pedidos[ped]["fecha_final"] = fin

        # Fecha requerida
        fecha_req = info_pedidos[ped]["fecha_requerida"]
        if fecha_req is not None and fin is not None:
            dias_retraso = calcular_dias_laborables(fecha_req, fin, df_calend)
            # Si termina antes de la fecha requerida, retraso=0
            if fin <= fecha_req:
                info_pedidos[ped]["retraso_laboral"] = 0
            else:
                info_pedidos[ped]["retraso_laboral"] = dias_retraso

        # Lead time
        fecha_mat = info_pedidos[ped]["fecha_materiales"]
        if fecha_mat is not None and fin is not None:
            lt = calcular_dias_laborables(fecha_mat, fin, df_calend)
            info_pedidos[ped]["leadtime_laboral"] = lt

    # 4. Inyectar estos datos a cada tarea (para que aparezcan en el hover)
    #    (el diagrama de Gantt usará la clave que guardemos en la tarea)
    for t in sol_tareas:
        ped = t["pedido"]
        pedido_info = info_pedidos[ped]
        t["fecha_entrega_requerida"] = pedido_info["fecha_requerida"]
        t["fecha_entrega_estimada"] = pedido_info["fecha_final"]
        t["retraso_dias_laborales"] = pedido_info["retraso_laboral"]
        t["leadtime_dias_laborales"] = pedido_info["leadtime_laboral"]

    # 5. Calcular métricas globales (retraso medio, leadtime medio, etc.)
    #    - Retraso medio (acumular solo si >0)
    #    - Lead time medio
    #    - Promedio de días entre entregas consecutivas (ordenamos las fechas_finales)
    retrasos = []
    leadtimes = []
    fechas_finales = []
    for ped, vals in info_pedidos.items():
        if vals["retraso_laboral"] > 0:
            retrasos.append(vals["retraso_laboral"])
        leadtimes.append(vals["leadtime_laboral"])
        if vals["fecha_final"] is not None:
            fechas_finales.append(vals["fecha_final"])

    retraso_medio = sum(retrasos)/len(retrasos) if len(retrasos)>0 else 0
    leadtime_medio = sum(leadtimes)/len(leadtimes) if len(leadtimes)>0 else 0

    # Para "cada cuántos días laborables se entrega un pedido":
    # Ordenamos las fechas finales y sacamos la diferencia promedio
    fechas_finales.sort()
    if len(fechas_finales) <= 1:
        dias_entre_entregas_prom = 0
    else:
        diferencias = []
        for i in range(len(fechas_finales)-1):
            d1 = fechas_finales[i]
            d2 = fechas_finales[i+1]
            dif = calcular_dias_laborables(d1, d2, df_calend)
            diferencias.append(dif)
        dias_entre_entregas_prom = sum(diferencias)/len(diferencias)

    # Estructura final con las métricas
    resumen_métricas = {
        "retraso_medio_dias": retraso_medio,
        "leadtime_medio_dias": leadtime_medio,
        "dias_entre_entregas_prom": dias_entre_entregas_prom
    }

    # También podemos devolver un DataFrame con la info de cada pedido si quieres
    # (Esto a veces es útil para exportar a Excel o para tablas en el reporte):
    df_pedidos = pd.DataFrame.from_dict(info_pedidos, orient="index")
    # df_pedidos tendrá columnas: fecha_final, fecha_requerida, fecha_materiales, retraso_laboral, leadtime_laboral, ...
    # Ajusta según lo que quieras

    return sol_tareas, timeline, (resumen_métricas, df_pedidos)