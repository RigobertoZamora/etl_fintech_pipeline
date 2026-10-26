"""
Módulo de Transformación e Integración (Fases 2, 3, 4 y 5)
Pipeline ETL Fintech - Grupo 2

Responsable: Ingeniero 2 - Luis Fernando Machuca (@LuisFerMCDev)
Materia: Ingeniería de Datos (ATD-2602)
Institución: Tecnológico Nacional de México - Campus Colima

Este módulo procesa los datasets crudos y perfilados por el Ingeniero 1,
aplicando:
1. FASE 2: Clasificación de ausencias (MCAR/MAR), imputación y recálculos.
2. FASE 3: Tratamiento robusto de outliers mediante Rango Intercuartílico (IQR)
   con Winsorizing/Capping e identificación de montos financieramente imposibles (<= 0).
3. FASE 4: Mapeo a esquema canónico, homologación temporal (ISO YYYY-MM-DD),
   conversión cambiaria USD a MXN ($19.50) y cruce con Core Bancario para
   marcar cuentas huérfanas sin pérdida destructiva.
4. FASE 5: Escalamiento Min-Max [0, 1] y discretización en 3 segmentos (Bajo, Medio, Alto).
"""

from typing import Any, Dict, Optional, Tuple
import numpy as np
import pandas as pd


# ==============================================================================
# FASE 2: MANEJO DE FALTANTES E IMPUTACIÓN (Ingeniero 1 / 2)
# ==============================================================================

def clasificar_ausencias(df: pd.DataFrame, nombre_dataset: str) -> Dict[str, str]:
    """
    Clasifica si los nulos de una columna son MCAR (Missing Completely At Random)
    o MAR (Missing At Random) evaluando si la ausencia correlaciona con otras variables.
    """
    reporte_ausencias = {}
    columnas_con_nulos = df.columns[df.isna().any()].tolist()

    for col in columnas_con_nulos:
        nulos_indicador = df[col].isna().astype(int)
        es_mar = False

        for otra_col in df.columns:
            if col == otra_col:
                continue

            if df[otra_col].dtype == "object":
                distribucion = nulos_indicador.groupby(df[otra_col].fillna("NULO")).mean()
                if any(distribucion > 0.5) and not all(distribucion == distribucion.iloc[0]):
                    es_mar = True
                    break

        tipo_ausencia = "MAR" if es_mar else "MCAR"
        reporte_ausencias[col] = tipo_ausencia

    return reporte_ausencias


def tratar_faltantes_e_imputar(df: pd.DataFrame, nombre_dataset: str) -> pd.DataFrame:
    """
    Imputa variables numéricas con la mediana y categóricas con etiquetas controladas.
    Justificación Estadística:
    - Se usa la MEDIANA en lugar de la media porque en finanzas las distribuciones
      presentan fuerte asimetría positiva; la media es arrastrada por transacciones
      atípicas gigantes, mientras que la mediana preserva el centro de la masa de datos.
    - Campos críticos (como identificadores o claves bancarias) no se inventan.
    """
    df_clean = df.copy()

    clasificacion = clasificar_ausencias(df_clean, nombre_dataset)
    if clasificacion:
        print(f"  Clasificación de ausencias en '{nombre_dataset}': {clasificacion}")

    cols_numericas = df_clean.select_dtypes(include=["number"]).columns
    cols_categoricas = df_clean.select_dtypes(include=["object", "string"]).columns

    for col in cols_numericas:
        if df_clean[col].isna().any():
            mediana = df_clean[col].median()
            df_clean[col] = df_clean[col].fillna(mediana)

    for col in cols_categoricas:
        if df_clean[col].isna().any():
            df_clean[col] = df_clean[col].fillna("ANONIMO")

    return df_clean


