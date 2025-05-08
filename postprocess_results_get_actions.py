#!/usr/bin/env python3
"""
postprocess_results_get_actions.py

Lee un .xlsx producido por el planificador, corrige el decalaje entre `t_idx`
y `id_interno`, calcula la hoja **Acciones** y crea una copia del archivo con
nombre `<original>_actions_<timestamp>.xlsx`.

Para esta fase se supone que hay **5 operarios** disponibles en total; la
columna *Operarios disponibles* mostrará cuántos quedan libres (no negativos)
y *Ocupación_%* reflejará el porcentaje sobre esos 5.

Requisitos:
    - pandas  >= 1.5
    - openpyxl
    - tkinter (viene en la distro estándar de Python)
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import sys
import tkinter as tk
from tkinter import filedialog

import pandas as pd

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ──────────────────────────────────────────────────────────────────────────────
ACCIONES_SHEET = "Acciones"
TIMESTAMP_FMT  = "%Y%m%d_%H%M%S"
OPERARIOS_MAX  = 5                          # ← hard-codeado por ahora

# ──────────────────────────────────────────────────────────────────────────────
# UTILIDADES DE ENTRADA / SALIDA
# ──────────────────────────────────────────────────────────────────────────────
def seleccionar_excel() -> Path:
    """Abre un diálogo y devuelve la ruta del Excel seleccionado."""
    tk_root = tk.Tk()
    tk_root.withdraw()                                    # Oculta ventana raíz
    ruta = filedialog.askopenfilename(
        title="Selecciona el fichero de resultados",
        filetypes=[("Excel files", "*.xlsx")],
    )
    tk_root.destroy()
    if not ruta:
        sys.exit("❌  No se seleccionó ningún archivo.")
    return Path(ruta)


def guardar_excel(
    original: Path,
    hojas_originales: dict[str, pd.DataFrame],
    acciones: pd.DataFrame,
) -> Path:
    """Escribe todas las hojas originales + Acciones a una copia del Excel."""
    nombre_salida = f"{original.stem}_actions_{datetime.now().strftime(TIMESTAMP_FMT)}.xlsx"
    ruta_salida   = original.with_name(nombre_salida)

    with pd.ExcelWriter(ruta_salida, engine="openpyxl") as writer:
        for nombre, df in hojas_originales.items():
            df.to_excel(writer, sheet_name=nombre, index=False)
        acciones.to_excel(writer, sheet_name=ACCIONES_SHEET, index=False)

    return ruta_salida


# ──────────────────────────────────────────────────────────────────────────────
# CARGA DE DATOS
# ──────────────────────────────────────────────────────────────────────────────
def cargar_hojas(path: Path) -> dict[str, pd.DataFrame]:
    """Carga las hojas necesarias en un diccionario."""
    hojas = {
        "Capacidades":       None,
        "Planificación tareas": None,
        "TAREAS":            None,
    }
    xls = pd.ExcelFile(path)
    for hoja in hojas:
        if hoja not in xls.sheet_names:
            sys.exit(f"❌  Falta la hoja '{hoja}' en el Excel.")
        hojas[hoja] = pd.read_excel(path, sheet_name=hoja)

    return hojas


# ──────────────────────────────────────────────────────────────────────────────
# AJUSTE DEL DECALAJE t_idx → id_interno
# ──────────────────────────────────────────────────────────────────────────────
def ajustar_t_idx(plan: pd.DataFrame) -> pd.DataFrame:
    """
    Corrige el decalaje: en versiones actuales `t_idx` empieza en 0
    mientras que `id_interno` empieza en 1.  Se suma +1 a todos los índices
    sólo si se detecta necesario.
    """
    plan = plan.copy()
    plan["t_idx"] = plan["t_idx"].astype(int)

    if plan["t_idx"].min() == 0 and (plan["t_idx"] + 1).isin(plan["t_idx"].unique()).sum() == 0:
        plan["t_idx"] += 1

    return plan


# ──────────────────────────────────────────────────────────────────────────────
# CONSTRUCCIÓN DE EVENTOS (INICIO/FINAL)
# ──────────────────────────────────────────────────────────────────────────────
def generar_eventos(plan: pd.DataFrame) -> pd.DataFrame:
    """
    Devuelve un DataFrame con un evento por fila:
        • timestamp
        • tipo       : 'INICIO' | 'FINAL'
        • pedido     : pedido involucrado
        • t_idx      : id interno de la tarea
        • x_op       : operarios implicados
    """
    eventos_ini  = plan[["timestamp_ini", "pedido", "t_idx", "x_op"]].copy()
    eventos_fin  = plan[["timestamp_fin", "pedido", "t_idx", "x_op"]].copy()

    eventos_ini.columns = ["timestamp", "pedido", "t_idx", "x_op"]
    eventos_fin.columns = eventos_ini.columns
    eventos_ini["tipo"] = "INICIO"
    eventos_fin["tipo"] = "FINAL"

    eventos = pd.concat([eventos_fin, eventos_ini])          # FINAL antes que INICIO
    eventos["timestamp"] = pd.to_datetime(eventos["timestamp"])
    eventos.sort_values(["timestamp", "tipo"], inplace=True) # 'FINAL' < 'INICIO'
    eventos.reset_index(drop=True, inplace=True)
    return eventos


# ──────────────────────────────────────────────────────────────────────────────
# FÁBRICA DE FILAS PARA ACCIONES
# ──────────────────────────────────────────────────────────────────────────────
def construir_acciones(
    eventos: pd.DataFrame,
    tareas: pd.DataFrame,
    capacidades: pd.DataFrame,
) -> pd.DataFrame:
    """
    Itera eventos secuencialmente, actualizando la ocupación por ubicación y
    construyendo la tabla Acciones.
    """
    tareas_idx = tareas.set_index("id_interno")
    cap_idx    = capacidades.set_index("ubicación")

    ubic_cols     = cap_idx["nom_ubicacion"].tolist()
    ocupacion_loc = {u: 0 for u in cap_idx.index}          # estado mutable

    filas = []
    for _, ev in eventos.iterrows():
        try:
            t_row = tareas_idx.loc[int(ev.t_idx)]
        except KeyError:
            t_row = tareas.iloc[int(ev.t_idx) - 1]         # fallback

        ubi_id     = t_row["ubicación"]
        ubi_nombre = t_row["nom_ubicacion"]
        delta      = ev.x_op if ev.tipo == "INICIO" else -ev.x_op
        ocupacion_loc[ubi_id] += delta

        ocupados_totales = sum(ocupacion_loc.values())
        disponibles      = max(OPERARIOS_MAX - ocupados_totales, 0)
        porcentaje_ocup  = round(100 * ocupados_totales / OPERARIOS_MAX, 2)

        accion_palabra = "iniciar" if ev.tipo == "INICIO" else "terminar"
        frase = (
            f'{accion_palabra} tarea {t_row["tipo_tarea"].lower()} '
            f'"{t_row["descripcion"]}" '
            f'de {ev.pedido} en {ubi_nombre}'
        )

        fila = {
            "Timestamp":             ev.timestamp,
            "Tipo_accion":           ev.tipo,
            "Acción":                frase,
            "Pedido_involucrado":    ev.pedido,
            "Operarios disponibles": disponibles,
            "Operarios ocupados":    ocupados_totales,
            "Ocupación_%":           porcentaje_ocup,
        }
        # Añadir ocupación por ubicación
        for uid, nombre in zip(cap_idx.index, ubic_cols):
            fila[nombre] = ocupacion_loc[uid]

        filas.append(fila)

    acciones = pd.DataFrame(filas)
    acciones.sort_values("Timestamp", inplace=True)
    return acciones


# ──────────────────────────────────────────────────────────────────────────────
# PUNTO DE ENTRADA
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    ruta_excel     = seleccionar_excel()
    hojas_orig     = cargar_hojas(ruta_excel)

    capacidades_df = hojas_orig["Capacidades"]
    plan_df        = ajustar_t_idx(hojas_orig["Planificación tareas"])
    tareas_df      = hojas_orig["TAREAS"]

    eventos_df     = generar_eventos(plan_df)
    acciones_df    = construir_acciones(eventos_df, tareas_df, capacidades_df)

    ruta_salida    = guardar_excel(ruta_excel, hojas_orig, acciones_df)
    print(f"✅  Hoja '{ACCIONES_SHEET}' generada correctamente → {ruta_salida}")


if __name__ == "__main__":
    main()
