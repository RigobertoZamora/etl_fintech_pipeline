from etl.calidad_1 import (
    cargar_y_perfilar_datos, 
    imputar_faltantes, 
    tratar_outliers_iqr
)

def main():
    # Ruta del archivo basada en la estructura de tu proyecto
    ruta_atm = "datasets/transacciones_atm.csv"
    
    # --- EJECUCIÓN MÓDULO 1 (CALIDAD) ---
    df_atm, reporte_atm, meta_atm = cargar_y_perfilar_datos(ruta_atm, 'csv')
    
    # Imputación usando los nombres reales de tus columnas
    df_atm_imputado = imputar_faltantes(
        df_atm, 
        num_cols=['monto_mxn', 'comision_aplicada'], 
        cat_cols=['id_cajero', 'tipo_operacion', 'resultado'], 
        critical_cols=['id_cuenta', 'id_transaccion']
    )
    
    # Tratamiento de outliers apuntando a 'monto_mxn'
    df_atm_final, df_atm_corruptos = tratar_outliers_iqr(df_atm_imputado, 'monto_mxn')
    
    # --- VISUALIZACIÓN CENTRALIZADA ---
    print("\n=== FASE 1: DIAGNÓSTICO DE CALIDAD ===")
    print("Metadatos:", meta_atm)
    print("\nReporte de Nulos:")
    print(reporte_atm)
    
    print("\n=== FASE 3: OUTLIERS Y VALORES IMPOSIBLES ===")
    print(f"Registros válidos (Capping aplicado): {len(df_atm_final)}")
    print(f"Registros corruptos aislados (<= 0): {len(df_atm_corruptos)}")
    
    print("\n=== MUESTRA DE DATOS LIMPIOS (Primeras 5 filas) ===")
    print(df_atm_final.head())

if __name__ == "__main__":
    main()

