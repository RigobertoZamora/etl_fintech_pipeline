"""
Pipeline ETL Fintech - Orquestador Principal (Grupo 2)
Materia: Ingeniería de Datos (ATD-2602)
Tecnológico Nacional de México - Campus Colima

Este script orquesta la ejecución secuencial de los módulos del equipo:
- FASE 1: Calidad y Perfilado (Ingeniero 1: Erick Moisés Urbina)
- FASES 2 a 5: Transformación, Outliers e Integración (Ingeniero 2: Luis Fernando Machuca)
- FASES 6 y 7: Validación Pydantic y Carga Transaccional (Ingeniero 3: Bruno Rigoberto Zamora)
"""

from pathlib import Path
import importlib
import pandas as pd

# ------------------------------------------------------------------------------
# IMPORTACIÓN MODULAR
# ------------------------------------------------------------------------------
calidad = importlib.import_module("etl.calidad_1")

transformacion = importlib.import_module("etl.transformacion_2")

validacion = importlib.import_module("etl.validacion_bd_3")


def main():
    print("=" * 70)
    print("PIPELINE ETL FINTECH - GRUPO 2")
    print("=" * 70)

    # ==========================================================================
    # FASE 1: DIAGNÓSTICO DE CALIDAD INICIAL (INGENIERO 1)
    # ==========================================================================
    print("\n" + "=" * 60)
    print("FASE 1: DIAGNÓSTICO DE CALIDAD INICIAL (INGENIERO 1)")
    print("=" * 60)

    ruta_datasets = Path(__file__).resolve().parent / "datasets"

    df_cuentas, rep_cuentas, meta_cuentas = calidad.cargar_y_perfilar_datos(
        str(ruta_datasets / "catalogo_cuentas.csv"), "csv"
    )
    df_atm, rep_atm, meta_atm = calidad.cargar_y_perfilar_datos(
        str(ruta_datasets / "transacciones_atm.csv"), "csv"
    )
    df_dig, rep_dig, meta_dig = calidad.cargar_y_perfilar_datos(
        str(ruta_datasets / "transferencias_digitales.json"), "json"
    )

    print(f"\n[ATM] Filas: {meta_atm['filas_originales']} | Duplicados eliminados: {meta_atm['duplicados_eliminados']}")
    print(f"[DIGITAL] Filas: {meta_dig['filas_originales']} | Duplicados eliminados: {meta_dig['duplicados_eliminados']}")
    print(f"[CATÁLOGO] Filas: {meta_cuentas['filas_originales']}")

    datasets_crudos = {
        "catalogo_cuentas": df_cuentas,
        "transacciones_atm": df_atm,
        "transferencias_digitales": df_dig,
    }

    # ==========================================================================
    # FASES 2 A 5: TRANSFORMACIÓN, OUTLIERS E INTEGRACIÓN (INGENIERO 2)
    # ==========================================================================
    print("\n" + "=" * 60)
    print("FASES 2 A 5: TRANSFORMACIÓN, OUTLIERS E INTEGRACIÓN (INGENIERO 2)")
    print("=" * 60)

    resultado_transformacion = transformacion.iniciar_transformacion(datasets_crudos)
    df_unificado = resultado_transformacion["df_unificado"]

    print(f"[OK] Fases 1 a 5 ejecutadas exitosamente.")
    print(f"[ENTREGABLE PARA INGENIERO 3] DataFrame unificado listo: "
          f"{df_unificado.shape[0]} filas x {df_unificado.shape[1]} columnas.")

    # ==========================================================================
    # FASES 6 Y 7: VALIDACIÓN PYDANTIC Y CARGA TRANSACCIONAL (INGENIERO 3)
    # ==========================================================================
    print("\n" + "=" * 60)
    print("FASES 6 Y 7: VALIDACIÓN PYDANTIC Y CARGA A POSTGRESQL")
    print("=" * 60)

    # Aquí entra en acción tu módulo recibiendo la tabla unificada
    validacion.iniciar_validacion_y_carga(df_unificado)

    print("\n" + "=" * 70)
    print("PIPELINE ETL COMPLETADO EXITOSAMENTE")
    print("=" * 70)

    return df_unificado


if __name__ == "__main__":
    main()
