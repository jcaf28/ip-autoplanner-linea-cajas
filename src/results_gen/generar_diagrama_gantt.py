# PATH: src/results_gen/generar_diagrama_gantt.py

def generar_diagrama_gantt(tareas, timeline, df_capac, resumen_pedidos=None):
    import pandas as pd
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from collections import defaultdict

    map_maq = {
        row["ubicación"]: (row["nom_ubicacion"], int(row["capacidad"]))
        for _, row in df_capac.iterrows()
    }

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

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.05
    )

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
        # Chequeamos si es retraso o adelanto
        delta = t.get("delta_entrega_dias_laborales", 0)
        # p.ej. +3 => Retraso de 3, -2 => Adelanto de 2
        if delta < 0:
            diff_text = f"✅ Adelanto: {abs(delta):.2f} días"
        elif delta > 0:
            diff_text = f"⚠️ Retraso: {delta:.2f} días"
        else:
            diff_text = f"= Sin retraso"

        hover_txt = (
            f"🧾 Pedido: {t['pedido']}<br>"
            f"🏭 Máquina: {t['machine']}<br>"
            f"🕒 {t['timestamp_ini']} → {t['timestamp_fin']}<br>"
            f"👷 Operarios: {t['x_op']}<br>"
            f"⏱️ Duración: {t['duration']} min<br>"
            f"📅 Entrega requerida: {t['fecha_entrega_requerida']}<br>"
            f"📅 Entrega estimada: {t['fecha_entrega_estimada']}<br>"
            f"{diff_text}<br>"
            f"🚀 Lead time (días lab.): {t['leadtime_dias_laborales']:.2f}"
        )
        fig.add_trace(go.Bar(
            x=[t["duration"]],
            y=[t["y_label"]],
            base=[t["start"]],
            orientation="h",
            marker=dict(color=t["color"]),
            hovertext=hover_txt,
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

    for seg in timeline:
        t_ini = seg["t_ini"]
        t_fin = seg["t_fin"]
        cap = seg["operarios_turno"]
        occ = seg["ocupacion"]
        porc = seg["%ocup"]
        ts_ini = seg["timestamp_ini"]
        ts_fin = seg["timestamp_fin"]

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

        fig.add_trace(go.Scatter(
            x=[t_ini, t_fin, t_fin, t_ini],
            y=[0, 0, occ, occ],
            fill="toself",
            fillcolor="blue",
            line=dict(color="blue"),
            opacity=0.7,
            text=f"{ts_ini} → {ts_fin}<br>{occ}/{cap} → {porc}%",
            hoverinfo="text",
            showlegend=False
        ), row=2, col=1)

    fig.update_yaxes(title="Operarios activos", row=2, col=1)

    layout_title = "Planificación: Gantt + Ocupación"

    if resumen_pedidos and isinstance(resumen_pedidos, tuple):
        resumen_metr, _ = resumen_pedidos

        # Determinar el icono de retraso
        if resumen_metr["retraso_medio_dias"] == 0:
            icono_retraso = "✅"
        else:
            icono_retraso = "⚠️"

        texto_metricas = (
            f"📈 <b>Métricas globales</b><br>"
            f"• 🕓 Horas/día laborable: {resumen_metr['horas_laborables_por_dia']:.2f}<br>"
            f"• ⏱️ Lead time medio: {resumen_metr['leadtime_medio_dias']:.2f} días<br>"
            f"• {icono_retraso} Retraso medio: {resumen_metr['retraso_medio_dias']:.2f} días<br>"
            f"• 📦 Días entre entregas: {resumen_metr['dias_entre_entregas_prom']:.2f} días"
        )

        fig.add_annotation(
            text=texto_metricas,
            xref="paper", yref="paper",
            x=1.02, y=1,
            showarrow=False,
            align="left",
            bordercolor="black",
            borderwidth=1,
            bgcolor="white",
            font=dict(size=12),
        )

    fig.update_layout(
        title=layout_title,
        barmode="overlay",
        template="plotly_white",
        height=700,
        width=1200
    )

    fig.show()
