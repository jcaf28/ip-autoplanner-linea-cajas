# PATH: src/model/time_management.py

import pandas as pd
from datetime import datetime, timedelta

def comprimir_calendario(df_calend):
    """
    Ordena los turnos de df_calend, calcula su duración en minutos
    y crea una lista 'intervals' con sus comp_start y comp_end acumulados.
    Si un turno cruza la medianoche, suma un día a dt_fin.
    """
    df_calend = df_calend.copy()
    df_calend = df_calend.sort_values(by=["dia", "hora_inicio"])
    intervals = []
    capacity_per_interval = []
    acumulado = 0

    for _, row in df_calend.iterrows():
        dia = row["dia"]
        hi = row["hora_inicio"]
        hf = row["hora_fin"]
        cap = row["cant_operarios"]

        if isinstance(hi, str):
            hi = datetime.strptime(hi, "%H:%M:%S").time()
        if isinstance(hf, str):
            hf = datetime.strptime(hf, "%H:%M:%S").time()

        dt_ini = datetime(dia.year, dia.month, dia.day, hi.hour, hi.minute, hi.second)
        dt_fin = datetime(dia.year, dia.month, dia.day, hf.hour, hf.minute, hf.second)

        # Turno cruza medianoche
        if dt_fin <= dt_ini:
            dt_fin += timedelta(days=1)

        dur_secs = (dt_fin - dt_ini).total_seconds()
        dur_min = int(round(dur_secs / 60.0))
        if dur_min <= 0:
            continue

        comp_start = acumulado
        comp_end = acumulado + dur_min

        intervals.append({
            "dt_inicio": dt_ini,
            "dt_fin": dt_fin,
            "comp_start": comp_start,
            "comp_end": comp_end
        })
        capacity_per_interval.append(int(cap))
        acumulado += dur_min

    return intervals, capacity_per_interval


def descomprimir_tiempo(t, df_calend, modo="ini"):
    """
    Convierte un minuto acumulado `t` en un timestamp, según df_calend.
    - modo="ini": se asocia al inicio del turno donde cae t
    - modo="fin": se asocia al final del turno donde cae t
    Devuelve None y lanza un warning si t queda fuera.
    """
    df_calend = df_calend.copy()
    df_calend["dia"] = pd.to_datetime(df_calend["dia"]).dt.date
    df_calend["hora_inicio"] = pd.to_datetime(df_calend["hora_inicio"], format="%H:%M:%S").dt.time
    df_calend["hora_fin"]    = pd.to_datetime(df_calend["hora_fin"],    format="%H:%M:%S").dt.time

    df_calend = df_calend.sort_values(by=["dia", "hora_inicio"]).reset_index(drop=True)

    acumulado = 0
    for _, row in df_calend.iterrows():
        dia = row["dia"]
        hi = row["hora_inicio"]
        hf = row["hora_fin"]

        dt_ini = datetime.combine(dia, hi)
        dt_fin = datetime.combine(dia, hf)

        # Turno cruza medianoche
        if dt_fin <= dt_ini:
            dt_fin += timedelta(days=1)

        dur_min = int((dt_fin - dt_ini).total_seconds() / 60)
        comp_start = acumulado
        comp_end = acumulado + dur_min

        if modo == "ini" and comp_start <= t < comp_end:
            delta = t - comp_start
            return dt_ini + timedelta(minutes=delta)

        elif modo == "fin" and comp_start < t <= comp_end:
            delta = t - comp_start
            return dt_ini + timedelta(minutes=delta)

        acumulado = comp_end

    print(f"⚠️ [WARNING] Tiempo {t} fuera del calendario definido. No se puede descomprimir.")
    return None


