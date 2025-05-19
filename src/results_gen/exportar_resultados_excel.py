# PATH: src/results_gen/exportar_resultados_excel.py

import os
import pandas as pd
from datetime import datetime
import platform
import subprocess

def exportar_resultados_excel(capacidades, tareas, timeline, resumen_pedidos, output_dir, open_file_location=True):
    os.makedirs(output_dir, exist_ok=True)

    df_tareas = pd.DataFrame(tareas)
    df_timeline = pd.DataFrame(timeline)
    df_capacidades = pd.DataFrame(capacidades)

    df_metrics = None
    if resumen_pedidos and isinstance(resumen_pedidos, tuple):
        resumen_metr, df_pedidos = resumen_pedidos
        df_metrics = pd.DataFrame([resumen_metr])
    elif isinstance(resumen_pedidos, dict):  # fallback
        df_metrics = pd.DataFrame([resumen_pedidos])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"solucion_planificada_{timestamp}.xlsx"
    ruta_salida = os.path.join(output_dir, filename)

    with pd.ExcelWriter(ruta_salida, engine="xlsxwriter") as writer:
        df_tareas.to_excel(writer, sheet_name="Tareas", index=False)
        df_timeline.to_excel(writer, sheet_name="Timeline", index=False)
        df_capacidades.to_excel(writer, sheet_name="Capacidades", index=False)
        
        if resumen_pedidos and isinstance(resumen_pedidos, tuple):
            resumen_metr, df_pedidos = resumen_pedidos
            df_metrics.to_excel(writer, sheet_name="Métricas_globales", index=False)
            
            # Mejorar el formato de la hoja de Pedidos
            workbook = writer.book
            
            # Formato para fechas
            fecha_format = workbook.add_format({'num_format': 'dd/mm/yyyy hh:mm'})
            
            # Crear una hoja mejorada de pedidos
            df_pedidos.reset_index(inplace=True)
            df_pedidos.rename(columns={'index': 'pedido'}, inplace=True)
            
            # Ordenar las columnas para mejor visualización
            cols_ordenadas = ['pedido', 'fecha_requerida', 'fecha_final', 
                             'fecha_materiales', 'fecha_materiales_calculada',
                             'recepcion_especificada', 'delta_entrega_laboral', 
                             'leadtime_laboral', 'holgura_dias']
            
            # Usar solo columnas que existen
            cols_a_usar = [c for c in cols_ordenadas if c in df_pedidos.columns]
            
            df_pedidos = df_pedidos[cols_a_usar]
            df_pedidos.to_excel(writer, sheet_name="Pedidos", index=False)
            
            # Aplicar formato a columnas de fecha
            worksheet = writer.sheets["Pedidos"]
            for col_idx, col_name in enumerate(df_pedidos.columns):
                if 'fecha' in col_name:
                    worksheet.set_column(col_idx, col_idx, 20, fecha_format)

    print(f"\n📁 Solución exportada a: {ruta_salida}")

    if open_file_location:
        abrir_explorador(output_dir)


def abrir_explorador(path):
    sistema = platform.system()
    try:
        if sistema == "Windows":
            os.startfile(os.path.realpath(path))
        elif sistema == "Darwin":  # macOS
            subprocess.Popen(["open", path])
        else:  # Linux (con entorno gráfico)
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"⚠️ No se pudo abrir la carpeta: {e}")
