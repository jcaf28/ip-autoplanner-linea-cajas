import plotly.express as px
import plotly.figure_factory as ff
import pandas as pd

def plot_gantt(df_sol, df_entregas, df_calend):
    tareas = []
    
    # tareas normales
    for _, row in df_sol.iterrows():
        tareas.append(dict(
            Task=row["ubicacion"],
            Start=row["datetime_inicio"],
            Finish=row["datetime_fin"],
            Resource=row["pedido"],
            Descripcion=(
                f"[Tarea: T{row['tarea']}]<br>"
                f"Pedido: {row['pedido']}<br>"
                f"Ubicación: {row['ubicacion']}<br>"
                f"Inicio: {row['datetime_inicio']}<br>"
                f"Fin: {row['datetime_fin']}<br>"
                f"Operarios: {row['operarios_asignados']}"
            )
        ))

    # recepciones y entregas
    for _, row in df_entregas.iterrows():
        tareas.append(dict(
            Task="Recepción materiales",
            Start=row["fecha_recepcion_materiales"],
            Finish=row["fecha_recepcion_materiales"],
            Resource=row["referencia"],
            Descripcion=f"Recepción Pedido: {row['referencia']}<br>Fecha: {row['fecha_recepcion_materiales']}"
        ))
        tareas.append(dict(
            Task="Entrega cliente",
            Start=row["fecha_entrega"],
            Finish=row["fecha_entrega"],
            Resource=row["referencia"],
            Descripcion=f"Entrega Pedido: {row['referencia']}<br>Fecha: {row['fecha_entrega']}"
        ))

    df_plot = pd.DataFrame(tareas)

    # colores alternados por pedido
    colores = px.colors.qualitative.Pastel
    pedidos = df_plot["Resource"].unique()
    color_map = {pedido: colores[i % len(colores)] for i, pedido in enumerate(pedidos)}

    fig = ff.create_gantt(
        df_plot,
        index_col='Resource',
        colors=color_map,
        show_colorbar=True,
        group_tasks=True,
        title="Diagrama de Gantt - Planificación de Producción",
        bar_width=0.2,
        showgrid_x=True,
        showgrid_y=True
    )

    # Añadir zonas sombreadas para turnos de trabajo
    for _, row in df_calend.iterrows():
        dia = pd.to_datetime(row["dia"])
        inicio_turno = pd.to_datetime(f"{dia.date()} {row['hora_inicio']}")
        fin_turno = pd.to_datetime(f"{dia.date()} {row['hora_fin']}")
        fig.add_vrect(
            x0=inicio_turno, x1=fin_turno,
            fillcolor="LightGray", opacity=0.15,
            layer="below", line_width=0,
        )

    # Ajustes visuales
    fig.update_layout(
        height=600,
        xaxis_title="Fecha y Hora",
        yaxis_title="Ubicación",
        hoverlabel_bgcolor="white",
        hoverlabel_bordercolor="black",
        xaxis=dict(
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1 día", step="day", stepmode="todate"),
                    dict(count=7, label="1 semana", step="day", stepmode="todate"),
                    dict(step="all", label="Todo")
                ])
            ),
            rangeslider=dict(visible=True),
            type="date"
        ),
    )

    # Hover personalizado mostrando descripciones completas
    for i, gantt_shape in enumerate(fig.data):
        gantt_shape.hovertemplate = df_plot.iloc[i]["Descripcion"]

    fig.show()
