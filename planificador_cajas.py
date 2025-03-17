# planificador_cajas.py
# --------------------------------------------------------------------------------
# Ejemplo de planificación con restricciones de:
#  - Precedencia de tareas
#  - Capacidad de zona (1 elemento, 2 elementos, etc.)
#  - No solapar tareas incompatibles en la misma zona
#  - Calendario de turnos y horas de trabajo
#  - Disponibilidad de operarios
#  - Tareas de verificación que no consumen operarios
#
# Uso:
#   python planificador_cajas.py
# --------------------------------------------------------------------------------

import pandas as pd
import pulp
from datetime import datetime

from src.utils import leer_datos

# -----------------------------------------------------------------------
# 2) APLICAR RESTRICCIONES ESPECÍFICAS
# -----------------------------------------------------------------------
def restriccion_duracion(modelo, df_tareas, start, end, df_entregas):
    """
    end = start + dur, y no se inicia antes de la recepción de materiales.
    """
    for (idx, row) in df_tareas.iterrows():
        mat = row["material_padre"]
        t_id = row["id_interno"]
        # Calculamos la duración según el tiempo requerido
        # Escogemos la mayor de las 3, o sumamos, o la que aplique:
        # (Aquí, como ejemplo: si la tarea requiere robot => tiempo_robot; si verificado => tiempo_verificado, etc.
        #  Podrías combinar si se necesita.)
        dur = 0
        if not pd.isnull(row["tiempo_operario"]):
            dur = max(dur, float(row["tiempo_operario"]))
        if not pd.isnull(row["tiempo_robot"]):
            dur = max(dur, float(row["tiempo_robot"]))
        if not pd.isnull(row["tiempo_verificado"]):
            dur = max(dur, float(row["tiempo_verificado"]))

        # Conectamos con la variable del modelo
        for (_, entreg_row) in df_entregas.iterrows():
            if entreg_row["referencia"] == mat:
                rec_date = entreg_row["fecha_recepcion_materiales"]
                # Convertimos fecha_recepcion_materiales a horas desde un origen
                rec_ts = (rec_date - datetime(2025,3,1)).total_seconds()/3600
                # end = start + dur
                modelo += end[(mat, t_id)] == start[(mat, t_id)] + dur
                # No empezar antes de la recepción
                modelo += start[(mat, t_id)] >= rec_ts

def restriccion_precedencia(modelo, df_tareas, start, end):
    """
    end(predecesora) <= start(tarea).
    Maneja múltiples predecesoras separadas por ';'.
    Hasta que *todas* las predecesoras no terminan, no se puede empezar la tarea.
    """
    for _, row in df_tareas.iterrows():
        mat = row["material_padre"]
        t_id = row["id_interno"]
        if not pd.isnull(row["predecesora"]):
            # Parseamos la lista de predecesoras
            lista_preds = [int(x.strip()) for x in str(row["predecesora"]).split(";")]
            for p_id in lista_preds:
                # Asegurarnos de que exista (mat, p_id) en end
                if (mat, p_id) not in end:
                    # Puedes lanzar un error, o ignorar la restricción. Pero
                    # lo correcto es depurar los datos para que sí exista:
                    raise ValueError(
                        f"La tarea {t_id} del material {mat} tiene predecesora {p_id}, "
                        f"pero no existe en 'end'. Revisa la hoja TAREAS."
                    )
                modelo += end[(mat, p_id)] <= start[(mat, t_id)]


