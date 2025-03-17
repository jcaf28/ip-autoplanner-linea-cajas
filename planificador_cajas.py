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
    for _, row in df_tareas.iterrows():
        mat = row["material_padre"]
        t_id = row["id_interno"]

        # Tomar la columna "num_operarios_fijos"
        n_ops = 1
        if "num_operarios_fijos" in df_tareas.columns and not pd.isnull(row["num_operarios_fijos"]):
            n_ops = float(row["num_operarios_fijos"])
            if n_ops < 1:
                n_ops = 1

        # Cálculo de la duración real
        # p.ej. dur_op = (tiempo_operario / n_ops) si tiempo_operario>0
        dur_op = 0.0
        if not pd.isnull(row["tiempo_operario"]) and row["tiempo_operario"]>0:
            dur_op = row["tiempo_operario"] / n_ops

        dur_robot = 0.0
        if not pd.isnull(row["tiempo_robot"]) and row["tiempo_robot"]>0:
            dur_robot = row["tiempo_robot"]

        dur_verif = 0.0
        if not pd.isnull(row["tiempo_verificado"]) and row["tiempo_verificado"]>0:
            dur_verif = row["tiempo_verificado"]

        # Escoges la mayor si se hacen en paralelo operario+robot, o la suma, según tu lógica.
        # Ejemplo: "tiempo_robot" implica un operario vigilando = la tarea entera
        dur = max(dur_op, dur_robot, dur_verif)

        # end[(mat,t_id)] = start[(mat,t_id)] + dur
        # No iniciar antes de fecha_recepcion
        for _, entreg_row in df_entregas.iterrows():
            if entreg_row["referencia"] == mat:
                rec_date = entreg_row["fecha_recepcion_materiales"]
                rec_ts = (rec_date - datetime(2025,3,1)).total_seconds()/3600

                modelo += end[(mat, t_id)] == start[(mat, t_id)] + dur
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

