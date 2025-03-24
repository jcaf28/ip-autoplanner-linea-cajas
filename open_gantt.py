# PATH: open_gantt.py

def load_and_show_gantt():
    """
    Carga y muestra la última figura de Gantt guardada, regenerando la interactividad de mplcursors.
    """
    import os
    import pickle
    import mplcursors
    import matplotlib.pyplot as plt

    gantt_dir = "archivos/db_dev/output/gantt"
    if not os.path.exists(gantt_dir):
        print("❌ No existe la carpeta de Gantt.")
        return

    # Buscar los archivos .pkl ordenados por fecha (última modificación)
    gantt_files = sorted(
        [f for f in os.listdir(gantt_dir) if f.endswith(".pkl")],
        key=lambda x: os.path.getmtime(os.path.join(gantt_dir, x))
    )
    if not gantt_files:
        print("❌ No hay diagramas de Gantt guardados.")
        return

    latest_file = gantt_files[-1]
    file_path = os.path.join(gantt_dir, latest_file)

    with open(file_path, "rb") as f:
        fig, artists, tooltips = pickle.load(f)

    print(f"📌 Cargando diagrama de Gantt: {file_path}")

    # Reconectar tooltips con mplcursors
    cursor = mplcursors.cursor(artists, hover=True, highlight=True, multiple=False)
    @cursor.connect("add")
    def on_add(sel):
        i = artists.index(sel.artist)
        sel.annotation.set_text(tooltips[i])
        sel.annotation.get_bbox_patch().set(fc="white", alpha=0.8)

    # Asegurarse de que figure se vincule al entorno de pyplot
    plt.figure(fig.number)
    plt.show(block=True)  # Mantiene la ventana abierta hasta que el usuario la cierre

if __name__ == '__main__':
    load_and_show_gantt()