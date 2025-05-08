# PATH: src/model/model_utils.py

import math

def estimar_horizonte(job_dict):
    """
    Calcula un horizonte aproximado para el modelo sumando las duraciones base.
    """
    horizon = 0
    for _, tasks in job_dict.items():
        for (_, _, tiempo_base, _, _, _) in tasks:
            horizon += max(1, tiempo_base)
    return max(horizon, 1)

def construir_diccionario_entregas(df_entregas):
    """
    Crea un diccionario: referencia -> {fecha_recepcion, fecha_entrega}
    para fácil acceso en las restricciones.
    """
    ent_dict = {}
    for _, row in df_entregas.iterrows():
        ref = str(row["referencia"])
        ent_dict[ref] = {
            "fecha_recepcion": row["fecha_recepcion_materiales"],
            "fecha_entrega":   row["fecha_entrega"]
        }
    return ent_dict

def crear_variables_tarea(model,
                          pedido,
                          tid,
                          t_idx,
                          tiempo_base,
                          min_op,
                          max_op,
                          machine_id,
                          horizon,
                          machine_to_intervals):
    """
    Crea las variables de una tarea: x_op, duration, start, end, interval.
    """
    if min_op == max_op == 0:
        x_op = model.NewIntVar(0, 0, f"xop_{pedido}_{tid}")
        duration_var = model.NewConstant(tiempo_base)
    else:
        x_op = model.NewIntVar(min_op, max_op, f"xop_{pedido}_{tid}")
        # Mapeamos la duración en función del nº de operarios
        dur_x = []
        for x in range(min_op, max_op + 1):
            val = math.ceil(tiempo_base / x) if tiempo_base > 0 else 0
            dur_x.append(val)
        dur_min = min(dur_x)
        dur_max = max(dur_x)
        duration_var = model.NewIntVar(dur_min, dur_max, f"dur_{pedido}_{tid}")
        model.AddElement(x_op - min_op, dur_x, duration_var)

    start_var = model.NewIntVar(0, horizon, f"start_{pedido}_{tid}")
    end_var   = model.NewIntVar(0, horizon, f"end_{pedido}_{tid}")
    interval_var = model.NewIntervalVar(start_var, duration_var, end_var,
                                        f"interval_{pedido}_{tid}")

    # Añadirlo a la estructura machine_to_intervals para la AddCumulative
    machine_to_intervals[machine_id].append((interval_var, 1))

    return {
        "start": start_var,
        "end": end_var,
        "interval": interval_var,
        "x_op": x_op,
        "duration": duration_var,
        "machine": machine_id
    }