def comprimir_tiempo(dt, df_calend):
    """
    Convierte una fecha/hora dt a un número de minutos acumulados en df_calend.
    Si dt cae antes del primer turno => 0.
    Si dt cae entre turnos => sumamos la parte previa más la parte parcial del turno.
    Si dt está después del último turno => el total acumulado.
    
    Nota: Si el turno cruza medianoche, habría que duplicar la misma lógica
    que en comprimir_calendario (sumar 1 día). 
    Si no, se asume que no hay problemas o ya se corrigió en df_calend.
    """
    dfc = df_calend.copy()
    dfc["dia"] = pd.to_datetime(dfc["dia"]).dt.date
    dfc["hora_inicio"] = pd.to_datetime(dfc["hora_inicio"], format="%H:%M:%S").dt.time
    dfc["hora_fin"]    = pd.to_datetime(dfc["hora_fin"],    format="%H:%M:%S").dt.time

    dfc = dfc.sort_values(by=["dia", "hora_inicio"]).reset_index(drop=True)

    # Calculamos dur_min ajustando cruces de medianoche
    # Similar a comprimir_calendario
    turnos = []
    acumulado = 0
    for _, row in dfc.iterrows():
        dia = row["dia"]
        hi = row["hora_inicio"]
        hf = row["hora_fin"]

        dt_ini = datetime.combine(dia, hi)
        dt_fin = datetime.combine(dia, hf)
        if dt_fin <= dt_ini:
            dt_fin += timedelta(days=1)

        dur_min = int((dt_fin - dt_ini).total_seconds() / 60)
        turnos.append((dt_ini, dt_fin, acumulado, acumulado + dur_min))
        acumulado += dur_min

    # Recorremos la lista 'turnos' para ubicar dt
    if not turnos:
        return 0

    # Si dt es antes del primer turno
    if dt < turnos[0][0]:
        return 0

    # Vamos iterando
    for (t_ini, t_fin, comp_start, comp_end) in turnos:
        if dt < t_ini:
            # Aún no llegamos a este turno
            return comp_start
        if t_ini <= dt < t_fin:
            # Estamos dentro del turno
            delta = (dt - t_ini).total_seconds() / 60
            return int(round(comp_start + delta))

    # Si dt es posterior al último turno
    return turnos[-1][3]


def construir_timeline_detallado(tareas, intervals, capacity_per_interval):
    """
    Devuelve una lista de diccionarios, cada uno con:
      t_ini, t_fin, ocupacion, operarios_turno, %ocup
    contemplando cambios simultáneos en ocupación y límites de turnos.
    """

    def turno_idx_de_tiempo(t):
        for i, seg in enumerate(intervals):
            if seg["comp_start"] <= t < seg["comp_end"]:
                return i
        return -1

    # 1) Generar eventos: +x_op en start, -x_op en end
    eventos = []
    for tarea in tareas:
        xop = tarea["x_op"]
        if xop > 0:
            eventos.append((tarea["start"], +xop))
            eventos.append((tarea["end"],   -xop))

    # Añadimos los límites de turnos con delta_op=0
    for i, seg in enumerate(intervals):
        eventos.append((seg["comp_start"], 0))
        eventos.append((seg["comp_end"],   0))

    # 2) Ordenar eventos: por tiempo, si empatan, primero entradas (+), luego salidas (-)
    eventos.sort(key=lambda e: (e[0], -e[1]))

    # 3) Recorremos para crear tramos [ti, ti+1) con su ocupación
    timeline = []
    ocupacion_actual = 0

    for i in range(len(eventos) - 1):
        t0, delta_op = eventos[i]
        ocupacion_actual += delta_op
        t1 = eventos[i + 1][0]

        if t1 > t0:
            t_ini_segmento = t0
            while t_ini_segmento < t1:
                idx_turno = turno_idx_de_tiempo(t_ini_segmento)
                if idx_turno == -1:
                    break  # fuera de todos los turnos

                fin_turno = intervals[idx_turno]["comp_end"]
                t_fin_segmento = min(fin_turno, t1)
                cap_turno = capacity_per_interval[idx_turno]

                porc_ocup = 0
                if cap_turno > 0:
                    porc_ocup = round(100 * ocupacion_actual / cap_turno, 2)

                timeline.append({
                    "t_ini": t_ini_segmento,
                    "t_fin": t_fin_segmento,
                    "ocupacion": ocupacion_actual,
                    "operarios_turno": cap_turno,
                    "%ocup": porc_ocup
                })

                t_ini_segmento = t_fin_segmento

    return timeline


