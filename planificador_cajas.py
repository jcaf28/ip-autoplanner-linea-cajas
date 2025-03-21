import pandas as pd
import pulp
from datetime import datetime, timedelta
import time

from src.utils import leer_datos, escribir_resultados, check_situacion_inicial

# =========================================================================
# 1) Compresión del calendario
# =========================================================================
def comprimir_calendario(df_calend):
    df_calend = df_calend.copy()
    df_calend = df_calend.sort_values(by=["dia", "hora_inicio"])

    intervals = []
    acumulado = 0.0
    capacity_per_interval = []

    for _, row in df_calend.iterrows():
        dia = row["dia"]
        hi = row["hora_inicio"]
        hf = row["hora_fin"]
        if isinstance(hi, str):
            hi = datetime.strptime(hi, "%H:%M:%S").time()
        if isinstance(hf, str):
            hf = datetime.strptime(hf, "%H:%M:%S").time()

        cap = row["cant_operarios"]
        dt_ini = datetime(dia.year, dia.month, dia.day, hi.hour, hi.minute, hi.second)
        dt_fin = datetime(dia.year, dia.month, dia.day, hf.hour, hf.minute, hf.second)

        dur_h = (dt_fin - dt_ini).total_seconds() / 3600.0
        if dur_h <= 0:
            continue

        comp_start = acumulado
        comp_end   = acumulado + dur_h
        intervals.append({
            "dt_inicio": dt_ini,
            "dt_fin": dt_fin,
            "comp_start": comp_start,
            "comp_end": comp_end
        })
        capacity_per_interval.append(cap)
        acumulado += dur_h

    def fn_comprimir(dt_real):
        if not intervals:
            return 0.0
        if dt_real < intervals[0]["dt_inicio"]:
            return 0.0
        for itv in intervals:
            if itv["dt_inicio"] <= dt_real <= itv["dt_fin"]:
                delta = (dt_real - itv["dt_inicio"]).total_seconds() / 3600.0
                return itv["comp_start"] + delta
            elif dt_real < itv["dt_inicio"]:
                return itv["comp_start"]
        return intervals[-1]["comp_end"]

    def fn_descomprimir(comp_t):
        if not intervals:
            return datetime(2025, 3, 1)
        if comp_t <= intervals[0]["comp_start"]:
            return intervals[0]["dt_inicio"]
        for itv in intervals:
            if itv["comp_start"] <= comp_t <= itv["comp_end"]:
                delta_h = comp_t - itv["comp_start"]
                return itv["dt_inicio"] + timedelta(hours=delta_h)
        return intervals[-1]["dt_fin"]

    total_h = intervals[-1]["comp_end"] if intervals else 0.0
    return intervals, fn_comprimir, fn_descomprimir, total_h, capacity_per_interval

# =========================================================================
# 2) Restricciones originales
# =========================================================================

def fijar_inicio_tareas_parciales(modelo, df_tareas, df_entregas, start, fn_comprimir):
    for _, row in df_tareas.iterrows():
        mat = row["material_padre"]
        t_id = row["id_interno"]
        pct = row.get("completada_porcentaje", 0.0)
        if 0 < pct < 1:
            fecha_rec = df_entregas.loc[df_entregas["referencia"] == mat, "fecha_recepcion_materiales"].iloc[0]
            rec_ts = fn_comprimir(fecha_rec)
            modelo += start[(mat, t_id)] == rec_ts

def restriccion_precedencia(modelo, df_tareas, start, end):
    for _, row in df_tareas.iterrows():
        mat = row["material_padre"]
        t_id = row["id_interno"]
        if not pd.isnull(row["predecesora"]):
            lista_preds = [int(x.strip()) for x in str(row["predecesora"]).split(";")]
            for p_id in lista_preds:
                if (mat, p_id) not in end:
                    raise ValueError(f"No existe la tarea predecesora {p_id} para {mat}-{t_id}")
                modelo += end[(mat, p_id)] <= start[(mat, t_id)]

