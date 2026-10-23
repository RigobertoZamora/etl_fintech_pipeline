# Guía de Desarrollo: Pipeline ETL Fintech (Grupo 2)

Para evitar conflictos en Git y mantener el código ordenado, cada ingeniero trabajará exclusivamente en el archivo `.py` que le corresponde dentro de la carpeta `etl/`. Nuestro dominio de datos es Fintech, por lo que procesaremos transacciones de cajeros, transferencias digitales y un catálogo de cuentas[cite: 2].

## Flujo de Trabajo y Archivos Asignados

### Ingeniero 1: Calidad de Datos
**Archivo de trabajo:** `etl/1_calidad.py`
**Tus responsabilidades:**
* Desarrollar funciones que lean los archivos de la carpeta `datasets/`[cite: 1].
* Realizar el perfilado inicial antes de cualquier cambio: medir el porcentaje de valores nulos por columna, contar los duplicados exactos y detectar los tipos de datos[cite: 2].
* Tus funciones deben retornar un reporte o un DataFrame con el diagnóstico crudo para el Ingeniero 2.

### Ingeniero 2: Transformación e Integración
**Archivo de trabajo:** `etl/2_transformacion.py`
**Tus responsabilidades:**
* Recibir los datos crudos e imputar los valores faltantes clasificándolos como MCAR o MAR, utilizando la mediana para numéricos y etiquetas controladas para categóricos[cite: 2].
* Tratar los valores atípicos (outliers), como los montos negativos absurdos, utilizando el Rango Intercuartílico (IQR) con un factor de 1.5 y aplicando Capping/Winsorizing sin eliminar filas a menos que las cantidades sean imposibles[cite: 2].
* Homologar las fechas a formato ISO (YYYY-MM-DD) y convertir las divisas a MXN con paridad de $19.50[cite: 2].
* Escalar la variable numérica en un rango de 0 a 1 (Min-Max) y discretizar el importe en tres segmentos (Bajo, Medio, Alto)[cite: 2].
* Integrar las tres fuentes y marcar las llaves huérfanas que no existan en el Core Bancario[cite: 2].

### Ingeniero 3: Validación y Resiliencia
**Archivo de trabajo:** `etl/3_validacion_bd.py`
**Mis responsabilidades:**
* Recibir el DataFrame transformado del Ingeniero 2.
* Modelar clases con Pydantic para validar estrictamente reglas de negocio (ej. validar que las CLABEs no tengan menos de 18 dígitos y rechazar comisiones nulas)[cite: 2].
* Capturar los registros inválidos mediante `try...except` y enviarlos a la tabla de cuarentena con su motivo de rechazo[cite: 2].
* Gestionar las transacciones seguras (`commit`/`rollback`) para persistir la información en la base de datos[cite: 2].

## Reglas del Repositorio
1. Ningún ingeniero debe modificar el archivo `main.py`, este solo servirá para orquestar la ejecución secuencial de nuestros tres módulos.
2. Todo avance técnico y justificación estadística debe documentarse en `REGLAS_DE_NEGOCIO.md`, ya que es el entregable obligatorio del Día 1[cite: 3].