import pandas as pd
import pulp
from datetime import datetime, timedelta
import time

from src.utils import leer_datos, escribir_resultados, check_situacion_inicial

# --------------------------------------------------------------------------------
# 1) COMPRESIÓN Y DESCOMPRESIÓN DEL CALENDARIO
# --------------------------------------------------------------------------------
def comprimir_calendario(df_calend):
    """
    Toma el calendario de turnos (fecha, hora_inicio, hora_fin) y construye una
    línea de tiempo comprimida, sólo con las horas efectivas de trabajo.
    
    Devuelve:
      - intervals: lista de diccionarios con:
            {
              "dt_inicio": datetime real,
              "dt_fin":    datetime real,
              "comp_start": hora_comprimida_inicio,
              "comp_end":   hora_comprimida_fin
            }
      - fn_comprimir(dt: datetime) -> float
      - fn_descomprimir(comp_t: float) -> datetime
      - total_horas_comprimidas (float)
    """
    # Ordenamos por fecha y turno (asumiendo que ya viene ordenado, pero por si acaso)
    df_calend = df_calend.copy()
    df_calend = df_calend.sort_values(by=["dia", "hora_inicio"])

    intervals = []
    acumulado = 0.0  # Acumula las horas comprimidas

    for _, row in df_calend.iterrows():
        dia = row["dia"]  # date
        hi = row["hora_inicio"]  # tipo datetime.time
        hf = row["hora_fin"]     # tipo datetime.time

        dt_ini = datetime(dia.year, dia.month, dia.day, hi.hour, hi.minute, hi.second)
        dt_fin = datetime(dia.year, dia.month, dia.day, hf.hour, hf.minute, hf.second)

        dur_h = (dt_fin - dt_ini).total_seconds() / 3600.0
        if dur_h <= 0:
            continue

        comp_start = acumulado
        comp_end = acumulado + dur_h
        intervals.append({
            "dt_inicio": dt_ini,
            "dt_fin": dt_fin,
            "comp_start": comp_start,
            "comp_end": comp_end
        })
        acumulado += dur_h

    def fn_comprimir(dt_real):
        """
        Convierte un datetime real en su correspondiente 'hora comprimida'.
        Si cae fuera de los intervalos de trabajo, se lleva al siguiente hueco disponible.
        Si dt_real < primer intervalo, devolvemos 0.
        """
        if not intervals:
            return 0.0

        # Si es anterior al primer turno
        if dt_real < intervals[0]["dt_inicio"]:
            return 0.0

        for itv in intervals:
            if itv["dt_inicio"] <= dt_real <= itv["dt_fin"]:
                # Está dentro de un turno
                delta = (dt_real - itv["dt_inicio"]).total_seconds() / 3600.0
                return itv["comp_start"] + delta
            elif dt_real < itv["dt_inicio"]:
                # Está en un hueco muerto (fuera de turno), saltamos al inicio del turno
                return itv["comp_start"]

        # Si es posterior al último turno, se redondea al final
        return intervals[-1]["comp_end"]

    def fn_descomprimir(comp_t):
        """
        Convierte una 'hora comprimida' a un datetime real.
        Si comp_t excede el último turno, devolvemos el final del último turno.
        """
        if not intervals:
            # No hay turnos; retornar algo por defecto
            return datetime(2025, 3, 1)

        if comp_t <= intervals[0]["comp_start"]:
            return intervals[0]["dt_inicio"]

        for itv in intervals:
            if itv["comp_start"] <= comp_t <= itv["comp_end"]:
                # está dentro de este turno
                delta_h = comp_t - itv["comp_start"]
                return itv["dt_inicio"] + timedelta(hours=delta_h)
        # Si supera el último tramo
        return intervals[-1]["dt_fin"]

    return intervals, fn_comprimir, fn_descomprimir, acumulado

# --------------------------------------------------------------------------------
# 2) RESTRICCIONES
# --------------------------------------------------------------------------------
def fijar_inicio_tareas_parciales(modelo, df_tareas, df_entregas, start, fn_comprimir):
    """
    Para cada tarea en curso (0 < completada_porcentaje < 1), se fija su inicio
    en el instante comprimido correspondiente a la fecha de recepción del material.
    """
    for _, row in df_tareas.iterrows():
        mat = row["material_padre"]
        t_id = row["id_interno"]
        pct = row.get("completada_porcentaje", 0.0)
        if 0 < pct < 1:
            # Obtener la fecha de recepción para ese material
            fecha_rec = df_entregas.loc[df_entregas["referencia"] == mat, "fecha_recepcion_materiales"].iloc[0]
            rec_ts = fn_comprimir(fecha_rec)
            modelo += start[(mat, t_id)] == rec_ts


