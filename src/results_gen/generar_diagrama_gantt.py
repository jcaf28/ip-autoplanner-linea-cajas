import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def generar_diagrama_gantt(tareas, timeline, df_capac):
    """
    Genera 2 subplots con Plotly:
      1) Gantt de tareas (arriba).
      2) Diagrama de ocupación (abajo).
    """

    # ==========================================================
    # 1) PREPARAR DATOS: MAPA (machine -> capacidad, nombre)
    # ==========================================================
    # df_capac: [ubicación, nom_ubicacion, capacidad]
    # Convertimos a dict: maquina_id -> (nom_ubicacion, capacidad)
    map_maq = {}
    for _, row in df_capac.iterrows():
        mid = row["ubicación"]
        map_maq[mid] = (row["nom_ubicacion"], int(row["capacidad"]))

    # ==========================================================
    # 2) ASIGNAR CADA TAREA A UNA "FILA" DE SU MÁQUINA
    #    Si capacidad > 1, generamos lineas: "Maq.1", "Maq.2", ...
    # ==========================================================
    # Construimos dict: machine -> lista de tareas en orden
    from collections import defaultdict
    tareas_por_maquina = defaultdict(list)
    for t in tareas:
        tareas_por_maquina[t["machine"]].append(t)

    # Ordenamos cada lista por start
    for m in tareas_por_maquina:
        tareas_por_maquina[m].sort(key=lambda x: x["start"])

    # Función para asignar slots
    # Devuelve un array con la info "slot_id" (0..capacidad-1) para cada tarea
    def asignar_slots(lista_tareas, capacidad):
        # slots[i] = end_time de la última tarea en el slot i
        slots = [ -1 for _ in range(capacidad) ]
        out = {}
        for t in lista_tareas:
            start = t["start"]
            # Buscar el primer slot libre
            for i_slot in range(capacidad):
                if start >= slots[i_slot]:
                    out[t["t_idx"]] = i_slot
                    slots[i_slot] = t["end"]
                    break
        return out

    # Asignamos
    asignaciones = {}
    for m, lista in tareas_por_maquina.items():
        nombre, cap = map_maq.get(m, (f"Maq{m}",1))
        slot_map = asignar_slots(lista, cap)
        for t in lista:
            key = (m, t["t_idx"])
            asignaciones[key] = slot_map[t["t_idx"]]

    # Preparamos "y_label" y "color" para cada tarea
    # y_label = "NombreDeMaq.slot"
    # color por "pedido"
    color_map = {}
    color_idx = 0

    for t in tareas:
        m = t["machine"]
        name_maq, cap = map_maq.get(m, (f"Maq{m}",1))
        slot_id = asignaciones[(m, t["t_idx"])]
        t["y_label"] = f"{name_maq}.{slot_id+1}" if cap>1 else f"{name_maq}"
        pedido = t["pedido"]
        if pedido not in color_map:
            color_map[pedido] = f"hsl({(color_idx*47)%360}, 70%, 50%)"
            color_idx += 1
        t["color"] = color_map[pedido]

    # ==========================================================
    # 3) CREAMOS FIGURA con SUBPLOTS (row_heights ajustable)
    # ==========================================================
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.6, 0.4],
                        vertical_spacing=0.03)

    # ==========================================================
    # 4) SUBPLOT 1: GANTT en "shapes" (barra = [start,end] x [y0,y1])
    # ==========================================================
    # Creamos un mapeo "y_label" -> indice
    # Pondremos la 1ª fila en y=0..1, la 2ª en y=1..2, etc.
    y_labels = list(set(t["y_label"] for t in tareas))
    y_labels.sort()
    y_map = { lbl:i for i,lbl in enumerate(y_labels) }

    # Añadimos shapes
    for t in tareas:
        y0 = y_map[t["y_label"]]
        y1 = y0+0.9
        fig.add_shape(
            type="rect",
            x0=t["start"], x1=t["end"],
            y0=y0, y1=y1,
            fillcolor=t["color"], opacity=0.8,
            line=dict(width=1, color="black"),
            row=1, col=1
        )
        # Añadimos un scatter invisible para tooltip
        fig.add_trace(go.Scatter(
            x=[(t["start"]+t["end"])/2],
            y=[(y0+y1)/2],
            text=(f"Pedido: {t['pedido']}<br>"
                  f"Máquina: {t['machine']}<br>"
                  f"Fila: {t['y_label']}<br>"
                  f"start: {t['start']}, end: {t['end']}<br>"
                  f"x_op: {t['x_op']}, dur: {t['duration']}"),
            mode="markers",
            marker=dict(size=2, color="rgba(0,0,0,0)"),
            hoverinfo="text",
            showlegend=False
        ), row=1, col=1)

    # Eje Y = labels "reverso" para que 1ª fila salga arriba
    fig.update_yaxes(
        tickmode="array",
        tickvals=[y_map[l] + 0.45 for l in y_labels],
        ticktext=y_labels,
        autorange="reversed",
        row=1, col=1
    )

    # ==========================================================
    # 5) SUBPLOT 2: Diagrama de ocupación
    #    Dibujamos rectángulos de [t_ini, t_fin] x [0,operarios_turno],
    #    en gris, y luego [0, ocupacion] en azul (o similar).
    # ==========================================================
    # Añadimos shapes
    for seg in timeline:
        t0 = seg["t_ini"]
        t1 = seg["t_fin"]
        cap = seg["operarios_turno"]
        occ = seg["ocupacion"]
        pc = seg["%ocup"]

        # Rect total (gris claro)
        fig.add_shape(
            type="rect",
            x0=t0, x1=t1,
            y0=0, y1=cap,
            fillcolor="lightgray",
            line=dict(width=0),
            opacity=0.6,
            row=2, col=1
        )

        # Rect ocupado
        fig.add_shape(
            type="rect",
            x0=t0, x1=t1,
            y0=0, y1=occ,
            fillcolor="blue",
            line=dict(width=0),
            opacity=0.6,
            row=2, col=1
        )
        # Scatter invisible para tooltip
        fig.add_trace(go.Scatter(
            x=[(t0+t1)/2],
            y=[occ/2],
            text=(f"t=[{t0},{t1})<br>"
                  f"Capacidad={cap}, Ocup={occ}<br>"
                  f"{pc}%"),
            mode="markers",
            marker=dict(size=2, color="rgba(0,0,0,0)"),
            hoverinfo="text",
            showlegend=False
        ), row=2, col=1)

    # Ajustar eje Y2 para que llegue hasta la máxima capacidad del timeline
    max_cap = 0
    for seg in timeline:
        if seg["operarios_turno"] > max_cap:
            max_cap = seg["operarios_turno"]

    fig.update_yaxes(range=[0, max_cap+1], row=2, col=1, title="Operarios")

    # ==========================================================
    # 6) AJUSTES FINALES
    # ==========================================================
    fig.update_layout(
        title="Planificación - Gantt + Ocupación",
        hovermode="x unified",
        width=1100,
        height=700,
        template="plotly_white"
    )

    fig.show()
