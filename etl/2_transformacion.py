import pandas as pd
import numpy as np

def clasificar_ausencias(df, nombre_dataset):
    """
    Clasifica si los nulos de una columna son MCAR (Missing Completely At Random)
    o MAR (Missing At Random) evaluando si la ausencia correlaciona con otras variables.
    """
    reporte_ausencias = {}
    columnas_con_nulos = df.columns[df.isna().any()].tolist()
    
    for col in columnas_con_nulos:
        # Creamos una variable booleana: 1 si es nulo, 0 si no lo es
        nulos_indicador = df[col].isna().astype(int)
        es_mar = False
        
        # Comparamos contra las demás columnas para ver si hay un patrón
        for otra_col in df.columns:
            if col == otra_col:
                continue
                
            # Si la otra columna es categórica, verificamos si un valor específico concentra los nulos
            if df[otra_col].dtype == 'object':
                distribucion = nulos_indicador.groupby(df[otra_col].fillna('NULO')).mean()
                # Si en alguna categoría más del 50% son nulos, hay dependencia (MAR)
                if any(distribucion > 0.5) and not all(distribucion == distribucion.iloc[0]):
                    es_mar = True
                    break
        
        tipo_ausencia = "MAR" if es_mar else "MCAR"
        reporte_ausencias[col] = tipo_ausencia
        
    return reporte_ausencias

def tratar_faltantes_e_imputar(df, nombre_dataset):
    """
    Imputa variables numéricas con la mediana y categóricas con etiquetas controladas.
    Justificación Numéricas: Se usa la MEDIANA en lugar de la MEDIA porque la mediana 
    es robusta ante valores atípicos (outliers) como montos absurdos o negativos, 
    mientras que la media se sesgaría drásticamente arruinando la distribución real.
    """
    df_clean = df.copy()
    
    # 1. Clasificar las ausencias antes de imputar
    clasificacion = clasificar_ausencias(df_clean, nombre_dataset)
    if clasificacion:
        print(f"  Clasificación de ausencias en '{nombre_dataset}': {clasificacion}")
    
    # 2. Separar columnas por tipo de dato
    cols_numericas = df_clean.select_dtypes(include=['number']).columns
    cols_categoricas = df_clean.select_dtypes(include=['object', 'string']).columns
    
    # 3. Imputar Numéricas con la Mediana
    for col in cols_numericas:
        if df_clean[col].isna().any():
            mediana = df_clean[col].median()
            df_clean[col] = df_clean[col].fillna(mediana)
            
    # 4. Imputar Categóricas con Etiqueta Controlada
    for col in cols_categoricas:
        if df_clean[col].isna().any():
            df_clean[col] = df_clean[col].fillna('ANONIMO')
            
    return df_clean

def recalcular_campos(df, nombre_dataset):
    """
    Recalcula campos donde la información exista en otras columnas.
    """
    df_calc = df.copy()
    
    # Ejemplo para transacciones_atm: monto_total = monto_mxn + comision_aplicada
    if nombre_dataset == "transacciones_atm":
        if 'monto_mxn' in df_calc.columns and 'comision_aplicada' in df_calc.columns:
            df_calc['monto_total_calculado'] = df_calc['monto_mxn'] + df_calc['comision_aplicada']
            
    return df_calc

def iniciar_transformacion(datasets_crudos):
    """
    Recibe los datasets crudos desde la Fase 1, aplica el tratamiento de 
    faltantes, recálculos y devuelve los DataFrames transformados.
    """
    datasets_transformados = {}
    
    for nombre, df in datasets_crudos.items():
        print(f"\n--- Procesando Fase 2: {nombre} ---")
        # 1. Manejo de faltantes
        df_imputado = tratar_faltantes_e_imputar(df, nombre)
        # 2. Recálculo de campos derivados
        df_recalculado = recalcular_campos(df_imputado, nombre)
        
        datasets_transformados[nombre] = df_recalculado
        
    return datasets_transformados