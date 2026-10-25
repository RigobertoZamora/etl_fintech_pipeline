"""
Pruebas de Validación y Conformidad para Fases 3 y 4 (y 5)
Ingeniero 2 - Luis Fernando Machuca Carrillo (@LuisFerMCDev)
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Asegurar path
RUTA_RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RUTA_RAIZ))

calidad = __import__("etl.1_calidad", fromlist=["cargar_datasets"])
transformacion = __import__("etl.2_transformacion", fromlist=[
    "tratar_outliers_iqr", "homologar_fecha_iso", "homologar_moneda_mxn",
    "normalizar_clabe", "ejecutar_fase_3", "ejecutar_fase_4", "ejecutar_fase_5",
    "iniciar_transformacion"
])

def test_pipeline_completo():
    print("=== INICIANDO VALIDACIÓN DE REQUISITOS TÉCNICOS ===")
    
    # 1. Carga
    ds_crudos = calidad.cargar_datasets()
    assert "catalogo_cuentas" in ds_crudos
    assert "transacciones_atm" in ds_crudos
    assert "transferencias_digitales" in ds_crudos
    print("  [PASÓ] Carga de fuentes crudas correcta.")

    # 2. Idempotencia de IQR Capping
    df_atm = ds_crudos["transacciones_atm"].copy()
    df_c1, m1 = transformacion.tratar_outliers_iqr(df_atm, "monto_mxn")
    df_c2, m2 = transformacion.tratar_outliers_iqr(df_c1, "monto_mxn")
    assert df_c1["monto_mxn"].equals(df_c2["monto_mxn"]), "Falla en requisito de idempotencia f(f(X)) == f(X)"
    print("  [PASÓ] Requisito de Idempotencia f(f(X)) = f(X) verificado.")

    # 3. Aislamiento de valores <= 0
    conteo_le_0_antes = (df_atm["monto_mxn"] <= 0).sum()
    conteo_le_0_despues = (df_c1["monto_mxn"] <= 0).sum()
    assert conteo_le_0_antes == conteo_le_0_despues, "Los montos <= 0 fueron modificados indebidamente"
    print(f"  [PASÓ] Montos <= 0 preservados sin sesgar cuartiles ({conteo_le_0_despues} registros).")

    # 4. Capping sin pérdida destructiva de filas
    assert len(df_c1) == len(df_atm), "Se eliminaron filas durante el capping"
    print("  [PASÓ] Conservación íntegra de registros tras Winsorizing/Capping.")

    # 5. Homologación de fechas
    fechas_prueba = ["2026/09/15 08:45:00", "12/09/2026 13:26", "2026-10-12 22:22:00", 1788816180, "2026-09-12T19:49:00-06:00"]
    for f in fechas_prueba:
        f_iso = transformacion.homologar_fecha_iso(f)
        assert len(f_iso) == 10 and f_iso[4] == "-" and f_iso[7] == "-", f"Fecha no cumple ISO YYYY-MM-DD: {f} -> {f_iso}"
    print("  [PASÓ] Homologación temporal estricta a ISO YYYY-MM-DD.")

    # 6. Conversión cambiaria USD -> MXN
    row_usd = pd.Series({"amount": 1000.0, "currency": "USD"})
    row_mxn = pd.Series({"amount": 1000.0, "currency": "MXN"})
    assert transformacion.homologar_moneda_mxn(row_usd, paridad=19.50) == 19500.0, "Conversión USD a MXN incorrecta"
    assert transformacion.homologar_moneda_mxn(row_mxn, paridad=19.50) == 1000.0, "Conversión MXN incorrecta"
    print("  [PASÓ] Conversión cambiaria USD @ $19.50 MXN verificada.")

    # 7. Normalización de CLABE
    assert transformacion.normalizar_clabe("012210100614023846") == "012210100614023846"
    assert transformacion.normalizar_clabe(12210100614023846) == "012210100614023846", "No recuperó el zero a la izquierda de CLABE de 17 dígitos"
    assert transformacion.normalizar_clabe("12345") == "12345", "Modificó erróneamente CLABE corta de cuarentena"
    print("  [PASÓ] Preservación y recuperación de CLABEs válidas y detección de inválidas.")

    # 8. Ejecución completa del pipeline
    res = transformacion.iniciar_transformacion(ds_crudos)
    df_u = res["df_unificado"]

    # 9. Verificación de columnas obligatorias
    cols_esperadas = [
        "id_transaccion", "id_cuenta", "clabe", "fecha_operacion",
        "canal", "monto_mxn", "comision_mxn", "es_cuenta_huerfana",
        "monto_escalado", "segmento_monto"
    ]
    for col in cols_esperadas:
        assert col in df_u.columns, f"Columna requerida ausente: {col}"
    print(f"  [PASÓ] Las 10 columnas canónicas obligatorias están presentes.")

    # 10. Verificación de cuentas huérfanas
    huerfanas = df_u["es_cuenta_huerfana"].sum()
    assert huerfanas == 61, f"Se esperaban 61 transacciones huérfanas, encontradas: {huerfanas}"
    print(f"  [PASÓ] Detección exacta de 61 cuentas huérfanas marcadas con indicador booleano.")

    # 11. Escalamiento Min-Max
    assert df_u["monto_escalado"].min() >= 0.0 and df_u["monto_escalado"].max() <= 1.0, "Escalamiento fuera del rango [0, 1]"
    print("  [PASÓ] Escalamiento Min-Max acotado exactamente en [0, 1].")

    # 12. Discretización
    categorias_presentes = set(df_u["segmento_monto"].unique())
    assert {"Bajo", "Medio", "Alto"}.issubset(categorias_presentes), "Faltan segmentos ordinales"
    print(f"  [PASÓ] Discretización en 3 segmentos completada: {categorias_presentes}.")

    print("\n>>> TODAS LAS PRUEBAS TÉCNICAS PASARON SATISFACTORIAMENTE (100% CUMPLIMIENTO). <<<")

if __name__ == "__main__":
    test_pipeline_completo()
