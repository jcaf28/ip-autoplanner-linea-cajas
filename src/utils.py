# PATH: src/utils.py

import pandas as pd
import pulp
from datetime import datetime
import os

from src.plot_gantt_matplotlib import plot_gantt_matplotlib
from src.plot_gantt import plot_gantt

def leer_datos(ruta_excel):
    """
    Lee datos de:
      - ENTREGAS: referencia, fecha_entrega, fecha_recepcion_materiales
      - CALENDARIO: dia, turno, hora_inicio, hora_fin, cantidad_operarios
      - TAREAS: id_interno, predecesora(s), ubicacion, tiempo_operario, tiempo_robot, tiempo_verificado
    Devuelve un dict con dataframes y listas útiles.
    """
    xls = pd.ExcelFile(ruta_excel)

    df_entregas = pd.read_excel(xls, sheet_name="ENTREGAS")
    df_calend   = pd.read_excel(xls, sheet_name="CALENDARIO")
    df_tareas   = pd.read_excel(xls, sheet_name="TAREAS")
    df_capacidades = pd.read_excel(xls, sheet_name="CAPACIDADES")
    df_parametros = pd.read_excel(xls, sheet_name="PARAMETROS")

    df_entregas["fecha_entrega"] = pd.to_datetime(df_entregas["fecha_entrega"], dayfirst=True)
    df_entregas["fecha_recepcion_materiales"] = pd.to_datetime(df_entregas["fecha_recepcion_materiales"], dayfirst=True)


    df_calend["dia"] = pd.to_datetime(df_calend["dia"]).dt.date

    pedidos = df_entregas["referencia"].unique().tolist()
    tareas = df_tareas["id_interno"].unique().tolist()

    datos = {
    "df_entregas": df_entregas,
    "df_calend": df_calend,
    "df_tareas": df_tareas,
    "df_capacidades": df_capacidades,
    "df_parametros": df_parametros,
    "pedidos": pedidos,
    "tareas": tareas
    }

    return datos

def escribir_resultados(modelo, start, end, ruta_excel, df_tareas, df_entregas, df_calend, fn_descomprimir, df_capacidades):
    """
    Guarda los resultados de la planificación y genera el diagrama de Gantt.
    """
    import os
    from datetime import datetime
    import pulp

    estado = pulp.LpStatus[modelo.status]
    print(f"Estado del solver: {estado}")

    filas = []
    origen = datetime(2025, 3, 1)

    for (p, t), var_inicio in start.items():
        val_i = pulp.value(var_inicio)
        val_f = pulp.value(end[(p, t)])

        # Se omiten tareas con duración 0
        if val_i is None or val_f is None or (val_f - val_i) == 0:
            continue

        dt_i = fn_descomprimir(val_i) if val_i is not None else None
        dt_f = fn_descomprimir(val_f) if val_f is not None else None

        # Obtener datos de la tarea
        row = df_tareas[(df_tareas["material_padre"] == p) & (df_tareas["id_interno"] == t)].iloc[0]
        ubicacion = row["nom_ubicacion"]
        n_ops = int(row["num_operarios_fijos"]) if not pd.isnull(row["num_operarios_fijos"]) else 1

        filas.append({
            "pedido": p,
            "tarea": t,
            "inicio": val_i,
            "fin": val_f,
            "datetime_inicio": dt_i,
            "datetime_fin": dt_f,
            "ubicacion": ubicacion,
            "operarios_asignados": n_ops
        })

    df_sol = pd.DataFrame(filas)

    # Guardar resultados en Excel
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../archivos/db_dev/output"))
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.basename(ruta_excel)
    base, ext = os.path.splitext(filename)
    new_file = os.path.join(output_dir, f"{base}_{timestamp}{ext}")

    with pd.ExcelWriter(new_file, engine="openpyxl", mode="w") as writer:
        df_sol.to_excel(writer, sheet_name="RESULTADOS", index=False)

    print(f"Resultados guardados en: {new_file}")

    # Generar la lista de ubicaciones ordenada según df_capacidades
    ordered_locations = df_capacidades.sort_values("ubicación")["nom_ubicacion"].tolist()

    # Llamar a la función del Gantt pasando ordered_locations
    from src.plot_gantt_matplotlib import plot_gantt_matplotlib
    plot_gantt_matplotlib(df_sol, df_entregas, df_calend, ordered_locations)

def check_situacion_inicial(df_tareas, df_capacidades, verbose=True):
    """
    FUNCIÓN PARA DETECTAR SI LA SITUACIÓN DE ARRANQUE ES VÁLIDA
    Verifica la coherencia de la situación inicial de las tareas.
    1) Detecta qué tareas "ocupan posición" (las que tienen 0% < completada_porcentaje < 100%).
    2) Asegura que en cada ubicación no se supere la capacidad definida en CAPACIDADES.
    3) Revisa que no se viole el orden de predecesoras: si una tarea está al 100%,
       todas sus predecesoras deben estar también al 100%.
    Lanza ValueError si detecta inconsistencias.
    """
    # Convertir las capacidades a diccionario {nom_ubicacion: capacidad}
    dict_cap = df_capacidades.set_index("nom_ubicacion")["capacidad"].to_dict()
    
    # 1) Detectar tareas en curso (completadas parcialmente)
    df_ocupando = df_tareas[(df_tareas["completada_porcentaje"] > 0) & 
                            (df_tareas["completada_porcentaje"] < 1)]
    
    # Verificar que en cada ubicación no se supere la capacidad
    if not df_ocupando.empty:
        g = df_ocupando.groupby("nom_ubicacion").size()
        for ubicacion, num in g.items():
            capacidad = dict_cap.get(ubicacion, 1)
            if num > capacidad:
                raise ValueError(
                    f"La ubicación '{ubicacion}' tiene {num} tareas en curso (completada entre 0% y 100%), "
                    f"pero su capacidad es {capacidad}. Supera la capacidad permitida."
                )
                
    # 2) Chequeo del orden de predecesoras:
    completado = {}
    for _, row in df_tareas.iterrows():
        mat = row["material_padre"]
        tid = row["id_interno"]
        pct = row.get("completada_porcentaje", 0.0)
        completado[(mat, tid)] = pct

    for _, row in df_tareas.iterrows():
        mat = row["material_padre"]
        tid = row["id_interno"]
        pct_tarea = completado[(mat, tid)]
        
        if pct_tarea >= 1.0 and not pd.isnull(row["predecesora"]):
            lista_preds = [int(x.strip()) for x in str(row["predecesora"]).split(";")]
            for p_id in lista_preds:
                pct_pred = completado.get((mat, p_id), 0.0)
                if pct_pred < 1.0:
                    raise ValueError(
                        f"La tarea {tid} se indica al 100% completada, pero su predecesora {p_id} "
                        f"del material {mat} no está al 100%. Violación de orden."
                    )

    if verbose:
        print("check_situacion_inicial: Situación inicial verificada con éxito.")
    return True