def restriccion_duracion(modelo, df_tareas, start, end):
    """
    end = start + dur_rest, donde dur_rest = dur_total * (1 - completada_porcentaje).
    El dur_total depende de (tiempo_operario, tiempo_robot, tiempo_verificado)
    y se asume que operario+robot suceden en paralelo (dur_total = max(t_op, t_robot, t_verif)).
    """
    for _, row in df_tareas.iterrows():
        mat = row["material_padre"]
        t_id = row["id_interno"]

        # Número de operarios, si aplica
        n_ops = 1
        if "num_operarios_fijos" in df_tareas.columns and not pd.isnull(row["num_operarios_fijos"]):
            n_ops = float(row["num_operarios_fijos"])
            if n_ops < 1:
                n_ops = 1

        dur_op = 0.0
        if not pd.isnull(row["tiempo_operario"]) and row["tiempo_operario"] > 0:
            dur_op = row["tiempo_operario"] / n_ops

        dur_robot = 0.0
        if not pd.isnull(row["tiempo_robot"]) and row["tiempo_robot"] > 0:
            dur_robot = row["tiempo_robot"]

        dur_verif = 0.0
        if not pd.isnull(row["tiempo_verificado"]) and row["tiempo_verificado"] > 0:
            dur_verif = row["tiempo_verificado"]

        # Duración teórica total (antes de restar el avance)
        dur_total = max(dur_op, dur_robot, dur_verif)

        # Porcentaje completado
        pct = row.get("completada_porcentaje", 0.0)
        if pct > 1.0:
            pct = 1.0  # Por si por error viniera mayor a 1

        # Duración restante a planificar
        dur_rest = dur_total * (1 - pct)

        # end = start + dur_rest
        modelo += end[(mat, t_id)] == start[(mat, t_id)] + dur_rest


def restriccion_precedencia(modelo, df_tareas, start, end):
    """
    end(predecesora) <= start(tarea). Si hay múltiples predecesoras, la tarea no arranca
    hasta que TODAS finalicen.
    """
    for _, row in df_tareas.iterrows():
        mat = row["material_padre"]
        t_id = row["id_interno"]

        if not pd.isnull(row["predecesora"]):
            lista_preds = [int(x.strip()) for x in str(row["predecesora"]).split(";")]
            for p_id in lista_preds:
                if (mat, p_id) not in end:
                    raise ValueError(
                        f"La tarea {t_id} del material {mat} tiene predecesora {p_id}, "
                        f"pero no existe en 'end'. Revisa la hoja TAREAS."
                    )
                modelo += end[(mat, p_id)] <= start[(mat, t_id)]


def restriccion_no_iniciar_antes_recepcion(modelo, df_entregas, df_tareas, start, fn_comprimir):
    """
    start(tarea) >= fecha_recepcion (en tiempo comprimido).
    """
    for _, row in df_tareas.iterrows():
        mat = row["material_padre"]
        t_id = row["id_interno"]

        fecha_rec = df_entregas.loc[df_entregas["referencia"] == mat, "fecha_recepcion_materiales"].iloc[0]
        rec_ts = fn_comprimir(fecha_rec)
        modelo += start[(mat, t_id)] >= rec_ts


def restriccion_entrega_a_tiempo(modelo, df_entregas, df_tareas, end, retraso, fn_comprimir):
    """
    end(tarea_final) <= fecha_entrega_comprimida + retraso[pedido].
    """
    for ref in df_entregas["referencia"].unique():
        fecha_limite = df_entregas.loc[df_entregas["referencia"] == ref, "fecha_entrega"].iloc[0]
        entrega_ts = fn_comprimir(fecha_limite)

        # Buscamos las tareas "finales" (aquellas que no son predecesoras de otras)
        df_mat = df_tareas[df_tareas["material_padre"] == ref]
        finales = []
        all_preds = set()

        for _, row in df_mat.iterrows():
            if not pd.isnull(row["predecesora"]):
                for pp in str(row["predecesora"]).split(";"):
                    all_preds.add(int(pp.strip()))

        for t_id in df_mat["id_interno"].unique():
            if t_id not in all_preds:
                finales.append(t_id)

        for t_id in finales:
            modelo += end[(ref, t_id)] <= entrega_ts + retraso[ref]