def recalcular_campos(df: pd.DataFrame, nombre_dataset: str) -> pd.DataFrame:
    """
    Recalcula campos donde la información exista en otras columnas componentes.
    Ejemplo: en transacciones_atm: monto_total_calculado = monto_mxn + comision_aplicada.
    """
    df_calc = df.copy()

    if nombre_dataset == "transacciones_atm":
        if "monto_mxn" in df_calc.columns and "comision_aplicada" in df_calc.columns:
            df_calc["monto_total_calculado"] = (
                df_calc["monto_mxn"] + df_calc["comision_aplicada"]
            )

    return df_calc


# ==============================================================================
# FASE 3: TRATAMIENTO DE OUTLIERS CON IQR Y VALORES IMPOSIBLES
# ==============================================================================

def identificar_valores_imposibles(
    df: pd.DataFrame, col_monto: str
) -> Tuple[pd.DataFrame, int]:
    """
    Identifica registros con valores financieramente imposibles (monto <= 0).
    Regla de Negocio:
    Los montos <= 0 o negativos no deben contaminar el cálculo estadístico de los
    cuartiles (Q1, Q3, IQR). Se aíslan del cálculo estadístico para no sesgar
    la distribución y se conservan para que la Fase 6 los derive a cuarentena.
    """
    df_copy = df.copy()
    conteo_imposibles = int((df_copy[col_monto] <= 0).sum())
    return df_copy, conteo_imposibles