def calcular_dias_laborables(ts_inicio, ts_fin, df_calend):
    """
    Devuelve el número decimal de días laborables entre dos timestamps, considerando turnos nocturnos.
    Cada día laborable se mide como su intersección con [ts_inicio, ts_fin],
    dividido por la media de horas/día (en segundos) => días decimales.
    """
    if ts_inicio > ts_fin:
        return 0.0

    df_calend = df_calend.copy()
    df_calend["dia"] = pd.to_datetime(df_calend["dia"]).dt.date
    df_calend["hora_inicio"] = pd.to_datetime(df_calend["hora_inicio"], format="%H:%M:%S").dt.time
    df_calend["hora_fin"]    = pd.to_datetime(df_calend["hora_fin"],    format="%H:%M:%S").dt.time

    total_seg_laborales = 0

    for _, row in df_calend.iterrows():
        dia = row["dia"]
        dt_ini = datetime.combine(dia, row["hora_inicio"])
        dt_fin = datetime.combine(dia, row["hora_fin"])

        # Turno nocturno
        if dt_fin <= dt_ini:
            dt_fin += timedelta(days=1)

        # Si el turno está totalmente fuera del rango, lo saltamos
        if dt_fin <= ts_inicio or dt_ini >= ts_fin:
            continue

        # Intersección real
        tramo_ini = max(ts_inicio, dt_ini)
        tramo_fin = min(ts_fin, dt_fin)
        if tramo_fin > tramo_ini:
            total_seg_laborales += (tramo_fin - tramo_ini).total_seconds()

    horas_por_dia = calcular_promedio_horas_laborables_por_dia(df_calend)
    if horas_por_dia == 0:
        return 0.0

    seg_por_dia = horas_por_dia * 3600
    return round(total_seg_laborales / seg_por_dia, 2)


def calcular_promedio_horas_laborables_por_dia(df_calend):
    """
    Calcula cuántas horas laborables hay en promedio por día natural (según df_calend).
    Soporta turnos nocturnos (si dt_fin < dt_ini => +1 día).
    """
    dfc = df_calend.copy()
    dfc["dia"] = pd.to_datetime(dfc["dia"]).dt.date
    dfc["hora_inicio"] = pd.to_datetime(dfc["hora_inicio"], format="%H:%M:%S").dt.time
    dfc["hora_fin"]    = pd.to_datetime(dfc["hora_fin"],    format="%H:%M:%S").dt.time

    # Sumamos horas reales por día
    # Si hf <= hi => cruza medianoche => sumamos 1 día
    rows = []
    for _, row in dfc.iterrows():
        dia = row["dia"]
        hi = datetime.combine(dia, row["hora_inicio"])
        hf = datetime.combine(dia, row["hora_fin"])
        if hf <= hi:
            hf += timedelta(days=1)

        dur_h = (hf - hi).total_seconds() / 3600
        rows.append((dia, dur_h))

    # rows puede contener un day X y un turno que termina al día siguiente
    # => si quieres que cuente para day+1, necesitaríamos otra partición,
    #   pero asumimos que se acumula al day principal.
    #   Si no, habría que trocear turnos. 
    #   Depende de tu preferencia. 
    #   Por ahora sumamos entero al day => la media puede quedar un poco sesgada.

    df_temp = pd.DataFrame(rows, columns=["dia", "horas"])
    # Agrupamos por 'dia'
    horas_por_dia = df_temp.groupby("dia")["horas"].sum()

    total_horas = horas_por_dia.sum()
    ndias = len(horas_por_dia)
    if ndias == 0:
        return 0.0

    return round(total_horas / ndias, 2)