def restriccion_capacidad_zonas(modelo, df_tareas, start, end):
    """
    Igual que antes: si la zona tiene capacidad 1, no se pueden solapar las tareas en esa zona.
    Si la capacidad es 2, se permite solapar sólo si son del mismo tipo (OPERATIVA vs VERIFICADO), etc.
    """
    ZONA_CAP = {
        "PREVIOS": 1,
        "UTILLAJES": 1,
        "ROBOT": 1,
        "SOPORTERIA": 2,     # 2 elementos a la vez, pero con restricción de tipo
        "CATEDRAL": 1,
        "SOLDADURA FINAL": 1,
        "INSPECCION FINAL": 1
    }
    M = 1e5
    order_zona = {}

    df_tareas_idx = df_tareas.reset_index(drop=True)
    lista_tuplas = []

    for i in range(len(df_tareas_idx)):
        for j in range(i + 1, len(df_tareas_idx)):
            rowi = df_tareas_idx.loc[i]
            rowj = df_tareas_idx.loc[j]

            zona_i, zona_j = rowi["nom_ubicacion"], rowj["nom_ubicacion"]
            tipo_i, tipo_j = rowi["tipo_tarea"], rowj["tipo_tarea"]
            mat_i, mat_j = rowi["material_padre"], rowj["material_padre"]
            t_i, t_j = rowi["id_interno"], rowj["id_interno"]

            cap_i = ZONA_CAP.get(zona_i, 1)
            cap_j = ZONA_CAP.get(zona_j, 1)

            if zona_i == zona_j:
                # Capacidad 1 -> no solapan
                if cap_i == 1:
                    var = pulp.LpVariable(f"zonaOrder_{mat_i}_{t_i}_{mat_j}_{t_j}", cat=pulp.LpBinary)
                    order_zona[(mat_i, t_i, mat_j, t_j)] = var
                    lista_tuplas.append((mat_i, t_i, mat_j, t_j))

                # Capacidad > 1 -> sólo solapan si el tipo_tarea es el mismo
                elif cap_i > 1 and tipo_i != tipo_j:
                    var = pulp.LpVariable(f"zonaOrder_{mat_i}_{t_i}_{mat_j}_{t_j}", cat=pulp.LpBinary)
                    order_zona[(mat_i, t_i, mat_j, t_j)] = var
                    lista_tuplas.append((mat_i, t_i, mat_j, t_j))

    # Aplicar restricciones
    for (mi, ti, mj, tj) in lista_tuplas:
        modelo += start[(mj, tj)] >= end[(mi, ti)] - M * (1 - order_zona[(mi, ti, mj, tj)])
        modelo += start[(mi, ti)] >= end[(mj, tj)] - M * order_zona[(mi, ti, mj, tj)]


def restriccion_operarios(modelo, df_tareas, start, end, df_parametros):
    """
    Cantidad de operarios fija, determinada en los parámetros de. 
    Se hace un control pairwise: si la suma de n_ops (tarea i + tarea j) > 8, 
    entonces dichas tareas no pueden solaparse.
    
    NOTA: Esto es un enfoque simplificado. Si quieres permitir que 3 ó más tareas se 
    solapen (siempre que la suma no supere 8), habría que modelar de forma más compleja.
    """
    MAX_OP = int(df_parametros.loc[df_parametros["parametro"] == "cant_operarios", "valor"].iloc[0])
    M = 1e5
    order_ops = {}

    df_tareas_idx = df_tareas.reset_index(drop=True)
    lista_pairs = []

    for i in range(len(df_tareas_idx)):
        for j in range(i + 1, len(df_tareas_idx)):
            rowi = df_tareas_idx.loc[i]
            rowj = df_tareas_idx.loc[j]
            mat_i, t_i = rowi["material_padre"], rowi["id_interno"]
            mat_j, t_j = rowj["material_padre"], rowj["id_interno"]

            # Calcula la "demanda" de operarios de cada tarea
            n_ops_i = 1
            if "num_operarios_fijos" in rowi and not pd.isnull(rowi["num_operarios_fijos"]):
                n_ops_i = float(rowi["num_operarios_fijos"])
                if n_ops_i < 1:
                    n_ops_i = 1

            n_ops_j = 1
            if "num_operarios_fijos" in rowj and not pd.isnull(rowj["num_operarios_fijos"]):
                n_ops_j = float(rowj["num_operarios_fijos"])
                if n_ops_j < 1:
                    n_ops_j = 1

            # Si la suma excede 8, no pueden solaparse
            if (n_ops_i + n_ops_j) > MAX_OP:
                var = pulp.LpVariable(f"opsOrder_{mat_i}_{t_i}_{mat_j}_{t_j}", cat=pulp.LpBinary)
                order_ops[(mat_i, t_i, mat_j, t_j)] = var
                lista_pairs.append((mat_i, t_i, mat_j, t_j))

    # Restricciones pairwise
    for (mi, ti, mj, tj) in lista_pairs:
        modelo += start[(mj, tj)] >= end[(mi, ti)] - M * (1 - order_ops[(mi, ti, mj, tj)])
        modelo += start[(mi, ti)] >= end[(mj, tj)] - M * order_ops[(mi, ti, mj, tj)]