def restriccion_no_iniciar_antes_recepcion(modelo, df_entregas, df_tareas, start, fn_comprimir):
    for _, row in df_tareas.iterrows():
        mat = row["material_padre"]
        t_id = row["id_interno"]
        fecha_rec = df_entregas.loc[df_entregas["referencia"] == mat, "fecha_recepcion_materiales"].iloc[0]
        rec_ts = fn_comprimir(fecha_rec)
        modelo += start[(mat, t_id)] >= rec_ts

def restriccion_entrega_a_tiempo(modelo, df_entregas, df_tareas, end, retraso, fn_comprimir):
    for ref in df_entregas["referencia"].unique():
        fecha_limite = df_entregas.loc[df_entregas["referencia"] == ref, "fecha_entrega"].iloc[0]
        entrega_ts = fn_comprimir(fecha_limite)

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

# =========================================================================
# 3) Restricciones de duración y asignación de operarios
# =========================================================================

def restriccion_duracion_variable_ops(modelo, df_tareas, start, end, dur_task, x_k, dur_op):
    """
    - dur_op[(mat,t)] = suma de (tiempo_operario_rest / k)*x_k
    - dur_task[(mat,t)] >= dur_op[(mat,t)], >= t_robot*(1-pct), >= t_verif*(1-pct)
    - end[(mat,t)] = start + dur_task
    """
    for _, row in df_tareas.iterrows():
        mat   = row["material_padre"]
        t_id  = row["id_interno"]
        t_op  = row.get("tiempo_operario", 0) or 0
        t_robot = row.get("tiempo_robot", 0) or 0
        t_verif = row.get("tiempo_verificado", 0) or 0
        pct = row.get("completada_porcentaje", 0.0)
        if pct > 1.0:
            pct = 1.0

        # Si la tarea no requiere operarios (p.ej. verificado, t_op=0, etc.),
        # forzamos dur_op=0 y no usamos x_k
        # (ya habremos evitado crearlas o las fijamos a 0).
        t_op_rest = t_op*(1 - pct)
        if t_op_rest <= 1e-9:
            # Sin trabajo de operarios
            modelo += dur_op[(mat, t_id)] == 0
        else:
            # Caso normal: la tarea sí tiene parte de operarios
            max_ops = int(row["num_operarios_max"]) if not pd.isnull(row["num_operarios_max"]) else 1
            modelo += dur_op[(mat, t_id)] == pulp.lpSum(
                (t_op_rest / k)* x_k[(mat, t_id, k)]
                for k in range(1, max_ops + 1)
            )

        # dur_task >= dur_op, >= t_robot*(1-pct), >= t_verif*(1-pct)
        modelo += dur_task[(mat, t_id)] >= dur_op[(mat, t_id)]
        modelo += dur_task[(mat, t_id)] >= (t_robot * (1 - pct))
        modelo += dur_task[(mat, t_id)] >= (t_verif * (1 - pct))

        # end = start + dur_task
        modelo += end[(mat, t_id)] == start[(mat, t_id)] + dur_task[(mat, t_id)]

def restriccion_eleccion_num_operarios(modelo, df_tareas, x_k):
    """
    Si la tarea requiere operarios, sum_k x_k = 1;
    si NO requiere operarios (tiempo_operario=0 o max=0),
    no creamos variables o las fijamos a 0.
    """
    for _, row in df_tareas.iterrows():
        mat    = row["material_padre"]
        t_id   = row["id_interno"]
        max_ops = row.get("num_operarios_max", 0)
        if pd.isnull(max_ops):
            max_ops = 0
        max_ops = int(max_ops)

        t_op   = row.get("tiempo_operario", 0) or 0
        pct    = row.get("completada_porcentaje", 0.0)
        if pct > 1: pct=1
        t_op_rest = t_op*(1 - pct)

        # Solo si t_op_rest>0 y max_ops>0 generamos la restricción sum_k x_k=1
        # En caso contrario, no se crea restricción (o se fija x_k=0).
        if (t_op_rest > 1e-9) and (max_ops > 0):
            modelo += pulp.lpSum(
                [x_k[(mat, t_id, k)] for k in range(1, max_ops+1)]
            ) == 1
        else:
            # Forzamos x_k=0 en todas las combinaciones, si es que existen
            # para evitar que el solver las use indebidamente
            for k in range(1, max_ops+1):
                var_x = x_k.get((mat, t_id, k), None)
                if var_x is not None:
                    modelo += var_x == 0

