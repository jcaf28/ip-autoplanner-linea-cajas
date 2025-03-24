# PATH: src/plot_gantt.py

def generar_diagrama_gantt(sol_tareas):
    import plotly.express as px
    import pandas as pd

    df = pd.DataFrame(sol_tareas)
    df["machine"] = df["machine"].astype(str)
    df["pedido_tarea"] = df["pedido"] + "_" + df["t_idx"].astype(str)

    fig = px.timeline(
        df,
        x_start="start",
        x_end="end",
        y="machine",                   # cada fila del diagrama = máquina
        color="pedido_tarea",         # cada tarea se pinta con un color diferente
        hover_data=["x_op", "duration"]
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(type="linear")   # trata start/end como ejes numéricos
    fig.update_layout(title="Diagrama de Gantt - Planificación de tareas")
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
