# PATH: src/service/generar_diagrama_gantt.py

import pandas as pd
import plotly.express as px

def generar_diagrama_gantt(tareas):
    if not tareas:
        return None

    df = pd.DataFrame(tareas)

    # Creamos una etiqueta legible que incluya el número de operarios
    df["Tarea"] = df.apply(
        lambda row: f"{row['pedido']} (t{row['t_idx']}) - {row['x_op']} op", axis=1
    )

    # Creamos la figura Gantt
    fig = px.timeline(
        df,
        x_start="start",
        x_end="end",
        y="machine",
        color="pedido",
        text="Tarea"
    )

    # Estilo
    fig.update_yaxes(title="Máquina")
    fig.update_xaxes(title="Tiempo")
    fig.update_layout(
        title="Diagrama de Gantt: planificación por máquina",
        margin=dict(l=40, r=40, t=40, b=40),
        height=500,
        showlegend=False
    )

    # Mostramos el número de operarios dentro de las barras
    fig.update_traces(insidetextanchor="start", textposition="inside")

    return fig
