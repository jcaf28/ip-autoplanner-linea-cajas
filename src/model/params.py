# PATH: src/model/params.py

"""
Archivo de parámetros para el modelo de planificación.
Aquí se centralizan las constantes que podrían necesitar ajustes.
"""

# ======================================================================
# PARÁMETROS DE INICIALIZACIÓN (WARM START)
# ======================================================================

# Número de días LABORABLES de anticipación para la recepción de materiales
# Este es el parámetro principal para el "warm start"
DIAS_LABORABLES_ANTICIPACION = 17  # <--- PARÁMETRO DE WARM START PRINCIPAL

# Número mínimo de días LABORABLES necesarios antes de la entrega
# Restringe que la fecha calculada no sea demasiado cercana a la entrega
DIAS_LABORABLES_MINIMOS = 3  # <--- Restricción de tiempo mínimo

# ======================================================================
# PESOS PARA LA FUNCIÓN OBJETIVO
# ======================================================================

# Peso para minimizar tardiness (entregas a tiempo) - PRIORIDAD ALTA
PESO_TARDINESS = 10000

# Peso para minimizar makespan - PRIORIDAD MEDIA
PESO_MAKESPAN = 10

# Peso para maximizar fechas de recepción - PRIORIDAD BAJA
# Un valor negativo porque estamos minimizando, queremos fechas más tardías
PESO_RECEPCION = -1