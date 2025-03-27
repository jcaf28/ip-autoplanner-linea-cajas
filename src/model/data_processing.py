import math
import pandas as pd
from ortools.sat.python import cp_model
from src.model.time_management import descomprimir_tiempo, construir_timeline_detallado


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


def extraer_solucion(solver, status, all_vars, intervals, capacity_per_interval, df_calend):
    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        print("⚠️ No se encontró solución factible u óptima")
        return [], []

    sol_tareas = []
    for (pedido, t_idx), varset in all_vars.items():
        st = solver.Value(varset["start"])
        en = solver.Value(varset["end"])
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

    # Añadir timestamp_ini y timestamp_fin también al timeline
    for tramo in timeline:
        tramo["timestamp_ini"] = descomprimir_tiempo(tramo["t_ini"], df_calend, modo="ini")
        tramo["timestamp_fin"] = descomprimir_tiempo(tramo["t_fin"], df_calend, modo="fin")

    return sol_tareas, timeline