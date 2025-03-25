# PATH: src/results_gen/generar_diagrama_gantt.py

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def generar_diagrama_gantt(tareas, timeline, turnos_ocupacion):
    if not tareas:
        print("⚠️ No hay tareas para graficar.")
        return

    print(f"✅ Graficando {len(tareas)} tareas y {len(timeline)} puntos de ocupación...")

    df_t = pd.DataFrame(tareas)
    df_t["label"] = df_t.apply(
        lambda r: f"{r['pedido']} - {r['x_op']} op", axis=1
    )

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.05,
        subplot_titles=("Gantt de tareas por máquina", "Tasa de ocupación de operarios")
    )

    colors = {}
    for i, row in df_t.iterrows():
        pedido = row["pedido"]
        if pedido not in colors:
            colors[pedido] = f"hsl({hash(pedido)%360},50%,60%)"

        fig.add_trace(
            go.Bar(
                x=[row["end"] - row["start"]],
                y=[str(row["machine"])],
                base=row["start"],
                name=row["pedido"],
                orientation='h',
                text=row["label"],
                hovertext=f"Pedido: {row['pedido']}<br>"
                          f"Inicio: {row['start']}<br>"
                          f"Fin: {row['end']}<br>"
                          f"x_op: {row['x_op']}<br>"
                          f"Máquina: {row['machine']}",
                marker_color=colors[pedido],
                showlegend=False
            ),
            row=1, col=1
        )

    if timeline:
        df_oc = pd.DataFrame(timeline, columns=["tiempo", "ocupacion", "texto"])
        df_oc["porcentaje"] = df_oc.apply(
            lambda r: eval(r["texto"].replace("-", "0")).__truediv__(int(r["texto"].split("/")[-1]) or 1)*100, axis=1
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

    fig.update_yaxes(title_text="Máquina", row=1, col=1, autorange="reversed")
    fig.update_yaxes(title_text="%", row=2, col=1)
    fig.update_xaxes(title_text="Tiempo", row=2, col=1)

    fig.update_layout(
        height=700,
        title="Planificación + Tasa de ocupación de operarios",
        margin=dict(l=60, r=40, t=60, b=40)
    )

    print("✅ Mostrando figura interactiva...\n")
    fig.show()
