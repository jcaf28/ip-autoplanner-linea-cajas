# PATH: src/results_gen/imprimir_resultados_consola.py

def imprimir_resultados_consola(tareas, timeline, turnos_ocupacion):
    if not tareas:
        print("No hay solución factible.")
        return

    makespan = max(t["end"] for t in tareas)
    print(f"\nSOLUCIÓN Factible - Makespan = {makespan}")
    for t in tareas:
        print(f" Pedido={t['pedido']} t_idx={t['t_idx']}, "
              f"Maq={t['machine']}, start={t['start']}, "
              f"end={t['end']}, x_op={t['x_op']} (dur={t['duration']})")

    print("\nTimeline de ocupación (cambios de número de operarios):")
    for evt in timeline:
        print(f"  t={evt[0]} -> Operarios activos: {evt[2]}")

    print("\nOcupación media por turno:")
    for turno in turnos_ocupacion:
        print(f"  Turno={turno['turno_id']} "
              f"[{turno['comp_start']},{turno['comp_end']}], "
              f"cap={turno['capacidad']} -> "
              f"ocupacion_media={turno['ocupacion_media_%']}%")