def restriccion_calendario(modelo, df_calend, start, end):
    """
    Ejemplo simplificado:
    - No se trabaja fuera de los rangos de turnos
    - Suponemos que la tarea se puede partir entre turnos (en la realidad, se modelaría de otro modo).
    - Aquí usaremos la idea de 'start' y 'end' deben caer dentro del rango global de horas laborables.
    """
    # Rango global
    min_ts = float("inf")
    max_ts = float("-inf")

    for (_, row) in df_calend.iterrows():
        dia_val = row["dia"]  # es un datetime.date
        day_dt = datetime(dia_val.year, dia_val.month, dia_val.day)
        hi_str = row["hora_inicio"]  # hh:mm:ss
        hf_str = row["hora_fin"]
        # Convertir a datetimes
        hi = datetime.strptime(str(hi_str), "%H:%M:%S").time()
        hf = datetime.strptime(str(hf_str), "%H:%M:%S").time()
        dt_ini = datetime(day_dt.year, day_dt.month, day_dt.day, hi.hour, hi.minute, hi.second)
        dt_fin = datetime(day_dt.year, day_dt.month, day_dt.day, hf.hour, hf.minute, hf.second)
        ts_ini = (dt_ini - datetime(2025,3,1)).total_seconds()/3600
        ts_fin = (dt_fin - datetime(2025,3,1)).total_seconds()/3600

        if ts_ini < min_ts: 
            min_ts = ts_ini
        if ts_fin > max_ts:
            max_ts = ts_fin

    # Forzamos que start/end estén dentro del horario global
    for (key, var) in start.items():
        modelo += var >= min_ts
    for (key, var) in end.items():
        modelo += var <= max_ts

def restriccion_entrega_a_tiempo(modelo, df_entregas, df_tareas, end):
    """
    end(tarea_final) <= fecha_entrega para cada pedido.
    Tarea final = la de id_interno máximo, o la que no aparezca como predecesora de ninguna.
    """
    for ref in df_entregas["referencia"].unique():
        fecha_limite = df_entregas.loc[df_entregas["referencia"]==ref, "fecha_entrega"].iloc[0]
        entrega_ts = (fecha_limite - datetime(2025,3,1)).total_seconds()/3600

        df_mat = df_tareas[df_tareas["material_padre"] == ref]
        # Buscamos tareas que no son predecesoras de nada => finales
        finales = []
        all_preds = set()
        for (_, row) in df_mat.iterrows():
            if not pd.isnull(row["predecesora"]):
                for pp in str(row["predecesora"]).split(";"):
                    all_preds.add(int(pp.strip()))
        for t_id in df_mat["id_interno"].unique():
            if t_id not in all_preds:
                finales.append(t_id)

        # end(tarea_final) <= entrega_ts
        for t_id in finales:
            modelo += end[(ref, t_id)] <= entrega_ts

def restriccion_capacidad_zonas(modelo, df_tareas, start, end):
    """
    Cada 'ubicacion' (zona) tiene una capacidad:
      - Z0, Z1 => 1, etc.
    Ejemplo simplificado de "no solapamiento" para capacidad=1:
      Si dos tareas comparten la misma zona, no se pueden solapar:
        end(i) <= start(j) OR end(j) <= start(i)
      => se modela con variables binarias o con la formulación disyuntiva:
         start(j) >= end(i) - M*(1 - x_ij)
         start(i) >= end(j) - M*(x_ij)
      Para no exceder 3 indentaciones, hacemos un pseudo Big-M:
    """
    ZONA_CAP = {
        "PREVIOS": 1,
        "UTILLAJES": 1,
        "ROBOT": 1,
        "SOPORTERIA": 2,      # 2 elementos a la vez, con matices
        "CATEDRAL": 1,
        "SOLDADURA FINAL": 1,
        "INSPECCION FINAL": 1
    }
    # M grande
    M = 1e5

    # Creamos variables binarias "order" para cada par de tareas que compartan zona
    # order[(i, j)] = 1 => la tarea i va antes que la j
    order = {}
    lista_tuplas = []
    df_tareas_idx = df_tareas.reset_index(drop=True)

    # Generamos pares (i, j) solo si zona y material_padre difieren, o no, y la zona es la misma.
    for i in range(len(df_tareas_idx)):
        for j in range(i+1, len(df_tareas_idx)):
            rowi = df_tareas_idx.loc[i]
            rowj = df_tareas_idx.loc[j]
            zona_i = rowi["nom_ubicacion"]
            zona_j = rowj["nom_ubicacion"]
            cap_i = ZONA_CAP.get(zona_i, 1)
            cap_j = ZONA_CAP.get(zona_j, 1)

            mat_i = rowi["material_padre"]
            mat_j = rowj["material_padre"]
            t_i   = rowi["id_interno"]
            t_j   = rowj["id_interno"]

            if zona_i == zona_j:
                # Si la capacidad es 1 => no puede haber solape
                # Si es 2 => puede haber 2 simultáneos, pero ojo con la restricción de "no mezclar verificado y soportería"
                # Simplificamos con "si cap=1 => no solape; si cap=2 => permitimos solape sin restricciones extra"
                if cap_i == 1:
                    # Definimos una binaria
                    order[(mat_i, t_i, mat_j, t_j)] = pulp.LpVariable(f"order_{mat_i}_{t_i}_{mat_j}_{t_j}", cat=pulp.LpBinary)
                    lista_tuplas.append((mat_i, t_i, mat_j, t_j))
                else:
                    # zona soporeria con cap=2 => no hacemos nada en este prototipo
                    pass

    for (mi, ti, mj, tj) in lista_tuplas:
        modelo += start[(mj, tj)] >= end[(mi, ti)] - (1e5)*(1 - order[(mi, ti, mj, tj)])
        modelo += start[(mi, ti)] >= end[(mj, tj)] - (1e5)*order[(mi, ti, mj, tj)]

