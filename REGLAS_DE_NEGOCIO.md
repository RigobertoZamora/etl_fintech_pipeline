# REGLAS DE NEGOCIO Y ESPECIFICACIÓN TÉCNICA DEL PIPELINE ETL

**Institución:** Tecnológico Nacional de México - Campus Colima  
**Materia:** Ingeniería de Datos (ATD-2602) | **Unidad 2:** Limpieza y Preprocesamiento de Datos  
**Grupo y Dominio:** Grupo 2 (LCNT) — Fintech & Transacciones Bancarias (Cajeros ATM + SPEI/App)  

---

## 1. Principio de Ingeniería y Arquitectura General

Este proyecto implementa un Pipeline ETL (*Extract, Transform, Load*) end-to-end bajo el **Principio de Robustez en Producción (No Crash)**. El sistema está diseñado para ingerir lotes de datos financieros crudos y altamente inconsistentes, aplicar preprocesamiento estadístico reproducible, validar reglas de negocio mediante esquemas estrictos y persistir los resultados de forma transaccional en una base de datos relacional, desviando cualquier anomalía a una **Zona de Cuarentena** auditable sin detener la ejecución del lote.

### Diagrama de Flujo End-to-End (Mockup Oficial)

~~~mermaid
flowchart TD
    subgraph FASE_0 [Ingesta de Fuentes Heterogéneas]
        A1[catalogo_cuentas.csv]
        A2[transacciones_atm.csv]
        A3[transferencias_digitales.json]
    end

    A1 & A2 & A3 --> B[FASE 1: Diagnóstico de Calidad Inicial<br/>Detección de nulos ocultos, completitud,<br/>unicidad por reintentos ATM y dtypes]

    B --> C[FASE 2: Manejo de Faltantes e Imputación<br/>Clasificación MCAR/MAR, Mediana en numéricos,<br/>Etiquetas controladas en categóricos y recálculo]

    C --> D{FASE 3: ¿Monto <= 0?<br/>Valor Imposible}
    D -- Sí: Dato Corrupto --> D1[Separar o marcar registro imposible<br/>para no sesgar cuartiles]
    D -- No: Rango Operativo --> E[FASE 3: Tratamiento de Outliers con IQR<br/>Capping / Winsorizing a límites de Tukey<br/>Q1 - 1.5*IQR y Q3 + 1.5*IQR]

    E --> F[FASE 4: Integración, Unificación y Huérfanos<br/>Mapeo de esquemas, Fechas a ISO YYYY-MM-DD,<br/>Conversión USD a MXN @ $19.50 y Merge con Catálogo]

    F --> G[FASE 5: Transformación, Escalamiento y Discretización<br/>Normalización Min-Max en rango 0 a 1<br/>y Binning en 3 segmentos: Bajo, Medio, Alto]

    G --> H{FASE 6: Validación Estricta Pydantic<br/>@field_validator + try...except}

    H -- Cumple Reglas --> I[Lista: Registros Conformes]
    H -- Viola Reglas --> J[Lista: Zona de Cuarentena<br/>+ motivo_rechazo_cuarentena]

    I & J --> K{FASE 7: Carga Transaccional SQL<br/>Bloque Atómico ACID}
    K -- Éxito en Lote --> L[conn.commit<br/>Tablas: transacciones_limpias<br/>y cuarentena_errores]
    K -- Fallo de Motor/Red --> M[conn.rollback<br/>Reversión segura sin corrupción]
~~~

---

## 2. Matriz de Responsabilidades y Contratos de Interfaz

Para garantizar modularidad e independencia en Git, cada integrante es propietario de un módulo dentro del paquete `etl/`:

