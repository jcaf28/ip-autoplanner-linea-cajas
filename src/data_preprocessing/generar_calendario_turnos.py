import pandas as pd
from datetime import datetime, timedelta

def generar_calendario_formateado(ruta_excel, hoja="CALENDARIO_SIN_FORMATO", debug=True):
    """
    Convierte un calendario compacto en formato largo y lo guarda como hoja 'CALENDARIO'.
    """
    df = pd.read_excel(ruta_excel, sheet_name=hoja)

    columnas_turnos = [
        ("hora_ini_turno_1", "cant_op_turno_1"),
        ("hora_ini_turno_2", "cant_op_turno_2"),
        ("hora_ini_turno_noche", "cant_op_turno_noche")
    ]

    registros = []

    for _, row in df.iterrows():
        dia = pd.to_datetime(row["dia"]).date()
        dur_turno = row["cant_horas"]

        turnos = []
        for idx, (col_hora, col_op) in enumerate(columnas_turnos, start=1):
            hora_ini = row.get(col_hora)
            cant_op = row.get(col_op)

            if pd.notna(hora_ini) and pd.notna(cant_op):
                hora_ini = datetime.strptime(str(hora_ini), "%H:%M:%S").time()
                dt_ini = datetime.combine(dia, hora_ini)
                dt_fin = dt_ini + timedelta(hours=dur_turno)
                hora_fin = dt_fin.time()
                turnos.append((idx, hora_ini, hora_fin, int(cant_op)))

        # Verificación de solapamientos
        for i in range(1, len(turnos)):
            prev_end = datetime.combine(dia, turnos[i-1][2])
            curr_start = datetime.combine(dia, turnos[i][1])
            if curr_start < prev_end:
                print(f"⚠️ [SOLAPAMIENTO] {dia} - Turno {turnos[i-1][0]} se solapa con Turno {turnos[i][0]}")

        for t in turnos:
            registros.append({
                "dia": dia.strftime("%d/%m/%Y"),  # <-- aquí el cambio de formato
                "turno": t[0],
                "hora_inicio": t[1],
                "hora_fin": t[2],
                "cant_operarios": t[3]
            })

    df_calendario = pd.DataFrame(registros)

    # Escribir hoja CALENDARIO en el Excel
    with pd.ExcelWriter(ruta_excel, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        df_calendario.to_excel(writer, sheet_name="CALENDARIO", index=False)

    if debug:
        print(f"✅ [DEBUG] Hoja 'CALENDARIO' generada con {len(df_calendario)} filas.")
