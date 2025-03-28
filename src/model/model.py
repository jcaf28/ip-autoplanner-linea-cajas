# PATH: src/model/model.py

from ortools.sat.python import cp_model
import collections

from src.model.model_restrictions import (
    add_precedences,
    add_machine_capacity,
    add_operarios_capacity,
    add_material_reception_limits,
    add_objective_tardiness_makespan,
    add_no_solapamiento_distinto_tipo
)

from src.model.model_utils import (
    estimar_horizonte,
    construir_diccionario_entregas,
    crear_variables_tarea
)

def crear_modelo_cp(job_dict,
                    precedences,
                    machine_capacity,
                    intervals,
                    capacity_per_interval,
                    df_entregas,   
                    df_calend):    
    """
    Crea y devuelve el CP-SAT model con las variables y restricciones principales.
    """

    model = cp_model.CpModel()
    all_vars = {}
    
    # 1) Calcular un horizonte simple
    horizon = estimar_horizonte(job_dict)

    # 2) Construir diccionario de entregas (fechas)
    ent_dict = construir_diccionario_entregas(df_entregas)

    # 3) Crear variables + intervals
    machine_to_intervals = collections.defaultdict(list)
    for pedido, tasks in job_dict.items():
        for t_idx, (tid, machine_id, tiempo_base, min_op, max_op, tipo) in enumerate(tasks):
            all_vars[(pedido, t_idx)] = crear_variables_tarea(
                model, pedido, tid, t_idx, tiempo_base, min_op, max_op, machine_id,
                horizon, machine_to_intervals
            )

    # 4) Llamamos a las funciones que añaden restricciones:
    add_precedences(model, all_vars, precedences)
    add_machine_capacity(model, machine_to_intervals, machine_capacity)
    add_operarios_capacity(model, all_vars, intervals, capacity_per_interval)
    add_material_reception_limits(model, all_vars, job_dict, precedences, df_calend, ent_dict)
    add_no_solapamiento_distinto_tipo(model, all_vars, job_dict)
    
    # 5) Añadimos la función objetivo
    add_objective_tardiness_makespan(model, all_vars, job_dict, precedences, df_calend, ent_dict, horizon)

    return model, all_vars

