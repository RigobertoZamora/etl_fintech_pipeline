import importlib

calidad = importlib.import_module("etl.1_calidad")
transformacion = importlib.import_module("etl.2_transformacion")

def main():
    print("=" * 60)
    print("FASE 1: DIAGNÓSTICO DE CALIDAD")
    print("=" * 60)
    datasets_crudos = calidad.cargar_datasets()
    reportes = calidad.generar_reporte_calidad(datasets_crudos)

    for nombre, reporte in reportes.items():
        print(f"\nDATASET: {nombre}")
        print("Resumen general:")
        for metrica, valor in reporte["resumen"].items():
            print(f"  {metrica}: {valor}")

    print("\n" + "=" * 60)
    print("FASE 2: TRANSFORMACIÓN E IMPUTACIÓN")
    print("=" * 60)
    datasets_transformados = transformacion.iniciar_transformacion(datasets_crudos)

    print("\n[OK] Fase 2 completada exitosamente.")

if __name__ == "__main__":
    main()