def restriccion_operarios(modelo, df_tareas, df_calend, start, end):
    # Creamos lista de turnos con (dia, turno, ts_ini, ts_fin, operarios_disponibles)
    turnos = []
    for (_, row) in df_calend.iterrows():
        dia = pd.to_datetime(row["dia"])
        hora_inicio = row["hora_inicio"]
        hora_fin = row["hora_fin"]
        dt_ini = datetime.combine(dia, hora_inicio)
        dt_fin = datetime.combine(dia, hora_fin)
        ts_ini = (dt_ini - datetime(2025,3,1)).total_seconds()/3600
        ts_fin = (dt_fin - datetime(2025,3,1)).total_seconds()/3600
        operarios_disp = row["cantidad_operarios"]
        turnos.append((ts_ini, ts_fin, operarios_disp))

    # Para cada turno, limitamos operarios simultáneos
    for (ts_ini, ts_fin, operarios_disp) in turnos:
        operarios_en_turno = []
        for (idx, tarea) in df_tareas.iterrows():
            mat, t_id = tarea["material_padre"], tarea["id_interno"]
            tiempo_operario = tarea["tiempo_operario"]
            tiempo_robot = tarea["tiempo_robot"]

            # Número fijo de operarios simultáneos por tarea (asumamos que ya lo tienes definido en df_tareas)
            num_operarios_simult = tarea.get("num_operarios_fijos", 1)  # Esta columna debe existir

            # Duración real
            duracion_real = tiempo_operario / num_operarios_simult if pd.notnull(tiempo_operario) else 0

            # Ajustar si hay robot (debe haber al menos 1 operario)
            if pd.notnull(tiempo_robot):
                duracion_real = max(duracion_real, tiempo_robot)
                num_operarios_simult = max(num_operarios_simult, 1)

            # Variable auxiliar (binaria): ¿La tarea está activa en este turno?
            activa_en_turno = pulp.LpVariable(f"activa_{mat}_{t_id}_{ts_ini}", cat='Binary')

            # Restricciones para asegurar activación solo cuando solapan
            M = 1e5
            modelo += start[(mat, t_id)] <= ts_fin + M*(1 - activa_en_turno)
            modelo += end[(mat, t_id)] >= ts_ini - M*(1 - activa_en_turno)

            operarios_en_turno.append(num_operarios_simult * activa_en_turno)

        if operarios_en_turno:
            modelo += pulp.lpSum(operarios_en_turno) <= operarios_disp


