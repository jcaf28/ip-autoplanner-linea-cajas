import plotly.express as px
import pandas as pd
import datetime

def plot_gantt(df_sol, df_entregas, df_calend):
    # --- 1) TAREAS
    tareas = []
    for _, row in df_sol.iterrows():
        tareas.append(dict(
            Task=f"{row['ubicacion']} (T{row['tarea']})",
            Start=row["datetime_inicio"],
            Finish=row["datetime_fin"],
            Pedido=row["pedido"],
            Operarios=row["operarios_asignados"],
            Ubicacion=row["ubicacion"],
            Tipo="Tarea"
        ))

    df_tareas = pd.DataFrame(tareas)

    # --- 2) LÍNEAS DE RECEPCIÓN/ENTREGA
    # Convertir a str ISO para Plotly
    lineas = []
    for _, row in df_entregas.iterrows():
        fecha_rec = pd.to_datetime(row["fecha_recepcion_materiales"]).isoformat()
        fecha_ent = pd.to_datetime(row["fecha_entrega"]).isoformat()
        pedido = row["referencia"]

        lineas.append(dict(Task="Recepción", Fecha=fecha_rec, Pedido=pedido, Tipo="Recepción"))
        lineas.append(dict(Task="Entrega",   Fecha=fecha_ent, Pedido=pedido, Tipo="Entrega"))

    df_lineas = pd.DataFrame(lineas)

    # --- 3) Colores
    colores = px.colors.qualitative.Pastel
    pedidos = df_tareas["Pedido"].unique()
    color_map = {pedido: colores[i % len(colores)] for i, pedido in enumerate(pedidos)}

    # --- 4) Gantt principal con Plotly Express
    fig = px.timeline(
        df_tareas,
        x_start="Start",
        x_end="Finish",
        y="Task",
        color="Pedido",
        color_discrete_map=color_map,
        hover_data=["Pedido", "Operarios", "Ubicacion"],
        title="Diagrama de Gantt - Planificación de Producción"
    )
    fig.update_yaxes(autorange="reversed")

    # # --- 5) Añadir líneas verticales (sin anotaciones)
    # for _, row in df_lineas.iterrows():
    #     # row["Fecha"] es str (ISO)
    #     fecha_str = row["Fecha"]
    #     pedido = row["Pedido"]
    #     tipo = row["Tipo"]

    #     # color
    #     c = color_map.get(pedido, "gray")

    #     # en x => parsea la cadena ISO para dársela a add_vline
    #     fig.add_vline(
    #         x=fecha_str,
    #         line_dash="dot" if tipo == "Recepción" else "dash",
    #         line_color=c,
    #         annotation_text="",  # no usamos annotation aquí
    #         opacity=0.7
    #     )

    # --- 6) Sombras de turnos
    for _, row in df_calend.iterrows():
        dia = pd.to_datetime(row["dia"])
        hi = pd.to_datetime(dia.strftime("%Y-%m-%d") + " " + row["hora_inicio"].strftime("%H:%M:%S"))
        hf = pd.to_datetime(dia.strftime("%Y-%m-%d") + " " + row["hora_fin"].strftime("%H:%M:%S"))

        fig.add_vrect(
            x0=hi.isoformat(), x1=hf.isoformat(),
            fillcolor="LightGray", opacity=0.1,
            layer="below", line_width=0
        )

    # --- 7) Ajustes finales: slider y zoom
    fig.update_layout(
        hovermode="closest",
        xaxis=dict(
            rangeselector=dict(
                buttons=[
                    dict(count=1, label="1 día", step="day", stepmode="todate"),
                    dict(count=7, label="1 semana", step="day", stepmode="todate"),
                    dict(step="all", label="Todo")
                ]
            ),
            rangeslider=dict(visible=True),
            type="date"
        ),
        height=600
    )

    fig.show()