| Rol | Archivo Asignado | Entrada (Input) | Salida Obligatoria (Output) | Entregable Clave |
| :--- | :--- | :--- | :--- | :--- |
| **Ingeniero/a 1:** Calidad, Nulos y Outliers | `etl/1_calidad.py` | Rutas a archivos crudos en `datasets/`. | DataFrames limpios de nulos/outliers + Diccionario/Tabla con métricas de calidad **Antes vs. Después**. | Funciones de perfilado, imputación e IQR Capping idempotentes + Reporte comparativo. |
| **Ingeniero/a 2:** Transformación e Integración | `etl/2_transformacion.py` | DataFrames preprocesados por el Ingeniero 1. | **Un único DataFrame unificado** con esquema estándar, fechas ISO, MXN, bandera de cuenta huérfana, columna Min-Max y columna discretizada. | Módulo de integración multifuente y normalización de variables. |
| **Ingeniero/a 3:** Validación, Resiliencia y BD (Rigoberto) | `etl/3_validacion_bd.py` | DataFrame unificado del Ingeniero 2. | Persistencia transaccional en PostgreSQL/SQLite (`transacciones_limpias` y `cuarentena_errores`). | Esquemas `Pydantic`, motor de cuarentena, carga SQL transaccional y pruebas de estrés. |

---

## 3. Especificación Técnica y Justificación Estadística por Fase (Las 7 Fases)

### FASE 1: Diagnóstico de Calidad Inicial (Responsable: Ingeniero 1)
Antes de modificar cualquier celda, el sistema debe ejecutar un perfilado cuantitativo sobre `catalogo_cuentas.csv`, `transacciones_atm.csv` y `transferencias_digitales.json`:

1. **Detección de Nulos Disfrazados:** Al cargar los archivos, se deben estandarizar cadenas basura (`["N/A", "null", "NULL", "-", "", "None", "desconocido"]`) como `NaN` reales mediante el parámetro `na_values`.
2. **Métrica de Completitud:** Calcular el porcentaje de valores válidos por columna mediante la fórmula:
   $$\text{Completitud (\%)} = \left(1 - \frac{\text{Total de Nulos en Columna}}{\text{Total de Filas}}\right) \times 100$$
3. **Métrica de Unicidad (Reintentos de Cajero ATM):** Contar y eliminar duplicados exactos (`df.drop_duplicates()`) generados por reintentos de red en cajeros ATM, documentando cuántas filas repetidas se descartaron.
4. **Inferencia de Tipos (`dtypes`):** Auditar qué columnas numéricas o temporales fueron leídas erróneamente como texto (`object`) debido a caracteres corruptos.

---

### FASE 2: Manejo de Faltantes e Imputación (Responsable: Ingeniero 1)
1. **Clasificación del Mecanismo de Pérdida:**
   * **MCAR (*Missing Completely At Random*):** Fallos esporádicos de transmisión en cajeros donde la ausencia del dato es independiente de cualquier variable observada o no observada.
   * **MAR (*Missing At Random*):** Ausencias en comisiones o metadatos que dependen de otra variable observada, como el canal de origen (ATM vs. App Digital) o el tipo de cuenta.
2. **Imputación de Variables Numéricas (Justificación de la Mediana sobre la Media):**
   * **Regla:** Los importes o valores numéricos recuperables se imputarán con la **mediana** ($\tilde{x}$) de su canal correspondiente, o mediante recálculo determinista si existen columnas componentes (por ejemplo, $\text{monto\_total} = \text{monto\_base} + \text{comision}$).
   * **Justificación Estadística:** En datos bancarios y transaccionales, la distribución de los importes presenta un fuerte sesgo positivo (asimetría hacia la derecha) y presencia de valores extremos. La media aritmética ($\mu = \frac{1}{n}\sum_{i=1}^{n} x_i$) no es un estimador robusto porque un solo retiro o transferencia gigante desplaza artificialmente el centro de la distribución. La mediana (percentil 50) es resistente a valores extremos y preserva la tendencia central real sin distorsionar la escala.
   * **Excepción Crítica para Auditoría y Cuarentena:** Si una transferencia carece de `comision` en un escenario donde la regla de negocio prohíbe comisiones nulas, o si el campo faltante es un identificador crítico (`id_cuenta` o `clabe`), **no se inventará el dato**; se conservará el marcador nulo para que el Ingeniero 3 lo intercepte con `Pydantic` y lo envíe a `cuarentena_errores` con trazabilidad completa.
