import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import mplcursors

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import mplcursors

def plot_gantt_matplotlib(df_sol, df_entregas, df_calend, ordered_locations):
    """
    Genera el diagrama de Gantt utilizando el orden de ubicaciones definido en ordered_locations.
    
    Parámetros:
      - df_sol: DataFrame con la planificación.
      - df_entregas: DataFrame con fechas de entrega.
      - df_calend: DataFrame con los turnos.
      - ordered_locations: Lista de nombres de ubicaciones en el orden deseado.
    """
    fig, ax = plt.subplots(figsize=(14, 6))

    # Sombrear turnos
    for _, row in df_calend.iterrows():
        dia = pd.to_datetime(row["dia"])
        hi = row["hora_inicio"]
        hf = row["hora_fin"]
        dt_ini = pd.to_datetime(dia.strftime("%Y-%m-%d") + " " + hi.strftime("%H:%M:%S"))
        dt_fin = pd.to_datetime(dia.strftime("%Y-%m-%d") + " " + hf.strftime("%H:%M:%S"))
        ax.axvspan(dt_ini, dt_fin, facecolor="gray", alpha=0.05, zorder=0)

    # Paleta pastel por 'pedido'
    pedidos_unicos = df_sol["pedido"].unique()
    palette = sns.color_palette("Set2", n_colors=len(pedidos_unicos))
    color_map = {pedido: palette[i % len(pedidos_unicos)] for i, pedido in enumerate(pedidos_unicos)}

    # Aquí usamos directamente ordered_locations para asignar la posición Y
    ubicacion_dict = {ubic: i for i, ubic in enumerate(ordered_locations)}

    artists = []
    tooltips = []

    # Dibujar las barras de tareas
    for _, row in df_sol.iterrows():
        pedido = row["pedido"]
        color = color_map.get(pedido, "gray")
        # Obtener la posición según ordered_locations (si la tarea aparece, de lo contrario se ignora)
        if row["ubicacion"] not in ubicacion_dict:
            continue  # Si la tarea tiene una ubicación que no está en el orden, se omite
        y_pos = ubicacion_dict[row["ubicacion"]]

        bar = ax.barh(
            y=y_pos,
            width=(row["datetime_fin"] - row["datetime_inicio"]),
            left=row["datetime_inicio"],
            color=color,
            edgecolor="black",
            alpha=0.8
        )

        ax.text(row["datetime_inicio"], y_pos, f"T{row['tarea']}", va="center", fontsize=7)
        artists.append(bar[0])
        tooltip = (
            f"[Tarea: T{row['tarea']}]\n"
            f"Pedido: {pedido}\n"
            f"Ubicación: {row['ubicacion']}\n"
            f"Inicio: {row['datetime_inicio']}\n"
            f"Fin: {row['datetime_fin']}\n"
            f"Operarios: {row['operarios_asignados']}"
        )
        tooltips.append(tooltip)

    # Líneas de recepción y entrega
    for _, row in df_entregas.iterrows():
        pedido = row["referencia"]
        color = color_map.get(pedido, "gray")

        # Recepción
        fecha_rec = row["fecha_recepcion_materiales"]
        line_rec = ax.axvline(fecha_rec, color=color, linestyle="dashed", lw=1.5, alpha=0.8)
        artists.append(line_rec)
        ttip_rec = (
            f"[Recepción]\nPedido: {pedido}\n"
            f"Fecha: {fecha_rec:%Y-%m-%d %H:%M}"
        )
        tooltips.append(ttip_rec)

        # Entrega
        fecha_ent = row["fecha_entrega"]
        line_ent = ax.axvline(fecha_ent, color=color, linestyle="dashed", lw=1.5, alpha=0.8)
        artists.append(line_ent)
        ttip_ent = (
            f"[Entrega]\nPedido: {pedido}\n"
            f"Fecha: {fecha_ent:%Y-%m-%d %H:%M}"
        )
        tooltips.append(ttip_ent)

    # Usar ordered_locations para fijar el eje Y
    ax.set_yticks(range(len(ordered_locations)))
    ax.set_yticklabels(ordered_locations)
    ax.set_xlabel("Fecha y Hora")
    ax.set_ylabel("Ubicación")
    ax.set_title("Diagrama de Gantt - Planificación de Producción")
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45)
    plt.tight_layout()

    # Tooltips interactivos
    cursor = mplcursors.cursor(artists, hover=True, highlight=True, multiple=False)
    @cursor.connect("add")
    def on_add(sel):
        i = artists.index(sel.artist)
        sel.annotation.set_text(tooltips[i])
        sel.annotation.get_bbox_patch().set(fc="white", alpha=0.8)

    plt.show()

