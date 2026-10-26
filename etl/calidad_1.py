import pandas as pd
import numpy as np
import os

# Valores nulos disfrazados a interceptar
NA_VALUES = ["N/A", "null", "NULL", "-", "", "None", "desconocido"]

def cargar_y_perfilar_datos(ruta_archivo: str, tipo: str = 'csv') -> tuple:
    """
    FASE 1: Diagnóstico de Calidad Inicial.
    Carga el archivo, detecta nulos disfrazados, calcula completitud, 
    elimina duplicados exactos y audita dtypes.
    """
    # 1. Ingesta y detección de nulos disfrazados
    if tipo == 'csv':
        df = pd.read_csv(ruta_archivo, na_values=NA_VALUES, keep_default_na=True)
    elif tipo == 'json':
        df = pd.read_json(ruta_archivo)
        df.replace(NA_VALUES, np.nan, inplace=True)
    else:
        raise ValueError("Tipo de archivo no soportado. Usa 'csv' o 'json'.")

    total_filas_original = len(df)
    
    # 3. Unicidad: Contar y eliminar duplicados exactos
    df_limpio = df.drop_duplicates().copy()
    duplicados_eliminados = total_filas_original - len(df_limpio)
    
    # 2. y 4. Métrica de Completitud e Inferencia de Tipos
    reporte_calidad = []
    for col in df_limpio.columns:
        nulos = df_limpio[col].isnull().sum()
        completitud = (1 - (nulos / len(df_limpio))) * 100 if len(df_limpio) > 0 else 0
        reporte_calidad.append({
            'columna': col,
            'tipo_dato': str(df_limpio[col].dtype),
            'nulos_detectados': nulos,
            'completitud_porcentaje': round(completitud, 2)
        })
    
    df_reporte = pd.DataFrame(reporte_calidad)
    
    metadata = {
        'archivo': os.path.basename(ruta_archivo),
        'filas_originales': total_filas_original,
        'filas_tras_deduplicar': len(df_limpio),
        'duplicados_eliminados': duplicados_eliminados
    }
    
    return df_limpio, df_reporte, metadata

def imputar_faltantes(df: pd.DataFrame, num_cols: list, cat_cols: list, critical_cols: list) -> pd.DataFrame:
    """
    FASE 2: Manejo de Faltantes e Imputación.
    Usa la mediana para numéricos y etiquetas para categóricos, respetando columnas críticas.
    """
    df_imputado = df.copy() # Idempotencia
    
    # Imputación Numérica (Mediana)
    for col in num_cols:
        if col in df_imputado.columns and col not in critical_cols:
            mediana = df_imputado[col].median()
            df_imputado[col] = df_imputado[col].fillna(mediana)
            
    # Imputación Categórica
    for col in cat_cols:
        if col in df_imputado.columns and col not in critical_cols:
            df_imputado[col] = df_imputado[col].fillna('SIN_DESCRIPCION')
            
    # Las critical_cols (como id_cuenta, clabe o comisiones estrictas) se dejan con NaN 
    # para que Pydantic las mande a cuarentena en la Fase 6.
    
    return df_imputado

def tratar_outliers_iqr(df: pd.DataFrame, col_monto: str) -> tuple:
    """
    FASE 3: Tratamiento de Outliers con IQR y Valores Imposibles.
    Separa montos <= 0 y aplica Capping/Winsorizing a los extremos superiores.
    """
    if col_monto not in df.columns:
        return df.copy(), pd.DataFrame()
        
    df_procesado = df.copy() # Idempotencia
    
    # 1. Separar Valores Imposibles (Monto <= 0)
    mascara_imposibles = df_procesado[col_monto] <= 0
    df_imposibles = df_procesado[mascara_imposibles].copy()
    df_validos = df_procesado[~mascara_imposibles].copy()
    
    if len(df_validos) > 0:
        # 2. Detección Robusta mediante IQR (Solo sobre valores válidos)
        Q1 = df_validos[col_monto].quantile(0.25)
        Q3 = df_validos[col_monto].quantile(0.75)
        IQR = Q3 - Q1
        
        limite_inf = Q1 - 1.5 * IQR
        limite_sup = Q3 + 1.5 * IQR
        
        # 3. Aplicación de Capping (Winsorizing) sin pérdida destructiva
        # Acotamos los montos válidos al límite superior (los inferiores <= 0 ya se separaron)
        df_validos[col_monto] = df_validos[col_monto].clip(upper=limite_sup)
        
    return df_validos, df_imposibles

# ==========================================
# EJEMPLO DE ORQUESTACIÓN DEL MÓDULO
# ==========================================
if __name__ == "__main__":
    # Rutas relativas basadas en la estructura del proyecto
    ruta_atm = "../datasets/transacciones_atm.csv"
    
    # 1. FASE 1: Perfilado
    # df_atm, reporte_atm, meta_atm = cargar_y_perfilar_datos(ruta_atm, 'csv')
    
    # 2. FASE 2: Imputación
    # df_atm_imputado = imputar_faltantes(
    #     df_atm, 
    #     num_cols=['monto', 'comision'], 
    #     cat_cols=['sucursal', 'concepto'], 
    #     critical_cols=['id_cuenta', 'id_transaccion'] # No imputar nulos críticos
    # )
    
    # 3. FASE 3: Outliers
    # df_atm_final, df_atm_corruptos = tratar_outliers_iqr(df_atm_imputado, 'monto')
    
    pass