# PATH: src/model/solver.py

from ortools.sat.python import cp_model

from src.model.model import crear_modelo_cp
from src.model.time_management import comprimir_calendario
from src.model.data_processing import leer_datos, construir_estructura_tareas
from src.model.results_postprocessing import extraer_solucion

def planificar_linea_produccion(ruta_excel, debug=False):
    datos = leer_datos(ruta_excel)
    df_tareas   = datos["df_tareas"]
    df_capac    = datos["df_capac"]
    df_calend   = datos["df_calend"]
    df_entregas = datos["df_entregas"]

    intervals, cap_int = comprimir_calendario(df_calend)
    job_dict, precedences, machine_cap = construir_estructura_tareas(df_tareas, df_capac)

    referencias_validas = set(df_entregas["referencia"])
    job_dict = {k: v for k, v in job_dict.items() if k in referencias_validas}
    precedences = {k: v for k, v in precedences.items() if k in referencias_validas}

    model, all_vars = crear_modelo_cp(job_dict,
                                      precedences,
                                      machine_cap,
                                      intervals,
                                      cap_int,
                                      df_entregas,
                                      df_calend)

    solver, status = resolver_modelo(model, debug)

    sol_tareas, timeline, resumen_pedidos = extraer_solucion(
        solver, status, all_vars, intervals, cap_int, df_calend, df_entregas
    )

    return sol_tareas, timeline, df_capac, resumen_pedidos

def resolver_modelo(model, debug=False):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 1200
    solver.parameters.num_search_workers = 8

    if debug:
        print("🛠️ [DEBUG] Resolviendo modelo...")
    
    status = solver.Solve(model)

    if debug:
        print("✅ Status:", solver.StatusName(status))
        print("⏱️ Tiempo (WallTime):", round(solver.WallTime(), 3), "s")
        print("🔄 Ramas:", solver.NumBranches())
        print("❌ Conflictos:", solver.NumConflicts())
        print("📊 Stats:", solver.SolutionInfo())

    return solver, status
