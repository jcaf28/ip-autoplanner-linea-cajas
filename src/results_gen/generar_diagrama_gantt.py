import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from collections import defaultdict

def generar_diagrama_gantt(tareas, timeline, df_capac):
    """
    Genera un Gantt (arriba) y un gráfico de ocupación (abajo) usando Plotly.
    """

    # =======================
    # 1. Preparar estructuras
    # =======================
    map_maq = {}
    for _, row in df_capac.iterrows():
        map_maq[row["ubicación"]] = (row["nom_ubicacion"], int(row["capacidad"]))

    tareas_por_maquina = defaultdict(list)
    for t in tareas:
        tareas_por_maquina[t["machine"]].append(t)

    for m in tareas_por_maquina:
        tareas_por_maquina[m].sort(key=lambda x: x["start"])

    def asignar_slots(lista_tareas, capacidad):
        slots = [-1] * capacidad
        out = {}
        for t in lista_tareas:
            for i in range(capacidad):
                if t["start"] >= slots[i]:
                    out[t["t_idx"]] = i
                    slots[i] = t["end"]
                    break
        return out

    asignaciones = {}
    for m, lista in tareas_por_maquina.items():
        _, cap = map_maq.get(m, (f"Maq{m}", 1))
        slots = asignar_slots(lista, cap)
        for t in lista:
            asignaciones[(m, t["t_idx"])] = slots[t["t_idx"]]

    color_map = {}
    color_idx = 0

    for t in tareas:
        m = t["machine"]
        nom, cap = map_maq.get(m, (f"Maq{m}", 1))
        slot = asignaciones[(m, t["t_idx"])]
        t["y_label"] = f"{nom}.{slot + 1}" if cap > 1 else nom
        if t["pedido"] not in color_map:
            color_map[t["pedido"]] = f"hsl({(color_idx * 47) % 360}, 70%, 50%)"
            color_idx += 1
        t["color"] = color_map[t["pedido"]]

    # ========================================
    # 2. Crear figura con subplots Gantt + Ocupación
    # ========================================
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.05
    )

    # =============================
    # 3. GANTT (subplot 1)
    # =============================
    y_labels = sorted(set(t["y_label"] for t in tareas))

    def extraer_id_ubicacion(y_label):
        base = y_label.split(".")[0]
        for _, row in df_capac.iterrows():
            if row["nom_ubicacion"] == base:
                return row["ubicación"]
        return 999

    y_labels.sort(key=lambda l: (extraer_id_ubicacion(l), l))
    y_map = {l: i for i, l in enumerate(y_labels)}

    for t in tareas:
        fig.add_trace(go.Bar(
            x=[t["duration"]],
            y=[t["y_label"]],
            base=[t["start"]],
            orientation="h",
            marker=dict(color=t["color"]),
            hovertext=(f"Pedido: {t['pedido']}<br>"
                        f"Maq: {t['machine']}<br>"
                        f"Start: {t['start']} – End: {t['end']}<br>"
                        f"x_op: {t['x_op']}, Dur: {t['duration']}"),
            hoverinfo="text",
            showlegend=False
        ), row=1, col=1)

    fig.update_yaxes(
        tickmode="array",
        tickvals=y_labels,
        autorange="reversed",
        row=1, col=1,
        title="Ubicación"
    )

    # =============================
    # 4. OCUPACIÓN (subplot 2) con eje X numérico
    # =============================
    for seg in timeline:
        t_ini = seg["t_ini"]
        t_fin = seg["t_fin"]
        cap = seg["operarios_turno"]
        occ = seg["ocupacion"]
        porc = seg["%ocup"]

        # Fondo: capacidad total (gris)
        fig.add_trace(go.Scatter(
            x=[t_ini, t_fin, t_fin, t_ini],
            y=[0, 0, cap, cap],
            fill="toself",
            fillcolor="lightgray",
            line=dict(color="lightgray"),
            opacity=0.5,
            hoverinfo="skip",
            showlegend=False
        ), row=2, col=1)

        # Ocupación: operarios activos (azul)
        fig.add_trace(go.Scatter(
            x=[t_ini, t_fin, t_fin, t_ini],
            y=[0, 0, occ, occ],
            fill="toself",
            fillcolor="blue",
            line=dict(color="blue"),
            opacity=0.7,
            text=f"{occ}/{cap} → {porc}%",
            hoverinfo="text",
            showlegend=False
        ), row=2, col=1)

    # =============================
    # 5. Layouts
    # =============================
    fig.update_layout(
        title="Planificación: Gantt + Ocupación",
        barmode="overlay",
        template="plotly_white",
        height=700,
        width=1100
    )

    fig.show()
