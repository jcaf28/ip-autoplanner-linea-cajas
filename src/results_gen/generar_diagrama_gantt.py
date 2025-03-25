import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def generar_diagrama_gantt(tareas, timeline, turnos_ocupacion, capacidades):
    if not tareas:
        print("⚠️ No hay tareas para graficar.")
        return

    print(f"✅ Graficando {len(tareas)} tareas y {len(timeline)} puntos de ocupación...")

    df_t = pd.DataFrame(tareas)
    df_cap = pd.DataFrame(capacidades)
    cap_dict = df_cap.set_index("ubicación")["capacidad"].to_dict()

    # Preparamos el diccionario de slots disponibles por máquina
    slot_disponible = {m: [[] for _ in range(cap_dict.get(m, 1))] for m in cap_dict}

    # Función para asignar a la primera ranura libre (sin solapamientos)
    def asignar_slot(machine, start, end):
        for i, tareas_slot in enumerate(slot_disponible[machine]):
            if all(end <= t["start"] or start >= t["end"] for t in tareas_slot):
                return i
        return 0  # Fallback (nunca debería pasar si el modelo CP lo ha respetado)

    slot_ids = []
    for i, row in df_t.iterrows():
        m = row["machine"]
        s = row["start"]
        e = row["end"]
        slot = asignar_slot(m, s, e)
        slot_ids.append(f"{m}.{slot+1}")
        slot_disponible[m][slot].append({"start": s, "end": e})  # Registrar tarea en slot

    df_t["slot_id"] = slot_ids
    df_t["label"] = df_t.apply(lambda r: f"{r['pedido']} - {r['x_op']} op", axis=1)

    # Colores únicos por pedido
    colors = {}
    for pedido in df_t["pedido"].unique():
        colors[pedido] = f"hsl({hash(pedido)%360}, 50%, 60%)"

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.05,
        subplot_titles=("Gantt de tareas por máquina (por capacidad)", "Tasa de ocupación de operarios")
    )

    for _, row in df_t.iterrows():
        fig.add_trace(
            go.Bar(
                x=[row["end"] - row["start"]],
                y=[row["slot_id"]],
                base=row["start"],
                name=row["pedido"],
                orientation='h',
                text=row["label"],
                hovertext=(
                    f"Pedido: {row['pedido']}<br>"
                    f"Inicia: {row['start']}<br>"
                    f"Finaliza: {row['end']}<br>"
                    f"x_op: {row['x_op']}<br>"
                    f"Máquina: {row['machine']}<br>"
                    f"Slot: {row['slot_id']}"
                ),
                marker_color=colors[row["pedido"]],
                showlegend=False
            ),
            row=1, col=1
        )

    # Curva de ocupación de operarios
    if timeline:
        df_oc = pd.DataFrame(timeline, columns=["tiempo", "ocupacion", "texto"])
        df_oc["porcentaje"] = df_oc.apply(
            lambda r: eval(r["texto"].replace("-", "0")).__truediv__(int(r["texto"].split("/")[-1]) or 1)*100,
            axis=1
        )

        fig.add_trace(
            go.Scatter(
                x=df_oc["tiempo"],
                y=df_oc["porcentaje"],
                mode="lines+markers",
                line=dict(color="firebrick"),
                name="Ocupación (%)",
                hoverinfo="x+y",
                showlegend=False
            ),
            row=2, col=1
        )

    fig.update_yaxes(title_text="Máquina.Capacidad", row=1, col=1, autorange="reversed")
    fig.update_yaxes(title_text="%", row=2, col=1)
    fig.update_xaxes(title_text="Tiempo", row=2, col=1)

    fig.update_layout(
        height=700,
        title="Planificación + Tasa de ocupación de operarios",
        margin=dict(l=60, r=40, t=60, b=40)
    )

    print("✅ Mostrando figura interactiva...\n")
    fig.show()
