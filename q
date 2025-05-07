[1mdiff --git a/src/model/time_management.py b/src/model/time_management.py[m
[1mindex 90e6e69..d0e2e65 100644[m
[1m--- a/src/model/time_management.py[m
[1m+++ b/src/model/time_management.py[m
[36m@@ -97,7 +97,6 @@[m [mdef descomprimir_tiempo(t, df_calend, modo="ini"):[m
     print(f"⚠️ [WARNING] Tiempo {t} fuera del calendario definido. No se puede descomprimir.")[m
     return None[m
 [m
[31m-[m
 def comprimir_tiempo(dt, df_calend):[m
     """[m
     Convierte una fecha/hora dt a un número de minutos acumulados en df_calend.[m
[36m@@ -155,7 +154,6 @@[m [mdef comprimir_tiempo(dt, df_calend):[m
     # Si dt es posterior al último turno[m
     return turnos[-1][3][m
 [m
[31m-[m
 def construir_timeline_detallado(tareas, intervals, capacity_per_interval):[m
     """[m
     Devuelve una lista de diccionarios, cada uno con:[m
[36m@@ -221,7 +219,6 @@[m [mdef construir_timeline_detallado(tareas, intervals, capacity_per_interval):[m
 [m
     return timeline[m
 [m
[31m-[m
 def calcular_dias_laborables(ts_inicio, ts_fin, df_calend):[m
     """[m
     Devuelve el número decimal de días laborables entre dos timestamps, considerando turnos nocturnos.[m
[36m@@ -264,7 +261,6 @@[m [mdef calcular_dias_laborables(ts_inicio, ts_fin, df_calend):[m
     seg_por_dia = horas_por_dia * 3600[m
     return round(total_seg_laborales / seg_por_dia, 2)[m
 [m
[31m-[m
 def calcular_promedio_horas_laborables_por_dia(df_calend):[m
     """[m
     Calcula cuántas horas laborables hay en promedio por día natural (según df_calend).[m
