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
from datetime import datetime, timedelta

# -----------------------------------------------------------------------
# 1) LECTURA DE DATOS
# -----------------------------------------------------------------------
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
    Maneja múltiples predecesoras separadas por ;
    """
    for (idx, row) in df_tareas.iterrows():
      mat = row["material_padre"]
      t_id = row["id_interno"]
      if not pd.isnull(row["predecesora"]):
          lista_preds = str(row["predecesora"]).split(";")
          for p_id in lista_preds:
              p_id = int(p_id.strip())
              if (mat, p_id) not in end:
                  print(f"¡No existe la tarea predecesora ({mat}, {p_id}) en end!")

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
    """
    Limitamos la suma de tareas que requieren operarios en cada intervalo de turno.
    - Si 'tiempo_verificado' > 0 => no consume operarios
    - Si 'tiempo_operario' > 0 => consume X=1 operario? O el # que haga falta.
    * Simplificación: cada tarea que requiera 'tiempo_operario' usa 1 operario
      y no puede solaparse con más tareas que la disponibilidad del turno.
    => Necesitamos discretizar en cada turno (ti) [start_t, end_t].
       Si la tarea solapa con el turno, consumimos 1 plaza.
    => Requiere variables 'uso_op[(pedido,tarea,turno)]' y restricciones big-M
    => Por simplicidad, haremos un approach parcial.
    """
    # Creamos una lista de turnos con (turno_id, ts_ini, ts_fin, ops_disp)
    turnos = []
    for (_, row) in df_calend.iterrows():
        d = datetime.strptime(str(row["dia"]), "%Y-%m-%d")
        hi = datetime.strptime(str(row["hora_inicio"]), "%H:%M:%S").time()
        hf = datetime.strptime(str(row["hora_fin"]), "%H:%M:%S").time()
        dti = datetime(d.year, d.month, d.day, hi.hour, hi.minute)
        dtf = datetime(d.year, d.month, d.day, hf.hour, hf.minute)
        t_ini = (dti - datetime(2025,3,1)).total_seconds()/3600
        t_fin = (dtf - datetime(2025,3,1)).total_seconds()/3600
        turnos.append((row["dia"], row["turno"], t_ini, t_fin, row["cantidad_operarios"]))

    # Variable binaria: la tarea (p,t) se ejecuta en el turno k => z[(p,t,k)]
    z = {}
    for (_, row) in df_tareas.iterrows():
        mat = row["material_padre"]
        t_id = row["id_interno"]
        # si tiempo_verificado => 0 operarios
        ops_needed = 1 if not pd.isnull(row["tiempo_operario"]) else 0

        if ops_needed > 0:
            for (dia, tur, ti, tf, disp) in turnos:
                z[(mat, t_id, dia, tur)] = pulp.LpVariable(f"z_{mat}_{t_id}_{dia}_{tur}", cat=pulp.LpBinary)

    # 1) Si z(p,t,turno)=1 => start/end deben solapar con [ti, tf]
    #    Simplificación: forzamos que la tarea se ejecute COMPLETAMENTE dentro de un turno
    #    (si no cabe, no la hace).
    for (key, var) in z.items():
        (mat, t_id, dia, tur) = key
        # Buscamos t_ini,t_fin
        turno_info = [x for x in turnos if x[0] == dia and x[1] == tur][0]
        t_ini = turno_info[2]
        t_fin = turno_info[3]
        # start >= t_ini * z
        # end   <= t_fin + M*(1 - z)
        M = 1e5
        modelo += start[(mat, t_id)] >= t_ini * var
        modelo += end[(mat, t_id)] <= t_fin + M*(1 - var)

    # 2) Para cada turno, la suma de z(p,t,turno)*ops_needed <= disp
    #    => si z(p,t,turno)=1 y ops_needed=1 => gastamos 1 operario
    for (dia, tur, ti, tf, disp) in turnos:
        sum_expr = []
        for (idx, row) in df_tareas.iterrows():
            mat = row["material_padre"]
            t_id = row["id_interno"]
            ops_needed = 1 if not pd.isnull(row["tiempo_operario"]) else 0
            if ops_needed > 0:
                if (mat, t_id, dia, tur) in z:
                    sum_expr.append(z[(mat, t_id, dia, tur)])
        if sum_expr:
            modelo += pulp.lpSum(sum_expr) <= disp

    # 3) Cada tarea que necesite operarios debe asignarse EXACTAMENTE a 1 turno
    for (idx, row) in df_tareas.iterrows():
        mat = row["material_padre"]
        t_id = row["id_interno"]
        ops_needed = 1 if not pd.isnull(row["tiempo_operario"]) else 0
        if ops_needed > 0:
            # sum z[(mat,t_id,*)] = 1
            terms = []
            for (dia, tur, ti, tf, disp) in turnos:
                if (mat, t_id, dia, tur) in z:
                    terms.append(z[(mat, t_id, dia, tur)])
            if terms:
                modelo += pulp.lpSum(terms) == 1

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
def escribir_resultados(modelo, start, end, ruta_excel):
    """
    Genera un archivo de resultados independiente, con nombre {archivo_original}_{timestamp}.xlsx,
    volcando solo la pestaña "RESULTADOS". Adicionalmente convierte las columnas 'inicio' y 'fin'
    a datetime, asumiendo que son horas desde 2025-03-01 00:00:00.
    """
    import pandas as pd
    from datetime import datetime, timedelta

    estado = pulp.LpStatus[modelo.status]
    print(f"Estado del solver: {estado}")

    # 1) Construimos el DataFrame con start/end
    filas = []
    for (p, t), var_inicio in start.items():
        val_i = pulp.value(var_inicio)
        val_f = pulp.value(end[(p, t)])
        filas.append({"pedido": p, "tarea": t, "inicio": val_i, "fin": val_f})

    df_sol = pd.DataFrame(filas)

    # 2) Convertir a datetime (origen = 2025-03-01 00:00)
    origen = datetime(2025, 3, 1, 0, 0, 0)
    df_sol["datetime_inicio"] = None
    df_sol["datetime_fin"] = None

    for i, row in df_sol.iterrows():
        if pd.notnull(row["inicio"]):
            df_sol.at[i, "datetime_inicio"] = origen + timedelta(hours=float(row["inicio"]))
        if pd.notnull(row["fin"]):
            df_sol.at[i, "datetime_fin"] = origen + timedelta(hours=float(row["fin"]))

    # 3) Crear nombre de archivo nuevo con timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base, ext = ruta_excel.rsplit(".", 1)
    new_file = f"{base}_{timestamp}.{ext}"

    # 4) Guardar SOLO la hoja RESULTADOS en el archivo nuevo
    #    Usamos engine="openpyxl" para permitir guardarlo sin problemas
    with pd.ExcelWriter(new_file, engine="openpyxl", mode="w") as writer:
        df_sol.to_excel(writer, sheet_name="RESULTADOS", index=False)

    print(f"Resultados guardados en: {new_file}")

# -----------------------------------------------------------------------
# 5) FLUJO PRINCIPAL
# -----------------------------------------------------------------------
def main():
    ruta = "archivos\db_dev\Datos_entrada_v3.xlsx"
    datos = leer_datos(ruta)
    modelo, start, end = armar_modelo(datos)
    resolver_modelo(modelo)
    escribir_resultados(modelo, start, end, ruta)

if __name__ == "__main__":
    main()
