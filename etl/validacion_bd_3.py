"""
Módulo de Validación y Resiliencia (Fases 6 y 7)
Pipeline ETL Fintech - Grupo 2

Responsable: Ingeniero 3 - Bruno Rigoberto Zamora
Materia: Ingeniería de Datos (ATD-2602)
"""

import pandas as pd
from pydantic import BaseModel, field_validator, ValidationError
from sqlalchemy import create_engine
from typing import Optional

# ==============================================================================
# FASE 6: VALIDACIÓN ESTRICTA CON PYDANTIC
# ==============================================================================

class TransaccionBancaria(BaseModel):
    """
    Esquema estricto para validar las 10 columnas que entrega el Ingeniero 2.
    """
    id_transaccion: str
    id_cuenta: str
    clabe: Optional[str]  # Es opcional porque los retiros en cajero ATM no usan CLABE
    fecha_operacion: str
    canal: str
    monto_mxn: float
    comision_mxn: float
    es_cuenta_huerfana: bool
    monto_escalado: float
    segmento_monto: str

    # 1. Regla: Cuenta Huérfana
    @field_validator('es_cuenta_huerfana')
    @classmethod
    def validar_cuenta_huerfana(cls, v):
        if v is True:
            raise ValueError("Cuenta huérfana: No existe en el Core Bancario.")
        return v

    # 2. Regla: CLABE de 18 dígitos
    @field_validator('clabe')
    @classmethod
    def validar_clabe(cls, v):
        if v is not None:
            if len(v) != 18 or not v.isdigit():
                raise ValueError("CLABE inválida: Debe contener exactamente 18 dígitos numéricos.")
        return v

    # 3. Regla: Montos reales
    @field_validator('monto_mxn')
    @classmethod
    def validar_monto(cls, v):
        if v <= 0:
            raise ValueError("Monto inválido: La transacción es menor o igual a cero.")
        return v

    # 4. Regla: Comisiones válidas
    @field_validator('comision_mxn')
    @classmethod
    def validar_comision(cls, v):
        if pd.isna(v) or v < 0:
            raise ValueError("Comisión inválida: Es nula o negativa.")
        return v

def separar_registros_validos_y_cuarentena(df_unificado: pd.DataFrame) -> tuple:
    """
    Toma la tabla unificada, evalúa fila por fila con Pydantic y separa 
    los datos limpios de los corruptos sin detener el programa (no crash).
    """
    registros_limpios = []
    registros_cuarentena = []

    # 1. Convertimos la tabla de pandas en una lista de diccionarios (fila por fila)
    datos_crudos = df_unificado.to_dict(orient="records")

    for fila in datos_crudos:
        try:
            # 2. El Cadenero (Pydantic) revisa la fila
            transaccion_validada = TransaccionBancaria(**fila)
            
            # Si nadie gritó error, la fila es VIP. La pasamos a la lista limpia.
            registros_limpios.append(transaccion_validada.model_dump())
            
        except ValidationError as e:
            # 3. ¡Alerta! Pydantic detectó una anomalía. 
            # Leemos exactamente por qué falló (el motivo).
            errores = e.errors()
            motivo = " | ".join([err["msg"] for err in errores])
            
            # Le pegamos una etiqueta a la fila corrupta explicando el error
            fila_corrupta = fila.copy()
            fila_corrupta["motivo_rechazo_cuarentena"] = motivo
            
            # La mandamos al contenedor de cuarentena
            registros_cuarentena.append(fila_corrupta)

    print(f"  [VALIDACIÓN] Registros VIP (Limpios): {len(registros_limpios)}")
    print(f"  [VALIDACIÓN] Registros rechazados (Cuarentena): {len(registros_cuarentena)}")

    return registros_limpios, registros_cuarentena

# ==============================================================================
# FASE 7: CARGA TRANSACCIONAL A BASE DE DATOS POSTGRESQL (ACID)
# ==============================================================================

def guardar_en_base_de_datos(registros_limpios: list, registros_cuarentena: list):
    """
    Persistencia en PostgreSQL vía Docker.
    Manejo de transacción explícita (commit/rollback) requerido por rúbrica.
    """
    if not registros_limpios and not registros_cuarentena:
        print("  [BD] No hay registros para procesar.")
        return

    df_limpios = pd.DataFrame(registros_limpios)
    df_cuarentena = pd.DataFrame(registros_cuarentena)

    # 1. Cadena de conexión (usuario:contraseña@servidor:puerto/base_de_datos)
    # Usamos pg8000 en lugar de psycopg2 para evitar errores de codificación en Windows
    db_url = "postgresql+pg8000://admin_etl:password_seguro@localhost:5433/banco_etl"
    engine = create_engine(db_url)
    
    # 2. Conexión explícita para manejar la transacción manualmente
    with engine.connect() as conn:
        trans = conn.begin() # Iniciamos el bloque transaccional ACID
        
        try:
            # 3. Inserción de lotes
            if not df_limpios.empty:
                df_limpios.to_sql("transacciones_limpias", conn, if_exists="append", index=False)
            
            if not df_cuarentena.empty:
                df_cuarentena.to_sql("cuarentena_errores", conn, if_exists="append", index=False)
            
            # 4. Confirmación segura
            trans.commit()
            print("  [EXITO] Fase 7 completada. Datos guardados en PostgreSQL (commit ejecutado).")
            
        except Exception as e:
            # 5. Reversión de emergencia ante cualquier fallo
            trans.rollback()
            print(f"  [ERROR CRÍTICO] Fallo de persistencia. Cambios revertidos (rollback ejecutado). Detalle: {e}")

# ==============================================================================
# ORQUESTADOR DEL MÓDULO
# ==============================================================================
def iniciar_validacion_y_carga(df_unificado: pd.DataFrame):
    print("\n" + "=" * 60)
    print("FASE 6: VALIDACIÓN ESTRICTA PYDANTIC Y CUARENTENA")
    print("=" * 60)
    limpios, cuarentena = separar_registros_validos_y_cuarentena(df_unificado)
    
    print("\n" + "=" * 60)
    print("FASE 7: CARGA TRANSACCIONAL A POSTGRESQL")
    print("=" * 60)
    guardar_en_base_de_datos(limpios, cuarentena)
    
    return True