# PATH: src/model/time_management.py

import pandas as pd
from datetime import datetime, timedelta

def comprimir_calendario(df_calend):
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
    Convierte un minuto acumulado `t` a un timestamp.
    - modo="ini": descompresión de inicio -> se asocia al inicio del turno donde cae t
    - modo="fin": descompresión de fin -> si t cae justo al final de un turno, se asocia a ese final
    """
    df_calend = df_calend.copy()

    df_calend["hora_inicio"] = pd.to_datetime(df_calend["hora_inicio"], format="%H:%M:%S").dt.time
    df_calend["hora_fin"]    = pd.to_datetime(df_calend["hora_fin"],    format="%H:%M:%S").dt.time

    df_calend["dur_min"] = [
        (datetime.combine(row["dia"], row["hora_fin"]) - datetime.combine(row["dia"], row["hora_inicio"])).total_seconds() / 60
        for _, row in df_calend.iterrows()
    ]
    df_calend["dur_min"] = df_calend["dur_min"].astype(int)

    df_calend = df_calend.sort_values(by=["dia", "hora_inicio"]).reset_index(drop=True)

    acumulado = 0
    for _, row in df_calend.iterrows():
        dur = row["dur_min"]
        comp_start = acumulado
        comp_end = acumulado + dur

        if modo == "ini" and comp_start <= t < comp_end:
            delta = t - comp_start
            base_dt = datetime.combine(row["dia"], row["hora_inicio"])
            return base_dt + timedelta(minutes=int(delta))

        elif modo == "fin" and comp_start < t <= comp_end:
            delta = t - comp_start
            base_dt = datetime.combine(row["dia"], row["hora_inicio"])
            return base_dt + timedelta(minutes=int(delta))

        acumulado = comp_end

    return None  # fuera de calendario

def comprimir_tiempo(dt, df_calend):
    """
    Convierte una fecha/hora dt (datetime) al número de minutos acumulados
    según la estructura de turnos de df_calend.
    Si dt cae antes del primer turno, devuelve 0.
    Si dt cae después del último turno, devuelve el total de minutos acumulados de toda la calendarización.
    Si cae en medio, suma los turnos enteros previos y añade la parte proporcional del turno en el que cae.
    """
    dfc = df_calend.copy()
    # Aseguramos que las columnas 'dia', 'hora_inicio' y 'hora_fin' estén como datetime/time
    dfc["dia"] = pd.to_datetime(dfc["dia"]).dt.date

    # Convertimos hora_inicio y hora_fin a tipo datetime.time si no lo están
    dfc["hora_inicio"] = pd.to_datetime(dfc["hora_inicio"], format="%H:%M:%S").dt.time
    dfc["hora_fin"]    = pd.to_datetime(dfc["hora_fin"],    format="%H:%M:%S").dt.time

    # Calculamos la duración en minutos de cada turno
    dfc = dfc.sort_values(by=["dia", "hora_inicio"]).reset_index(drop=True)
    dfc["dur_min"] = [
        (datetime.combine(row["dia"], row["hora_fin"]) - datetime.combine(row["dia"], row["hora_inicio"])).total_seconds()/60
        for _, row in dfc.iterrows()
    ]
    dfc["dur_min"] = dfc["dur_min"].astype(int)

    acumulado = 0
    ultimo_acumulado = 0
    for _, row in dfc.iterrows():
        dt_inicio_turno = datetime.combine(row["dia"], row["hora_inicio"])
        dt_fin_turno    = datetime.combine(row["dia"], row["hora_fin"])
        dur_minutos     = row["dur_min"]

        # Si dt está antes de este turno, devolvemos el acumulado sin contar este turno.
        if dt < dt_inicio_turno:
            return acumulado

        # Si dt está dentro de este turno, añadimos la parte parcial
        if dt_inicio_turno <= dt < dt_fin_turno:
            delta = (dt - dt_inicio_turno).total_seconds()/60
            return int(acumulado + round(delta))

        # Si dt está más allá de este turno, sumamos todo el turno y seguimos
        acumulado += dur_minutos
        ultimo_acumulado = acumulado

    # Si dt es posterior al último turno disponible, devolvemos el acumulado total
    return ultimo_acumulado

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
    #    + también añadimos los límites de turnos con delta_op=0
    eventos = []
    for tarea in tareas:
        xop = tarea["x_op"]
        if xop > 0:
            eventos.append((tarea["start"], +xop))
            eventos.append((tarea["end"],   -xop))
    for i, seg in enumerate(intervals):
        eventos.append((seg["comp_start"], 0))
        eventos.append((seg["comp_end"],   0))

    # 2) Ordenar eventos: primero por tiempo, si empatan
    #    primero las entradas (+) y después las salidas (-)
    eventos.sort(key=lambda e: (e[0], -e[1]))

    # 3) Recorremos eventos para crear tramos [tiempo_i, tiempo_(i+1))
    #    y en cada tramo calculamos la ocupación (acumulada) y
    #    partimos dicho tramo según los límites de los turnos.
    timeline = []
    ocupacion_actual = 0

    for i in range(len(eventos) - 1):
        t0, delta_op = eventos[i]
        # Actualizar ocupacion con el evento actual
        ocupacion_actual += delta_op

        t1 = eventos[i + 1][0]
        if t1 > t0:
            # Recorremos este rango [t0, t1) y lo partimos
            # si cruza varios turnos
            t_ini_segmento = t0
            while t_ini_segmento < t1:
                idx_turno = turno_idx_de_tiempo(t_ini_segmento)
                if idx_turno == -1:
                    break  # fuera de todos los turnos

                fin_turno = intervals[idx_turno]["comp_end"]
                t_fin_segmento = min(fin_turno, t1)
                cap_turno = capacity_per_interval[idx_turno]

                if cap_turno > 0:
                    p_ocup = round(100 * ocupacion_actual / cap_turno, 2)
                else:
                    p_ocup = 0

                timeline.append({
                    "t_ini": t_ini_segmento,
                    "t_fin": t_fin_segmento,
                    "ocupacion": ocupacion_actual,
                    "operarios_turno": cap_turno,
                    "%ocup": p_ocup
                })

                t_ini_segmento = t_fin_segmento

    return timeline

def calcular_dias_laborables(ts_inicio, ts_fin, df_calend):
    """
    Devuelve el número decimal de días laborables entre dos timestamps, según df_calend.

    Cada día laborable tiene una contribución proporcional a sus horas trabajadas,
    y se normaliza dividiendo entre el promedio de horas laborables por día natural.
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
        h_ini = datetime.combine(dia, row["hora_inicio"])
        h_fin = datetime.combine(dia, row["hora_fin"])

        # Si el turno está completamente fuera del rango, lo saltamos
        if h_fin <= ts_inicio or h_ini >= ts_fin:
            continue

        # Calculamos la intersección entre el turno y el intervalo
        tramo_ini = max(ts_inicio, h_ini)
        tramo_fin = min(ts_fin, h_fin)

        if tramo_fin > tramo_ini:
            total_seg_laborales += (tramo_fin - tramo_ini).total_seconds()

    # Horas laborables promedio por día (usamos función que ya tienes)
    horas_por_dia = calcular_promedio_horas_laborables_por_dia(df_calend)
    if horas_por_dia == 0:
        return 0.0

    segundos_por_dia = horas_por_dia * 3600

    dias_laborales_decimal = total_seg_laborales / segundos_por_dia

    return round(dias_laborales_decimal, 2)


def calcular_promedio_horas_laborables_por_dia(df_calend):
    """
    Calcula cuántas horas laborables hay en promedio por día natural (según df_calend).
    """
    dfc = df_calend.copy()
    dfc["dia"] = pd.to_datetime(dfc["dia"]).dt.date
    # Duración de cada turno en horas
    dfc["hora_inicio"] = pd.to_datetime(dfc["hora_inicio"], format="%H:%M:%S").dt.time
    dfc["hora_fin"]    = pd.to_datetime(dfc["hora_fin"],    format="%H:%M:%S").dt.time

    dfc["horas"] = dfc.apply(
        lambda row: (datetime.combine(row["dia"], row["hora_fin"]) - 
                      datetime.combine(row["dia"], row["hora_inicio"])).total_seconds() / 3600,
        axis=1
    )

    horas_por_dia = dfc.groupby("dia")["horas"].sum()
    total_horas = horas_por_dia.sum()
    ndias = len(horas_por_dia)

    if ndias == 0:
        return 0.0

    return round(total_horas / ndias, 2)