3. **Imputación de Variables Categóricas:** Los campos de texto descriptivos vacíos (concepto, sucursal o ubicación) se imputarán con la etiqueta controlada `'ANONIMO'` o `'SIN_DESCRIPCION'`.

---

### FASE 3: Tratamiento de Outliers con IQR y Valores Imposibles (Responsable: Ingeniero 1)
1. **Regla para Valores Financieramente Imposibles ($\text{monto} \le 0$):**
   * Los montos negativos absurdos o en cero representan errores críticos de captura o corrupción de origen. Conforme a los lineamientos de la Fase 3, las filas con cantidades o montos $\le 0$ no deben contaminar el cálculo estadístico de los cuartiles. Se documentará su conteo y se aislarán para eliminación o desvío directo a cuarentena.
2. **Detección Robusta mediante Rango Intercuartílico ($IQR$ de Tukey):**
   * **¿Por qué $IQR$ y no Z-Score?** El método Z-Score ($z = \frac{x - \mu}{\sigma}$) asume normalidad y utiliza la media ($\mu$) y la desviación estándar ($\sigma$), las cuales ya están contaminadas por los propios outliers (efecto de enmascaramiento). El método de Tukey se basa en los cuartiles $Q_1$ (percentil 25) y $Q_3$ (percentil 75), que son inmunes a las colas extremas:
     $$IQR = Q_3 - Q_1$$
     $$\text{Límite Inferior } (L_{\text{inf}}) = Q_1 - 1.5 \times IQR$$
     $$\text{Límite Superior } (L_{\text{sup}}) = Q_3 + 1.5 \times IQR$$
3. **Aplicación de Winsorizing / Capping (Sin pérdida destructiva de datos):**
   * **Prohibido eliminar filas por tener montos altos:** En banca, una transacción muy alta puede ser una operación legítima de tesorería. En lugar de borrar el registro, se aplicará *Capping* (`df['monto'].clip(lower=limite_inf, upper=limite_sup)`) para acotar los valores extremos a los umbrales de Tukey.
4. **Requisito de Idempotencia:** La función de limpieza debe ser idempotente, devolviendo un DataFrame nuevo (`.copy()`) y garantizando que aplicarla una o múltiples veces sobre su propia salida produzca exactamente el mismo resultado:
   $$f(f(X)) = f(X)$$

---

### FASE 4: Integración, Unificación y Detección de Huérfanos (Responsable: Ingeniero 2)
1. **Mapeo de Esquemas (*Schema Mapping*):**
   * Unificar los nombres dispares de columnas entre `transacciones_atm.csv` (canal físico) y `transferencias_digitales.json` (canal SPEI/App) mediante diccionarios explícitos de renombrado hacia un esquema canónico común:
     * `id_transaccion` (`str`)
     * `id_cuenta` (`str`)
     * `clabe` (`str`)
     * `fecha_operacion` (`str` en formato ISO)
     * `canal` (`str`: `'ATM'` o `'DIGITAL'`)
     * `monto_mxn` (`float`)
     * `comision_mxn` (`float`)
2. **Homologación Temporal:** Convertir todas las fechas mixtas (`DD/MM/YYYY`, timestamps o texto ISO) al estándar estricto **`YYYY-MM-DD`**.
3. **Homologación Monetaria:** Cualquier transacción cuya divisa de origen sea `USD` se convertirá a `MXN` aplicando la paridad oficial fija de **$\$19.50\text{ MXN}$ por $\text{USD}$**:
   $$\text{Monto}_{\text{MXN}} = \text{Monto}_{\text{USD}} \times 19.50$$
