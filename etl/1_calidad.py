
from pathlib import Path

import pandas as pd


# Directorio raíz del proyecto
RUTA_PROYECTO = Path(__file__).resolve().parent.parent
RUTA_DATASETS = RUTA_PROYECTO / "datasets"

# Marcadores que deben interpretarse como valores nulos
MARCADORES_NULOS = [
    "N/A",
    "null",
    "NULL",
    "-",
    "",
    "None",
    "desconocido",
]


def cargar_datasets():
    """
    Lee los tres datasets originales y los devuelve en un diccionario.
    Los marcadores de ausencia se interpretan como valores nulos.
    No elimina duplicados ni realiza limpieza adicional.
    """
    archivos = {
        "catalogo_cuentas": RUTA_DATASETS / "catalogo_cuentas.csv",
        "transacciones_atm": RUTA_DATASETS / "transacciones_atm.csv",
        "transferencias_digitales": RUTA_DATASETS / "transferencias_digitales.json",
    }

    datasets = {}

    for nombre, ruta in archivos.items():
        if not ruta.exists():
            raise FileNotFoundError(
                f"No se encontró el dataset '{nombre}': {ruta}"
            )

        if ruta.suffix.lower() == ".csv":
            df = pd.read_csv(
                ruta,
                na_values=MARCADORES_NULOS,
                keep_default_na=True,
            )
        elif ruta.suffix.lower() == ".json":
            df = pd.read_json(ruta)

            # Reconocer los marcadores de ausencia también en JSON.
            df = df.replace(MARCADORES_NULOS, float("nan"))
        else:
            raise ValueError(
                f"Formato de archivo no compatible: {ruta.suffix}"
            )

        datasets[nombre] = df

    return datasets


def perfilar_dataset(df, nombre):
    """
    Genera el diagnóstico inicial de un DataFrame sin modificarlo.

    Retorna:
        dict: resumen general, métricas por columna y duplicados.
    """
    total_filas = len(df)

    nulos_por_columna = df.isna().sum()

    if total_filas > 0:
        porcentaje_nulos = (
            nulos_por_columna / total_filas * 100
        )
    else:
        porcentaje_nulos = pd.Series(
            0.0, index=df.columns, dtype=float
        )

    reporte_columnas = pd.DataFrame({
        "dataset": nombre,
        "columna": df.columns,
        "tipo_dato": [
            str(df[columna].dtype) for columna in df.columns
        ],
        "total_nulos": [
            int(nulos_por_columna[columna])
            for columna in df.columns
        ],
        "porcentaje_nulos": [
            float(porcentaje_nulos[columna])
            for columna in df.columns
        ],
        "total_validos": [
            int(total_filas - nulos_por_columna[columna])
            for columna in df.columns
        ],
        "completitud_porcentaje": [
            float(100 - porcentaje_nulos[columna])
            for columna in df.columns
        ],
        "tipo_postgresql": [
            tipo_postgresql(df[columna])
            for columna in df.columns
        ],
    })

    duplicados_exactos = int(df.duplicated().sum())

    resumen = {
        "dataset": nombre,
        "total_filas": total_filas,
        "total_columnas": len(df.columns),
        "duplicados_exactos": duplicados_exactos,
    }

    return {
        "resumen": resumen,
        "columnas": reporte_columnas,
    }


def generar_reporte_calidad(datasets=None):
    """
    Perfila todos los datasets y devuelve los reportes crudos.

    Puede recibir los DataFrames previamente cargados o cargarlos
    automáticamente si no se proporciona ningún argumento.
    """
    if datasets is None:
        datasets = cargar_datasets()

    reportes = {}

    for nombre, df in datasets.items():
        reportes[nombre] = perfilar_dataset(df, nombre)

    return reportes


def tipo_postgresql(serie):
    """
    Sugiere un tipo de dato PostgreSQL a partir del dtype de pandas.
    Es una sugerencia técnica que puede requerir reglas de negocio.
    """
    tipo = str(serie.dtype)

    if tipo == "bool":
        return "BOOLEAN"
    elif tipo.startswith("int"):
        return "BIGINT"
    elif tipo.startswith("float"):
        return "DOUBLE PRECISION"
    elif tipo.startswith("datetime"):
        return "TIMESTAMP"
    elif tipo.startswith("timedelta"):
        return "INTERVAL"
    else:
        return "TEXT"
