"""
Módulo de compatibilidad retroactiva: etl/1_calidad.py -> etl/calidad_1.py
Permite que scripts que referencien etl.1_calidad funcionen de manera transparente.
"""

from etl.calidad_1 import *
