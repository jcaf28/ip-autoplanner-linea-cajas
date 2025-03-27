# PATH: src/results_gen/guardar_resultados_raw.py

import os
import pickle
from datetime import datetime
def guardar_resultados_raw(df_capac, tareas, timeline, resumen_pedidos, output_dir, ruta_archivo_base):
    raw_dir = os.path.join(output_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    nombre_base = os.path.splitext(os.path.basename(ruta_archivo_base))[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"{nombre_base}_{timestamp}.pkl"
    raw_path = os.path.join(raw_dir, nombre_archivo)

    with open(raw_path, "wb") as f:
        pickle.dump({
            "capacidades": df_capac,
            "tareas": tareas,
            "timeline": timeline,
            "resumen_pedidos": resumen_pedidos  # 👈 se guarda también
        }, f)

    print(f"\n✅ Resultados crudos guardados correctamente:")
    print(f"   - 📁 Ruta: {raw_path}")
    print(f"   - 🧾 Tablas guardadas:")
    print(f"       • capacidades ({len(df_capac)} registros)")
    print(f"       • tareas ({len(tareas)} registros)")
    print(f"       • timeline ({len(timeline)} eventos)")
    if resumen_pedidos:
        print(f"       • resumen_pedidos (incluye métricas + dataframe de pedidos)")

