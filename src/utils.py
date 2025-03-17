import pandas as pd

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