# PATH: src/data_preprocessing/preparar_tareas_por_tiempos_validados.py

import pandas as pd

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


def preparar_tareas_por_tiempos_validados(ruta_excel, debug=True):
    xls = pd.ExcelFile(ruta_excel)

    # Leer hojas necesarias
    df_entregas = pd.read_excel(xls, sheet_name="ENTREGAS")
    df_validaciones = pd.read_excel(xls, sheet_name="VALIDACIONES_TIEMPOS")
    df_capacidades = pd.read_excel(xls, sheet_name="CAPACIDADES")

    # Crear diccionario rápido para ubicación -> nombre
    ubicacion_nombres = df_capacidades.set_index("ubicación")['nom_ubicacion'].to_dict()

    # Estructura base para la nueva hoja TAREAS
    tareas_cols = [
        "material_padre", "id_interno", "predecesora", "ubicación",
        "nom_ubicacion", "tipo_tarea", "descripcion", "tiempo_operario",
        "tiempo_verificado", "num_operarios_max"
    ]

    df_tareas = pd.DataFrame(columns=tareas_cols)

    # Verificar que todos los vértices en ENTREGAS tengan validaciones
    vertices_validos = set(df_validaciones["vertice"].unique())

    for _, entrega in df_entregas.iterrows():
        vertice = entrega["vertice"]
        referencia = entrega["referencia"]

        if vertice not in vertices_validos:
            if debug:
                print(f"⚠️ [DEBUG] Vértice '{vertice}' sin validaciones encontradas. Referencia '{referencia}' omitida.")
            continue

        validaciones_vertice = df_validaciones[df_validaciones["vertice"] == vertice]

        for _, val in validaciones_vertice.iterrows():
            tipo_tarea = val["tipo_tarea"]

            # Asignar tiempos según tipo de tarea
            tiempo_op = val["duracion_estimada"] if tipo_tarea == "OPERATIVA" else None
            tiempo_ver = val["duracion_estimada"] if tipo_tarea == "VERIFICADO" else None

            # Obtener ubicación directamente desde validaciones
            ubicacion_asignada = val.get("ubicación", 1)
            nom_ubicacion = ubicacion_nombres.get(ubicacion_asignada, "PREVIOS")

            nueva_tarea = {
                "material_padre": referencia,
                "id_interno": val["id_interno"],
                "predecesora": val["predecesoras"],
                "ubicación": ubicacion_asignada,
                "nom_ubicacion": nom_ubicacion,
                "tipo_tarea": tipo_tarea,
                "descripcion": val["descripcion"],
                "tiempo_operario": tiempo_op,
                "tiempo_verificado": tiempo_ver,
                "num_operarios_max": val["num_operarios_max"]
            }

            df_tareas = pd.concat([df_tareas, pd.DataFrame([nueva_tarea])], ignore_index=True)

    # Guardar la nueva hoja TAREAS
    with pd.ExcelWriter(ruta_excel, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        df_tareas.to_excel(writer, sheet_name="TAREAS", index=False)

    if debug:
        print(f"✅ [DEBUG] Hoja 'TAREAS' generada correctamente en '{ruta_excel}' con {len(df_tareas)} tareas.")


if __name__ == "__main__":
    ruta_excel = "archivos/db_dev/Datos_entrada_v16_fechas_relajadas_tiempos_reales.xlsx"
    preparar_tareas_por_tiempos_validados(ruta_excel)