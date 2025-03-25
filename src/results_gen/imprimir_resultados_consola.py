def imprimir_resultados_consola(tareas, timeline):
    if not tareas:
        print("No hay solución factible.")
        return

    makespan = max(t["end"] for t in tareas)
    print(f"\n✅ SOLUCIÓN Factible - Makespan = {makespan}")
    print("-" * 60)
    print("Detalle de tareas planificadas:\n")
    for t in tareas:
        ts_ini = t.get("timestamp_ini", "")
        ts_fin = t.get("timestamp_fin", "")
        print(f" Pedido={t['pedido']} t_idx={t['t_idx']}, "
              f"Maq={t['machine']}, start={t['start']}, end={t['end']} "
              f"(dur={t['duration']}, x_op={t['x_op']})"
              f" [{ts_ini} → {ts_fin}]")

    print("\n🕒 Timeline de ocupación (por tramos):")
    print("-" * 60)
    for tramo in timeline:
        ts_ini = tramo.get("timestamp_ini", "")
        ts_fin = tramo.get("timestamp_fin", "")
        print(f"  [{tramo['t_ini']:>4}, {tramo['t_fin']:>4}) "
              f"=> ocup: {tramo['ocupacion']:>2}, "
              f"turno: {tramo['operarios_turno']:>2}, "
              f"%ocup: {tramo['%ocup']:>5.1f}%, "
              f"{ts_ini} → {ts_fin}")