4. **Cruce con Catálogo Maestro y Detección de Cuentas Huérfanos:**
   * Realizar un cruce izquierdo (`pd.merge(..., on='id_cuenta', how='left', indicator=True)`) contra `catalogo_cuentas.csv` (Core Bancario).
   * **Regla Crítica:** **NO eliminar** los registros donde `_merge == 'left_only'`. Crear una columna booleana `es_cuenta_huerfana = (df['_merge'] == 'left_only')` para que el módulo del Ingeniero 3 detecte la anomalía y la desvíe a la tabla `cuarentena_errores` con su causa exacta.

---

### FASE 5: Transformación, Escalamiento y Discretización (Responsable: Ingeniero 2)
1. **Escalamiento Min-Max:**
   * Normalizar la columna `monto_mxn` al rango acotado $[0, 1]$ en una nueva columna llamada `monto_escalado`:
     $$x' = \frac{x - x_{\min}}{x_{\max} - x_{\min}}$$
   * **Orden de ejecución obligatorio:** Dado que el escalamiento Min-Max es altamente sensible a valores extremos, **siempre** se ejecuta en la Fase 5, *después* de haber aplicado el Capping con $IQR$ en la Fase 3.
2. **Discretización (*Binning*):**
   * Crear la columna categórica ordinal `segmento_monto` dividiendo el importe en **3 segmentos (`'Bajo'`, `'Medio'`, `'Alto'`)** mediante cuantiles (`pd.qcut`) o reglas de negocio justificadas (`pd.cut`), facilitando el análisis agregado por nivel de transacción.

---

### FASE 6: Validación con Pydantic y Zona de Cuarentena (Responsable: Ingeniero 3)
Cada fila del DataFrame integrado pasará por el esquema `TransaccionBancaria(BaseModel)` de `Pydantic` con validadores personalizados (`@field_validator`). Un bloque `try...except ValidationError` evaluará registro por registro sin detener el procesamiento del lote:

* **Criterios de Rechazo Directo a `cuarentena_errores`:**
  1. **Cuenta Huérfana:** `es_cuenta_huerfana == True` (la cuenta no existe en `catalogo_cuentas.csv` del Core Bancario).
  2. **CLABE Inválida:** Longitud distinta de 18 caracteres o presencia de caracteres no numéricos ($\text{len}(\text{clabe}) \neq 18$).
  3. **Comisión Nula o Inválida:** `comision_mxn` es nula (`NaN`/`None`) o menor a cero ($\text{comision\_mxn} < 0$).
  4. **Monto Inválido:** `monto_mxn <= 0` o nulo.
  5. **Fecha Malformada:** Fecha que no cumpla con el patrón ISO `YYYY-MM-DD`.
* Todo registro rechazado conservará su payload original junto con la columna `motivo_rechazo_cuarentena` detallando exactamente qué regla de validación violó.

---

### FASE 7: Carga Transaccional a Base de Datos Relacional (Responsable: Ingeniero 3)
La persistencia se realizará en **PostgreSQL / SQLite** bajo control estricto de transacciones ACID:
* Se poblarán dos tablas obligatorias: `transacciones_limpias` (registros validados por Pydantic) y `cuarentena_errores` (registros rechazados con su motivo y marca temporal de auditoría).
* La inserción de cada lote se ejecutará dentro de un bloque transaccional seguro: si ocurre cualquier excepción de infraestructura o violación de integridad a nivel motor, se invocará `conn.rollback()` para revertir la operación completa y evitar estados parcialmente corruptos; solo tras verificar la inserción íntegra del lote se ejecutará `conn.commit()`.

---

## 4. Firmas de Conformidad Técnica (Entregable Día 1)

| Rol en el Proyecto | Nombre del Integrante | Usuario Git | Fecha de Aprobación |
| :--- | :--- | :--- | :--- |
| **Ingeniero/a 1** (Calidad, Nulos y Outliers) | **Erick Moisés Urbina** | `@sonrisa-fan` | 
| **Ingeniero/a 2** (Transformación e Integración) | **Luis Fernando Machuca** | `@LuisFerMCDev` | 
| **Ingeniero/a 3** (Validación, Resiliencia y BD) | **Bruno Rigoberto Zamora** | `@RigobertoZamora` | 