# =========================================================================
# 4) Capacidad de operarios por turno (pairwise, bigM)
# =========================================================================

def get_assigned_ops_expr(mat, t_id, max_k, x_k):
    return pulp.lpSum(k * x_k[(mat, t_id, k)] for k in range(1, max_k+1)
                      if (mat, t_id, k) in x_k)

def restriccion_capacidad_operarios_por_turno(modelo, df_tareas, start, end,
                                              intervals, capacity_per_interval,
                                              x_k):
    """
    Si dos tareas se solapan en un bloque i, la suma de operarios asignados
    no puede exceder capacity_per_interval[i]. Si la suma > cap_i,
    se aplica una restricción de orden para que no se solapen.
    """

    df_tareas_idx = df_tareas.reset_index(drop=True)
    M = 1e6
    order_block = {}

    for i in range(len(intervals)):
        block_start = intervals[i]["comp_start"]
        block_end   = intervals[i]["comp_end"]
        cap_i       = capacity_per_interval[i]

        for idx_a in range(len(df_tareas_idx)):
            rowA = df_tareas_idx.loc[idx_a]
            matA = rowA["material_padre"]
            tA   = rowA["id_interno"]
            maxA = int(rowA.get("num_operarios_max", 0))

            for idx_b in range(idx_a+1, len(df_tareas_idx)):
                rowB = df_tareas_idx.loc[idx_b]
                matB = rowB["material_padre"]
                tB   = rowB["id_interno"]
                maxB = int(rowB.get("num_operarios_max", 0))

                # Calculamos la expresión de operarios sumados
                ops_sum_expr = get_assigned_ops_expr(matA, tA, maxA, x_k) \
                              + get_assigned_ops_expr(matB, tB, maxB, x_k)

                # Si la suma MÁXIMA (maxA + maxB) <= cap_i, no hay problema: pueden solaparse sin pasarse de cap.
                if (maxA + maxB) > cap_i:
                    # Creamos la var binaria de orden
                    var = pulp.LpVariable(f"orderBlock_{i}_{matA}_{tA}_{matB}_{tB}", cat=pulp.LpBinary)
                    order_block[(i, matA, tA, matB, tB)] = var

                    # si ops_sum_expr > cap_i => var=1 => forzamos que no se solapen
                    modelo += ops_sum_expr <= cap_i + M*var

                    # "No solape" => startB >= endA - M*(1-var), etc.
                    modelo += start[(matB, tB)] >= end[(matA, tA)] - M*(1 - var)
                    modelo += start[(matA, tA)] >= end[(matB, tB)] - M*var

# =========================================================================
# 5) Montamos y resolvemos el modelo
# =========================================================================