def tratar_outliers_iqr(
    df: pd.DataFrame,
    col_monto: str,
    factor: float = 1.5,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Detecta y acota outliers numéricos mediante el método del Rango Intercuartílico (IQR de Tukey).

    Justificación Estadística (IQR vs Z-Score):
    El método Z-Score (z = (x - mu) / sigma) asume normalidad y utiliza la media y desviación estándar,
    las cuales sufren del efecto de enmascaramiento al estar previamente sesgadas por los propios outliers.
    El IQR de John Tukey se basa en los cuartiles Q1 (percentil 25) y Q3 (percentil 75), estadísticos de orden
    resistentes a las colas pesadas y asimétricas propias del dominio bancario.

    Reglas de Negocio:
    1. Prohibido eliminar filas por montos altos (Winsorizing / Capping sin pérdida destructiva).
    2. Los montos <= 0 no contaminan el cálculo de cuartiles y se mantienen inalterados
       para ser rechazados en la Fase 6 por Pydantic.
    3. Idempotencia matemática garantizada: f(f(X)) == f(X).
    """
    df_clean = df.copy()

    # Separar registros con monto financieramente válido (> 0)
    mask_operativos = df_clean[col_monto] > 0
    df_operativos = df_clean.loc[mask_operativos, col_monto]

    if len(df_operativos) == 0:
        return df_clean, {
            "q1": np.nan,
            "q3": np.nan,
            "iqr": np.nan,
            "lim_inf": np.nan,
            "lim_sup": np.nan,
            "conteo_imposibles": len(df_clean),
            "outliers_acotados": 0,
        }

    q1 = float(df_operativos.quantile(0.25))
    q3 = float(df_operativos.quantile(0.75))
    iqr = float(q3 - q1)
    lim_inf = float(q1 - factor * iqr)
    lim_sup = float(q3 + factor * iqr)

    # El límite inferior operativo en banca no debe ser negativo
    capping_lower = max(0.0, lim_inf)

    # Identificar cuántos valores superan el umbral superior
    outliers_altos = int((df_operativos > lim_sup).sum())
    conteo_imposibles = int((df_clean[col_monto] <= 0).sum())

    # Aplicar Capping / Winsorizing exclusivamente sobre las filas operativas
    df_clean.loc[mask_operativos, col_monto] = df_operativos.clip(
        lower=capping_lower, upper=lim_sup
    )

    metricas = {
        "columna": col_monto,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "lim_inf": lim_inf,
        "lim_sup": lim_sup,
        "capping_lower": capping_lower,
        "capping_upper": lim_sup,
        "conteo_imposibles": conteo_imposibles,
        "outliers_acotados": outliers_altos,
    }

    return df_clean, metricas


def ejecutar_fase_3(datasets: Dict[str, pd.DataFrame]) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Any]]:
    """
    Ejecuta el tratamiento de outliers e identificación de valores imposibles
    sobre las fuentes de transacciones (ATM y Digital).
    Garantiza además la eliminación de duplicados exactos en ATM (reintentos de cajero).
    """
    datasets_fase3 = {}
    reportes_fase3 = {}

    for nombre, df in datasets.items():
        df_proc = df.copy()

        # FASE 1/3: Eliminar reintentos duplicados exactos si existen
        if nombre == "transacciones_atm":
            duplicados_antes = df_proc.duplicated().sum()
            if duplicados_antes > 0:
                df_proc = df_proc.drop_duplicates().copy()
                print(f"  [ATM] Descartados {duplicados_antes} registros duplicados exactos (reintentos de red).")

            df_proc, metricas = tratar_outliers_iqr(df_proc, col_monto="monto_mxn")
            reportes_fase3[nombre] = metricas
            print(f"  [ATM] IQR Capping: Q1={metricas['q1']:.2f}, Q3={metricas['q3']:.2f}, "
                  f"LimSup={metricas['lim_sup']:.2f} | Outliers acotados: {metricas['outliers_acotados']} | "
                  f"Montos <= 0 aislados: {metricas['conteo_imposibles']}")

        elif nombre == "transferencias_digitales":
            df_proc, metricas = tratar_outliers_iqr(df_proc, col_monto="amount")
            reportes_fase3[nombre] = metricas
            print(f"  [DIGITAL] IQR Capping: Q1={metricas['q1']:.2f}, Q3={metricas['q3']:.2f}, "
                  f"LimSup={metricas['lim_sup']:.2f} | Outliers acotados: {metricas['outliers_acotados']} | "
                  f"Montos <= 0 aislados: {metricas['conteo_imposibles']}")

        datasets_fase3[nombre] = df_proc

    return datasets_fase3, reportes_fase3


# ==============================================================================
# FASE 4: INTEGRACIÓN, UNIFICACIÓN Y DETECCIÓN DE HUÉRFANOS
# ==============================================================================

def homologar_fecha_iso(valor: Any) -> Optional[str]:
    """
    Convierte fechas en formatos heterogéneos (DD/MM/YYYY, YYYY/MM/DD, timestamps unix
    en segundos o strings ISO con zona horaria) al formato canónico estricto 'YYYY-MM-DD'.
    Si el valor es corrupto o no convertible, retorna el string original o None para
    que sea auditado por Pydantic en la Fase 6.
    """
    if pd.isna(valor) or valor is None:
        return None

    val_str = str(valor).strip()

    try:
        # 1. Timestamps Unix en segundos (ej. 1788816180)
        if val_str.isdigit() and len(val_str) == 10:
            return pd.to_datetime(int(val_str), unit="s").strftime("%Y-%m-%d")

        # 2. Formato año inicial: YYYY/MM/DD o YYYY-MM-DD (con o sin hora/offset)
        if len(val_str) >= 4 and val_str[:4].isdigit():
            return pd.to_datetime(val_str).strftime("%Y-%m-%d")

        # 3. Formato latinoamericano: DD/MM/YYYY (ej. 12/09/2026 13:26)
        return pd.to_datetime(val_str, dayfirst=True).strftime("%Y-%m-%d")

    except Exception:
        # Mantener valor malformado para auditoría en Fase 6
        return val_str


def normalizar_clabe(valor: Any) -> Optional[str]:
    """
    Normaliza el campo CLABE bancaria:
    - Restaura ceros a la izquierda para CLABEs mexicanas estándar de 18 dígitos que
      pudieron haber sido convertidas a enteros de 17 dígitos durante la ingesta.
    - Preserva CLABEs inválidas (como '12345' de longitud 5) sin alterarlas para su
      detección en Fase 6.
    - Retorna None para transacciones de cajero ATM (no aplican CLABE).
    """
    if pd.isna(valor) or valor is None:
        return None

    val_str = str(valor).strip()
    if val_str.endswith(".0"):
        val_str = val_str[:-2]

    # Recuperación de leading zero en CLABEs de 17 dígitos
    if len(val_str) == 17 and val_str.isdigit():
        return val_str.zfill(18)

    return val_str


def homologar_moneda_mxn(row: pd.Series, col_monto: str = "amount", col_moneda: str = "currency", paridad: float = 19.50) -> float:
    """
    Convierte transacciones registradas en divisa extranjera (USD) a pesos mexicanos (MXN)
    aplicando la paridad oficial fija de $19.50 MXN por USD:
    Monto_MXN = Monto_USD * 19.50
    """
    monto = float(row[col_monto])
    moneda = str(row[col_moneda]).strip().upper() if col_moneda in row and pd.notna(row[col_moneda]) else "MXN"

    if moneda == "USD":
        return float(np.round(monto * paridad, 2))
    return float(monto)


def mapear_a_esquema_canonico(df_atm: pd.DataFrame, df_dig: pd.DataFrame) -> pd.DataFrame:
    """
    Unifica los nombres dispares de columnas entre canales hacia el esquema canónico común:
    - id_transaccion (str)
    - id_cuenta (str)
    - clabe (str o None)
    - fecha_operacion (str en ISO YYYY-MM-DD)
    - canal (str: 'ATM' o 'DIGITAL')
    - monto_mxn (float)
    - comision_mxn (float)
    """
    # 1. Mapeo ATM
    atm_mapped = pd.DataFrame({
        "id_transaccion": df_atm["id_transaccion"].astype(str),
        "id_cuenta": df_atm["id_cuenta"].astype(str),
        "clabe": None,
        "fecha_operacion": df_atm["fecha_hora"].apply(homologar_fecha_iso),
        "canal": "ATM",
        "monto_mxn": df_atm["monto_mxn"].astype(float),
        "comision_mxn": df_atm["comision_aplicada"].astype(float) if "comision_aplicada" in df_atm.columns else 0.0,
    })

    # 2. Mapeo Digital (SPEI / App)
    dig_monto_mxn = df_dig.apply(homologar_moneda_mxn, axis=1)
    dig_mapped = pd.DataFrame({
        "id_transaccion": df_dig["transfer_id"].astype(str),
        "id_cuenta": df_dig["account_id"].astype(str),
        "clabe": df_dig["beneficiary_clabe"].apply(normalizar_clabe) if "beneficiary_clabe" in df_dig.columns else None,
        "fecha_operacion": df_dig["timestamp"].apply(homologar_fecha_iso),
        "canal": "DIGITAL",
        "monto_mxn": dig_monto_mxn.astype(float),
        "comision_mxn": 0.0,  # En transferencias digitales SPEI la comisión bancaria es $0.00
    })

    df_unificado = pd.concat([atm_mapped, dig_mapped], ignore_index=True)
    return df_unificado


def detectar_cuentas_huerfanas(
    df_transacciones: pd.DataFrame, df_catalogo: pd.DataFrame
) -> pd.DataFrame:
    """
    Realiza un cruce izquierdo (left merge) contra el catálogo maestro del Core Bancario
    para detectar cuentas huérfanas.

    Regla Crítica:
    NO eliminar registros donde _merge == 'left_only'. Se genera la columna booleana
    'es_cuenta_huerfana' para que el Ingeniero 3 envíe las operaciones anómalas a
    la tabla de cuarentena sin detener el flujo del lote.
    """
    cuentas_validas = df_catalogo[["id_cuenta"]].drop_duplicates()

    df_merged = pd.merge(
        df_transacciones,
        cuentas_validas,
        on="id_cuenta",
        how="left",
        indicator=True,
    )

    df_merged["es_cuenta_huerfana"] = (df_merged["_merge"] == "left_only")
    df_merged = df_merged.drop(columns=["_merge"])

    conteo_huerfanas = int(df_merged["es_cuenta_huerfana"].sum())
    print(f"  Detección de cuentas huérfanas: {conteo_huerfanas} transacciones sin cuenta en Core Bancario.")

    return df_merged


def ejecutar_fase_4(
    datasets_fase3: Dict[str, pd.DataFrame], df_catalogo: pd.DataFrame
) -> pd.DataFrame:
    """
    Ejecuta de punta a punta la Fase 4: Schema mapping, homologación de fechas,
    conversión monetaria USD -> MXN y detección de huérfanos con el catálogo bancario.
    """
    df_atm = datasets_fase3["transacciones_atm"]
    df_dig = datasets_fase3["transferencias_digitales"]

    # 1. Homologación de esquemas y concatenación
    df_unificado = mapear_a_esquema_canonico(df_atm, df_dig)

    # 2. Cruce con el catálogo del Core Bancario
    df_con_huerfanas = detectar_cuentas_huerfanas(df_unificado, df_catalogo)

    return df_con_huerfanas


# ==============================================================================
# FASE 5: TRANSFORMACIÓN, ESCALAMIENTO Y DISCRETIZACIÓN
# ==============================================================================

def escalar_min_max(df: pd.DataFrame, col_monto: str = "monto_mxn") -> pd.DataFrame:
    """
    Normaliza la columna numérica monto_mxn al rango acotado [0, 1] en 'monto_escalado':
    x' = (x - x_min) / (x_max - x_min)

    Orden de ejecución obligatorio:
    Se ejecuta después de haber aplicado el Capping con IQR en la Fase 3 para evitar
    que los outliers compriman los valores operativos cerca de cero.
    """
    df_esc = df.copy()
    min_val = float(df_esc[col_monto].min())
    max_val = float(df_esc[col_monto].max())

    if max_val - min_val > 0:
        df_esc["monto_escalado"] = (df_esc[col_monto] - min_val) / (max_val - min_val)
    else:
        df_esc["monto_escalado"] = 0.0

    return df_esc


def discretizar_monto(
    df: pd.DataFrame,
    col_monto: str = "monto_mxn",
    n_bins: int = 3,
    etiquetas: Optional[list] = None,
) -> pd.DataFrame:
    """
    Discretiza (Binning) el importe monetario en tres segmentos ('Bajo', 'Medio', 'Alto')
    utilizando cuantiles (pd.qcut) con resolución de empates para garantizar grupos balanceados.
    """
    if etiquetas is None:
        etiquetas = ["Bajo", "Medio", "Alto"]

    df_disc = df.copy()

    try:
        df_disc["segmento_monto"] = pd.qcut(
            df_disc[col_monto],
            q=n_bins,
            labels=etiquetas,
            duplicates="drop",
        )
    except Exception:
        # Fallback a discretización por cortes uniformes en caso de distribuciones de varianza cero
        df_disc["segmento_monto"] = pd.cut(
            df_disc[col_monto],
            bins=n_bins,
            labels=etiquetas,
        )

    return df_disc


def ejecutar_fase_5(df_unificado: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica escalamiento Min-Max y discretización sobre el DataFrame unificado.
    """
    df_escalado = escalar_min_max(df_unificado, col_monto="monto_mxn")
    df_final = discretizar_monto(df_escalado, col_monto="monto_mxn")
    return df_final


# ==============================================================================
# ORQUESTACIÓN COMPLETA PARA INGENIERO 2
# ==============================================================================

def ejecutar_fase_3_y_4(
    datasets_fase2: Dict[str, pd.DataFrame],
    df_catalogo: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Punto de entrada principal para ejecutar las Fases 3, 4 y 5 del Pipeline.

    Entrada:
        datasets_fase2: Diccionario con DataFrames procesados por Fase 2.
        df_catalogo: DataFrame opcional con el Core Bancario.
    Salida:
        pd.DataFrame: DataFrame unificado con las 10 columnas obligatorias requeridas
                      por el contrato de interfaz para el Ingeniero 3.
        dict: Métricas y reportes estadísticos de ejecución.
    """
    if df_catalogo is None and "catalogo_cuentas" in datasets_fase2:
        df_catalogo = datasets_fase2["catalogo_cuentas"]

    print("\n" + "=" * 60)
    print("FASE 3: TRATAMIENTO DE OUTLIERS CON IQR Y CAPPING")
    print("=" * 60)
    datasets_fase3, metricas_f3 = ejecutar_fase_3(datasets_fase2)

    print("\n" + "=" * 60)
    print("FASE 4: INTEGRACIÓN, UNIFICACIÓN Y DETECCIÓN DE HUÉRFANOS")
    print("=" * 60)
    df_integrado = ejecutar_fase_4(datasets_fase3, df_catalogo)

    print("\n" + "=" * 60)
    print("FASE 5: TRANSFORMACIÓN, ESCALAMIENTO Y DISCRETIZACIÓN")
    print("=" * 60)
    df_final = ejecutar_fase_5(df_integrado)

    print(f"  [OK] Unificación exitosa: {len(df_final)} transacciones integradas.")
    print(f"  [OK] Esquema canónico verificado: {list(df_final.columns)}")
    print(f"  [OK] Distribución de segmentos: {dict(df_final['segmento_monto'].value_counts())}")

    print("\n" + "=" * 80)
    print("RESUMEN Y VISTA PREVIA DEL DATAFRAME UNIFICADO (INGENIERO 2)")
    print("=" * 80)
    print("\n[INFO] Estructura de tipos de datos y nulos:")
    df_final.info()
    print("\n[MUESTRA] Primeros 10 registros integrados:")
    with pd.option_context("display.max_columns", None, "display.width", 1000):
        print(df_final.head(10))
    print("=" * 80 + "\n")

    reportes = {
        "metricas_fase3": metricas_f3,
        "total_transacciones": len(df_final),
        "total_huerfanas": int(df_final["es_cuenta_huerfana"].sum()),
    }

    return df_final, reportes


def iniciar_transformacion(datasets_crudos: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """
    Función de compatibilidad con main.py.
    Ejecuta la Fase 2 (Imputación y Recálculos), y a continuación orquesta
    las Fases 3, 4 y 5, integrando todo el flujo del Ingeniero 2.

    Retorna un diccionario con los datasets transformados individuales
    y la clave 'df_unificado' con el entregable final obligatorio para el Ingeniero 3.
    """
    datasets_fase2 = {}

    for nombre, df in datasets_crudos.items():
        print(f"\n--- Procesando Fase 2: {nombre} ---")
        df_imputado = tratar_faltantes_e_imputar(df, nombre)
        df_recalculado = recalcular_campos(df_imputado, nombre)
        datasets_fase2[nombre] = df_recalculado

    # Orquestación de Fase 3, 4 y 5
    df_unificado, reportes = ejecutar_fase_3_y_4(
        datasets_fase2, df_catalogo=datasets_fase2.get("catalogo_cuentas")
    )

    resultado = dict(datasets_fase2)
    resultado["df_unificado"] = df_unificado
    resultado["reportes_transformacion"] = reportes

    return resultado


if __name__ == "__main__":
    import sys
    import importlib
    from pathlib import Path

    # Permitir ejecución directa de este script
    ruta_raiz = Path(__file__).resolve().parent.parent
    if str(ruta_raiz) not in sys.path:
        sys.path.insert(0, str(ruta_raiz))

    calidad = importlib.import_module("etl.1_calidad")
    print("Cargando fuentes de datos crudas...")
    datasets_crudos = calidad.cargar_datasets()
    iniciar_transformacion(datasets_crudos)