# -----------------------------------------------------------------------
# 3) CREAR Y RESOLVER EL MODELO
# -----------------------------------------------------------------------
def armar_modelo(datos):
    """
    Crea el modelo, define start/end para cada (pedido, tarea),
    y aplica todas las restricciones (precedencia, calendario, capacidad, etc.).
    Luego define la función objetivo.
    """
    df_entregas = datos["df_entregas"]
    df_tareas   = datos["df_tareas"]
    modelo = pulp.LpProblem("Planificacion_Completa", pulp.LpMinimize)

    pedidos = df_entregas["referencia"].unique().tolist()
    t_ids   = df_tareas["id_interno"].unique().tolist()

    # 1) Variables start/end
    start = {}
    end   = {}
    for p in pedidos:
        # Filtramos las tareas que apliquen a este pedido
        df_mat = df_tareas[df_tareas["material_padre"] == p]
        for t_id in df_mat["id_interno"].unique():
            start[(p, t_id)] = pulp.LpVariable(f"start_{p}_{t_id}", lowBound=0)
            end[(p, t_id)]   = pulp.LpVariable(f"end_{p}_{t_id}", lowBound=0)

    # 2) Aplicar restricciones
    restriccion_duracion(modelo, df_tareas, start, end, df_entregas)
    restriccion_precedencia(modelo, df_tareas, start, end)
    restriccion_calendario(modelo, datos["df_calend"], start, end)
    restriccion_entrega_a_tiempo(modelo, df_entregas, df_tareas, end)
    restriccion_capacidad_zonas(modelo, df_tareas, start, end)
    restriccion_operarios(modelo, df_tareas, datos["df_calend"], start, end)

    # 3) Función objetivo:
    #    Minimizar la suma del end de tareas finales (o de todas)
    obj_expr = []
    for p in pedidos:
        df_mat = df_tareas[df_tareas["material_padre"] == p]
        # Tareas finales
        finales = []
        all_preds = set()
        for (_, row) in df_mat.iterrows():
            if not pd.isnull(row["predecesora"]):
                for x in str(row["predecesora"]).split(";"):
                    all_preds.add(int(x.strip()))
        for t_id in df_mat["id_interno"].unique():
            if t_id not in all_preds:
                finales.append(t_id)
        for f_id in finales:
            obj_expr.append(end[(p, f_id)])

    modelo += pulp.lpSum(obj_expr), "Minimize_Fin"

    return modelo, start, end

def resolver_modelo(modelo):
    modelo.solve(pulp.PULP_CBC_CMD(msg=0))
    return modelo

# -----------------------------------------------------------------------
# 4) EXPORTAR RESULTADOS
# -----------------------------------------------------------------------
def escribir_resultados(modelo, start, end, ruta_excel, df_tareas):
    """
    Igual que antes, pero añade 'operarios_asignados' = 1 si tiempo_operario>0 o tiempo_robot>0,
    de lo contrario 0.
    """
    import pandas as pd
    from datetime import datetime, timedelta

    estado = pulp.LpStatus[modelo.status]
    print(f"Estado del solver: {estado}")

    filas = []
    origen = datetime(2025, 3, 1, 0, 0, 0)

    # Precalcular dict de 'operarios_usados'
    op_usage = {}
    for _, row in df_tareas.iterrows():
        mat = row["material_padre"]
        t_id = row["id_interno"]
        need_op = 0
        if (not pd.isnull(row["tiempo_operario"]) and row["tiempo_operario"]>0) \
            or (not pd.isnull(row["tiempo_robot"]) and row["tiempo_robot"]>0):
            need_op = 1
        op_usage[(mat, t_id)] = need_op

    for (p, t), var_inicio in start.items():
        val_i = pulp.value(var_inicio)
        val_f = pulp.value(end[(p, t)])
        dt_i = origen + timedelta(hours=float(val_i)) if val_i else None
        dt_f = origen + timedelta(hours=float(val_f)) if val_f else None
        filas.append({
            "pedido": p,
            "tarea": t,
            "inicio": val_i,
            "fin": val_f,
            "datetime_inicio": dt_i,
            "datetime_fin": dt_f,
            "operarios_asignados": op_usage.get((p, t), 0)
        })

    df_sol = pd.DataFrame(filas)

    # Generar nombre de archivo
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base, ext = ruta_excel.rsplit(".", 1)
    new_file = f"{base}_{timestamp}.{ext}"

    with pd.ExcelWriter(new_file, engine="openpyxl", mode="w") as writer:
        df_sol.to_excel(writer, sheet_name="RESULTADOS", index=False)

    print(f"Resultados guardados en: {new_file}")

# -----------------------------------------------------------------------
# 5) FLUJO PRINCIPAL
# -----------------------------------------------------------------------
def main():
    ruta = "archivos\db_dev\Datos_entrada_v4.xlsx"
    datos = leer_datos(ruta)
    modelo, start, end = armar_modelo(datos)
    resolver_modelo(modelo)
    escribir_resultados(modelo, start, end, ruta, datos["df_tareas"])

if __name__ == "__main__":
    main()