# --------------------------------------------------------------------------------
# 3) CREAR Y RESOLVER EL MODELO
# --------------------------------------------------------------------------------
def armar_modelo(datos):
    df_entregas = datos["df_entregas"]
    df_tareas = datos["df_tareas"]
    fn_comprimir = datos["fn_comprimir"]

    modelo = pulp.LpProblem("Planificacion_Completa", pulp.LpMinimize)
    pedidos = df_entregas["referencia"].unique().tolist()

    # Crear variables start, end y retraso
    start = {}
    end = {}
    retraso = {}

    for p in pedidos:
        df_mat = df_tareas[df_tareas["material_padre"] == p]
        for t_id in df_mat["id_interno"].unique():
            start[(p, t_id)] = pulp.LpVariable(f"start_{p}_{t_id}", lowBound=0)
            end[(p, t_id)] = pulp.LpVariable(f"end_{p}_{t_id}", lowBound=0)
        retraso[p] = pulp.LpVariable(f"retraso_{p}", lowBound=0)

    # Restricción de duración (con duración restante en función del avance)
    restriccion_duracion(modelo, df_tareas, start, end)

    # Fijar el inicio para las tareas en curso según la fecha de recepción
    fijar_inicio_tareas_parciales(modelo, df_tareas, df_entregas, start, fn_comprimir)

    # Resto de restricciones
    restriccion_precedencia(modelo, df_tareas, start, end)
    restriccion_no_iniciar_antes_recepcion(modelo, df_entregas, df_tareas, start, fn_comprimir)
    restriccion_capacidad_zonas(modelo, df_tareas, start, end)
    restriccion_operarios(modelo, df_tareas, start, end, datos["df_parametros"])
    restriccion_entrega_a_tiempo(modelo, df_entregas, df_tareas, end, retraso, fn_comprimir)

    # Función objetivo
    modelo += pulp.lpSum(retraso.values()), "Minimize_Total_Tardiness"

    return modelo, start, end, retraso


def resolver_modelo(modelo):
    solver = pulp.PULP_CBC_CMD(
        msg=True,        # Activa logs detallados
        timeLimit=120,   # Máximo 2 minutos
        gapRel=0.05,     # Permite soluciones con un 5% de tolerancia respecto al óptimo
        presolve=True,   # Reduce tamaño del problema antes de resolver
        cuts=True,       # Habilita generación de cortes adicionales
        mip=True         # Indica que estamos resolviendo un problema de programación entera
    )
    modelo.solve(solver)
    return modelo


# --------------------------------------------------------------------------------
# 4) FLUJO PRINCIPAL
# --------------------------------------------------------------------------------
import time

def main():
    start_time = time.time()  # Marca inicial de tiempo

    print("🔹 Cargando datos de entrada...")
    ruta = "archivos\db_dev\Datos_entrada_v9.xlsx"
    datos = leer_datos(ruta)
    print(f"✅ Datos cargados en {time.time() - start_time:.2f} segundos.")

    print("🔹 Verificando consistencia de la situación inicial...")
    check_situacion_inicial(datos["df_tareas"], datos["df_capacidades"])
    print(f"✅ Situación inicial verificada en {time.time() - start_time:.2f} segundos.")

    print("🔹 Comprimiendo calendario de turnos...")
    cal_start = time.time()
    intervals, fn_comp, fn_decomp, total_h = comprimir_calendario(datos["df_calend"])
    datos["fn_comprimir"] = fn_comp
    datos["fn_descomprimir"] = fn_decomp
    datos["total_horas_comprimidas"] = total_h
    print(f"✅ Compresión del calendario completada en {time.time() - cal_start:.2f} segundos.")

    print("🔹 Armando modelo de optimización...")
    model_start = time.time()
    modelo, start, end, retraso = armar_modelo(datos)
    print(f"✅ Modelo armado en {time.time() - model_start:.2f} segundos.")

    print("🔹 Guardando modelo en archivos para depuración...")
    modelo.writeLP("debug_model.lp")  # Guardar modelo en formato LP
    modelo.writeMPS("debug_model.mps")  # Guardar modelo en formato MPS

    print("🔹 Resolviendo modelo de optimización...")
    solver_start = time.time()
    resolver_modelo(modelo)
    print(f"✅ Modelo resuelto en {time.time() - solver_start:.2f} segundos.")

    print("🔹 Guardando resultados y generando diagrama de Gantt...")
    escribir_resultados(
        modelo, start, end, ruta,
        datos["df_tareas"], datos["df_entregas"], datos["df_calend"],
        fn_decomp,
        datos["df_capacidades"]  # Pasamos el DataFrame de capacidades
    )

if __name__ == "__main__":
    main()