def restriccion_entrega_a_tiempo(modelo, df_entregas, df_tareas, end, retraso):
    """
    end(tarea_final) <= fecha_entrega + retraso[pedido].
    Si no es posible cumplir la fecha de entrega, el modelo busca minimizar el retraso total.
    """
    for ref in df_entregas["referencia"].unique():
        fecha_limite = df_entregas.loc[df_entregas["referencia"]==ref, "fecha_entrega"].iloc[0]
        entrega_ts = (fecha_limite - datetime(2025,3,1)).total_seconds()/3600

        df_mat = df_tareas[df_tareas["material_padre"] == ref]
        finales = []
        all_preds = set()

        for (_, row) in df_mat.iterrows():
            if not pd.isnull(row["predecesora"]):
                for pp in str(row["predecesora"]).split(";"):
                    all_preds.add(int(pp.strip()))
                    
        for t_id in df_mat["id_interno"].unique():
            if t_id not in all_preds:
                finales.append(t_id)

        # end(tarea_final) <= entrega_ts + retraso[pedido]
        for t_id in finales:
            modelo += end[(ref, t_id)] <= entrega_ts + retraso[ref]

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
    Limitamos el número de operarios disponibles en cada turno según el calendario.
    - Si 'tiempo_verificado' > 0 => no consume operarios.
    - Si 'tiempo_operario' > 0 => necesita operarios, pero el número es flexible.
    """
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

    # Variables de asignación de operarios
    uso_operarios = {}

    for (_, tarea) in df_tareas.iterrows():
        mat, t_id = tarea["material_padre"], tarea["id_interno"]
        tiempo_operario = tarea["tiempo_operario"]
        tiempo_robot = tarea["tiempo_robot"]

        # Se necesitan operarios si hay tiempo operario o el robot requiere vigilancia
        necesita_op = (not pd.isnull(tiempo_operario) and tiempo_operario > 0) or \
                      (not pd.isnull(tiempo_robot) and tiempo_robot > 0)

        if necesita_op:
            for (ts_ini, ts_fin, operarios_disp) in turnos:
                uso_operarios[(mat, t_id, ts_ini)] = pulp.LpVariable(f"uso_op_{mat}_{t_id}_{ts_ini}",
                                                                      lowBound=0, upBound=operarios_disp, cat="Integer")

                # Restricción de que no exceda los operarios disponibles en el turno
                modelo += uso_operarios[(mat, t_id, ts_ini)] <= operarios_disp

                # Restricción de solapamiento de tareas que consumen operarios
                M = 1e5  # Big-M
                modelo += start[(mat, t_id)] >= ts_ini - M * (1 - uso_operarios[(mat, t_id, ts_ini)])
                modelo += end[(mat, t_id)] <= ts_fin + M * (1 - uso_operarios[(mat, t_id, ts_ini)])


# -----------------------------------------------------------------------
# 3) CREAR Y RESOLVER EL MODELO
# -----------------------------------------------------------------------
def armar_modelo(datos):
    """
    Crea el modelo, define start/end para cada (pedido, tarea),
    y aplica todas las restricciones (precedencia, calendario, capacidad, etc.).
    Luego define la función objetivo permitiendo retrasos mínimos.
    """
    df_entregas = datos["df_entregas"]
    df_tareas   = datos["df_tareas"]
    modelo = pulp.LpProblem("Planificacion_Completa", pulp.LpMinimize)

    pedidos = df_entregas["referencia"].unique().tolist()
    t_ids   = df_tareas["id_interno"].unique().tolist()

    # 1) Variables start/end
    start = {}
    end   = {}
    retraso = {}  # Nueva variable de tardiness

    for p in pedidos:
        df_mat = df_tareas[df_tareas["material_padre"] == p]
        for t_id in df_mat["id_interno"].unique():
            start[(p, t_id)] = pulp.LpVariable(f"start_{p}_{t_id}", lowBound=0)
            end[(p, t_id)]   = pulp.LpVariable(f"end_{p}_{t_id}", lowBound=0)

        # Variable de retraso (puede ser >= 0, sin límite superior)
        retraso[p] = pulp.LpVariable(f"retraso_{p}", lowBound=0)

    # 2) Aplicar restricciones
    restriccion_duracion(modelo, df_tareas, start, end, df_entregas)
    restriccion_precedencia(modelo, df_tareas, start, end)
    restriccion_calendario(modelo, datos["df_calend"], start, end)
    restriccion_capacidad_zonas(modelo, df_tareas, start, end)
    restriccion_operarios(modelo, df_tareas, datos["df_calend"], start, end)
    restriccion_entrega_a_tiempo(modelo, df_entregas, df_tareas, end, retraso)

    # 4) Función objetivo: minimizar retraso total
    modelo += pulp.lpSum(retraso.values()), "Minimize_Total_Tardiness"

    return modelo, start, end, retraso


def resolver_modelo(modelo):
    modelo.solve(pulp.PULP_CBC_CMD(msg=0))
    return modelo

# -----------------------------------------------------------------------
# 4) EXPORTAR RESULTADOS
# -----------------------------------------------------------------------
def escribir_resultados(modelo, start, end, ruta_excel, df_tareas):
    """
    Guarda los resultados de la planificación y genera el diagrama de Gantt.
    """
    import pandas as pd
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime, timedelta

    estado = pulp.LpStatus[modelo.status]
    print(f"Estado del solver: {estado}")

    filas = []
    origen = datetime(2025, 3, 1)

    for (p, t), var_inicio in start.items():
        val_i = pulp.value(var_inicio)
        val_f = pulp.value(end[(p, t)])
        dt_i = origen + timedelta(hours=float(val_i)) if val_i else None
        dt_f = origen + timedelta(hours=float(val_f)) if val_f else None

        # Obtener ubicación y operarios asignados
        row = df_tareas[(df_tareas["material_padre"]==p) & (df_tareas["id_interno"]==t)].iloc[0]
        ubicacion = row["nom_ubicacion"]
        n_ops = int(row["num_operarios_fijos"]) if not pd.isnull(row["num_operarios_fijos"]) else 1

        filas.append({
            "pedido": p,
            "tarea": t,
            "inicio": val_i,
            "fin": val_f,
            "datetime_inicio": dt_i,
            "datetime_fin": dt_f,
            "ubicacion": ubicacion,
            "operarios_asignados": n_ops
        })
    
    df_sol = pd.DataFrame(filas)

    # Guardar en Excel
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base, ext = ruta_excel.rsplit(".", 1)
    new_file = f"{base}_{timestamp}.{ext}"
    with pd.ExcelWriter(new_file, engine="openpyxl", mode="w") as writer:
        df_sol.to_excel(writer, sheet_name="RESULTADOS", index=False)

    print(f"Resultados guardados en: {new_file}")

    # Generar gráfico de Gantt
    plot_gantt(df_sol)


def plot_gantt(df_sol):
    """
    Genera un diagrama de Gantt de las tareas planificadas.
    """
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    # Crear un diccionario de colores para cada ubicación
    colores = {
        "PREVIOS": "blue",
        "UTILLAJES": "orange",
        "ROBOT": "red",
        "SOPORTERIA": "green",
        "CATEDRAL": "purple",
        "SOLDADURA FINAL": "cyan",
        "INSPECCION FINAL": "magenta"
    }

    fig, ax = plt.subplots(figsize=(12, 6))

    # Obtener posiciones únicas para cada ubicación en el eje Y
    ubicaciones = df_sol["ubicacion"].unique()
    ubicacion_dict = {ubicacion: i for i, ubicacion in enumerate(ubicaciones)}

    for _, row in df_sol.iterrows():
        ax.barh(
            y=ubicacion_dict[row["ubicacion"]],
            width=row["datetime_fin"] - row["datetime_inicio"],
            left=row["datetime_inicio"],
            color=colores.get(row["ubicacion"], "gray"),
            alpha=0.7,
            label=row["ubicacion"] if row["ubicacion"] not in ax.get_legend_handles_labels()[1] else ""
        )

        # Agregar texto con el ID de la tarea
        ax.text(row["datetime_inicio"], ubicacion_dict[row["ubicacion"]], f'T{row["tarea"]}', va='center', fontsize=9)

    # Formatear ejes
    ax.set_yticks(range(len(ubicaciones)))
    ax.set_yticklabels(ubicaciones)
    ax.set_xlabel("Fecha y Hora")
    ax.set_ylabel("Ubicación")
    ax.set_title("Diagrama de Gantt - Planificación de Producción")
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45)
    plt.legend(title="Ubicaciones")
    plt.tight_layout()
    
    # Mostrar gráfico
    plt.show()

# -----------------------------------------------------------------------
# 5) FLUJO PRINCIPAL
# -----------------------------------------------------------------------
def main():
    ruta = "archivos\db_dev\Datos_entrada_v4.xlsx"
    datos = leer_datos(ruta)
    modelo, start, end, retraso = armar_modelo(datos)
    resolver_modelo(modelo)
    escribir_resultados(modelo, start, end, ruta, datos["df_tareas"])

if __name__ == "__main__":
    main()
