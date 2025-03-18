# PATH: src/utils.py

import pandas as pd
import pulp
from datetime import datetime,timedelta
import os

from src.plot_gantt_matplotlib import plot_gantt

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

    df_entregas["fecha_entrega"] = pd.to_datetime(df_entregas["fecha_entrega"])
    df_entregas["fecha_recepcion_materiales"] = pd.to_datetime(df_entregas["fecha_recepcion_materiales"])

    df_calend["dia"] = pd.to_datetime(df_calend["dia"]).dt.date

    pedidos = df_entregas["referencia"].unique().tolist()
    tareas = df_tareas["id_interno"].unique().tolist()

    datos = {
        "df_entregas": df_entregas,
        "df_calend": df_calend,
        "df_tareas": df_tareas,
        "pedidos": pedidos,
        "tareas": tareas
    }
    return datos

def escribir_resultados(modelo, start, end, ruta_excel, df_tareas, df_entregas, df_calend):
    """
    Guarda los resultados de la planificación y genera el diagrama de Gantt.
    """

    estado = pulp.LpStatus[modelo.status]
    print(f"Estado del solver: {estado}")

    filas = []
    origen = datetime(2025, 3, 1)

    for (p, t), var_inicio in start.items():
        val_i = pulp.value(var_inicio)
        val_f = pulp.value(end[(p, t)])
        dt_i = origen + timedelta(hours=float(val_i)) if val_i else None
        dt_f = origen + timedelta(hours=float(val_f)) if val_f else None

        # Obtener ubicación y operarios asignados
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

    # Ruta base donde se guardará el archivo
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../archivos/bd_dev/output"))
    os.makedirs(output_dir, exist_ok=True)  # Crea la carpeta si no existe

    # Generar timestamp y nueva ruta del archivo
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.basename(ruta_excel)  # Extrae solo el nombre del archivo original
    base, ext = os.path.splitext(filename)  # Separa nombre y extensión de archivo
    new_file = os.path.join(output_dir, f"{base}_{timestamp}{ext}")  # Ensambla nueva ruta

    # Guardar el DataFrame en Excel
    with pd.ExcelWriter(new_file, engine="openpyxl", mode="w") as writer:
        df_sol.to_excel(writer, sheet_name="RESULTADOS", index=False)

    print(f"Resultados guardados en: {new_file}")

    # Llamar a la función plot_gantt pasando df_entregas
    plot_gantt(df_sol, df_entregas, df_calend)