def armar_modelo(datos):
    df_entregas  = datos["df_entregas"]
    df_tareas    = datos["df_tareas"]
    intervals    = datos["intervals"]
    capacity     = datos["capacity_per_interval"]
    fn_comprimir = datos["fn_comprimir"]

    modelo = pulp.LpProblem("Planificacion_VariableOps", pulp.LpMinimize)

    pedidos = df_entregas["referencia"].unique().tolist()

    start    = {}
    end      = {}
    retraso  = {}
    dur_task = {}
    dur_op   = {}
    x_k      = {}

    # 1) Crear variables start, end, retraso, dur_task, dur_op para cada tarea
    for p in pedidos:
        df_mat = df_tareas[df_tareas["material_padre"] == p]
        for t_id in df_mat["id_interno"].unique():
            start[(p, t_id)]    = pulp.LpVariable(f"start_{p}_{t_id}", lowBound=0)
            end[(p, t_id)]      = pulp.LpVariable(f"end_{p}_{t_id}",   lowBound=0)
            dur_task[(p, t_id)] = pulp.LpVariable(f"durTask_{p}_{t_id}", lowBound=0)
            dur_op[(p, t_id)]   = pulp.LpVariable(f"durOp_{p}_{t_id}",   lowBound=0)

        retraso[p] = pulp.LpVariable(f"retraso_{p}", lowBound=0)

    # 2) Crear x_k sólo para tareas que realmente tengan num_operarios_max>0
    for idx, row in df_tareas.iterrows():
        mat = row["material_padre"]
        t_id= row["id_interno"]
        max_ops = row.get("num_operarios_max", 0)
        if pd.isnull(max_ops):
            max_ops = 0
        max_ops = int(max_ops)
        if max_ops < 1:
            continue  # No creamos variables x_k
        # Creamos x_k(1..max_ops) para esa tarea
        for k in range(1, max_ops+1):
            nombre = f"x_k_{mat}_{t_id}_{k}"
            x_k[(mat, t_id, k)] = pulp.LpVariable(nombre, cat=pulp.LpBinary)

    print('leyendo restricciones...')
    # 3) Restricciones
    #    A) Elección de num_operarios
    restriccion_eleccion_num_operarios(modelo, df_tareas, x_k)
    #    B) Duración variable
    restriccion_duracion_variable_ops(modelo, df_tareas, start, end, dur_task, x_k, dur_op)
    #    C) Tareas en curso
    fijar_inicio_tareas_parciales(modelo, df_tareas, df_entregas, start, fn_comprimir)
    #    D) Precedencia
    restriccion_precedencia(modelo, df_tareas, start, end)
    #    E) No iniciar antes de recepción
    restriccion_no_iniciar_antes_recepcion(modelo, df_entregas, df_tareas, start, fn_comprimir)
    #    F) Capacidad de operarios por turno
    restriccion_capacidad_operarios_por_turno(modelo, df_tareas, start, end, intervals, capacity, x_k)
    #    G) Fechas de entrega
    restriccion_entrega_a_tiempo(modelo, df_entregas, df_tareas, end, retraso, fn_comprimir)

    print('función objetivo...')

    # 4) Función objetivo: minimizar la suma de retrasos
    modelo += pulp.lpSum([retraso[p] for p in pedidos]), "Minimize_Total_Tardiness"

    return modelo, start, end, retraso, dur_task


def resolver_modelo(modelo):
    solver = pulp.HiGHS_CMD(
        msg=True,
        timeLimit=300,  # por si el modelo es grande
        mip=True
    )
    print("Resolviendo el modelo con HiGHS...")
    modelo.solve(solver)
    print("Estado:", pulp.LpStatus[modelo.status])
    if modelo.status == pulp.LpStatusOptimal:
        print("Valor objetivo:", pulp.value(modelo.objective))
    else:
        print("⚠ No se encontró solución óptima.")
    return modelo

# =========================================================================
# 6) Flujo principal
# =========================================================================

def main():
    print("1) Leyendo datos...")
    ruta = "archivos/db_dev/Datos_entrada_v10.xlsx"
    datos = leer_datos(ruta)

    print("2) Revisando consistencia inicial...")
    check_situacion_inicial(datos["df_tareas"], datos["df_capacidades"])

    print("3) Comprimiendo calendario...")
    intervals, fn_comp, fn_decomp, total_h, capacity = comprimir_calendario(datos["df_calend"])
    datos["intervals"]               = intervals
    datos["capacity_per_interval"]   = capacity
    datos["fn_comprimir"]            = fn_comp
    datos["fn_descomprimir"]         = fn_decomp
    datos["total_horas_comprimidas"] = total_h

    print("4) Creando modelo...")
    modelo, start, end, retraso, dur_task = armar_modelo(datos)

    print("5) Guardando modelo LP para depurar...")
    modelo.writeLP("debug_model_variable_ops.lp")

    print("6) Resolviendo...")
    resolver_modelo(modelo)

    print("7) Guardando resultados...")
    escribir_resultados(
        modelo, start, end, ruta,
        datos["df_tareas"], datos["df_entregas"], datos["df_calend"],
        datos["fn_descomprimir"],
        datos["df_capacidades"]
    )
    print("¡Terminado!")


if __name__ == "__main__":
    main()
