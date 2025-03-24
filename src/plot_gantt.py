# PATH: src/plot_gantt.py

import plotly.graph_objects as go
import pandas as pd

def generar_diagrama_gantt(sol_tareas):
    df = pd.DataFrame(sol_tareas)
    df["pedido_tarea"] = df["pedido"] + "_" + df["t_idx"].astype(str)

    fig = go.Figure()

    for _, row in df.iterrows():
        fig.add_trace(go.Bar(
            x=[row["end"] - row["start"]],
            y=[str(row["machine"])],
            base=row["start"],
            orientation='h',
            name=row["pedido_tarea"],
            hovertemplate=f"{row['pedido_tarea']}<br>Máquina: {row['machine']}<br>Inicio: {row['start']}<br>Fin: {row['end']}<br>Operarios: {row['x_op']}"
        ))

    fig.update_layout(
        barmode='stack',
        title="Diagrama de Gantt - Planificación de tareas",
        xaxis_title="Tiempo (minutos)",
        yaxis_title="Máquina",
        yaxis=dict(autorange="reversed"),
        height=600
    )

    return fig



def trazar_ocupacion_operarios(sol_intervals):
    import plotly.express as px
    import pandas as pd

    filas = []
    for iv in sol_intervals:
        cini = iv["comp_start"]
        cfin = iv["comp_end"]
        val = iv["operarios_ocupados"]
        filas.append({"tiempo": cini, "ocupados": val})
        filas.append({"tiempo": cfin, "ocupados": val})

    df = pd.DataFrame(filas)
    df = df.sort_values("tiempo")

    fig = px.line(
        df,
        x="tiempo",
        y="ocupados",
        markers=True,
        title="Ocupación de operarios en el tiempo"
    )
    return fig
