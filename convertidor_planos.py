"""Script para convertir BD_planos.xlsx en los archivos Parquet requeridos."""

import os
import pandas as pd
from pathlib import Path
from src.config.settings import PLANOS_PARQUET, REFERIDOS_PARQUET

def main():
    excel_path = Path("BD_planos.xlsx")
    if not excel_path.exists():
        print(f"Error: No se encontró el archivo '{excel_path}' en el directorio principal.")
        return

    print("Cargando BD_planos.xlsx...")

    # 1. Procesar planos-suministros-direcciones
    try:
        df_planos = pd.read_excel(excel_path, sheet_name="PLANOS-SUMINISTROS-DIRECCIONES")
        print(f"Hoja 'PLANOS-SUMINISTROS-DIRECCIONES' cargada con {len(df_planos)} registros.")
        
        # Mapear columnas según los requisitos del modelo (manejando las erratas del excel)
        mapeo_planos = {
            "PLANO": "PLANO",
            "TECNOLOGIA": "TECNOLOGIA",
            "CLINETES": "CLIENTES",
            "CMTS/OLT": "CMTS_OLT",
            "HUB": "HUB",
            "ANILLO/TRONCAL": "ANILLO_TRONCAL",
            "REGION": "REGION",
            "SITE": "SITE",
            "CODIGO SITE": "CODIGO_SITE",
            "SUMINISTRO": "SUMINISTRO",
            "DEPARTAMENTO": "DEPARTAMENTO",
            "PRIVINCIA": "PROVINCIA",
            "DISTRITO": "DISTRITO",
            "DIRECCION": "DIRECCION",
            "MARCA": "MARCA"
        }
        df_planos = df_planos.rename(columns=mapeo_planos)
        
        # Convertir tipos explícitamente para evitar problemas de tipos mixtos en pyarrow
        string_cols = [
            "PLANO", "TECNOLOGIA", "CMTS_OLT", "HUB", "ANILLO_TRONCAL", "REGION",
            "SITE", "CODIGO_SITE", "SUMINISTRO", "DEPARTAMENTO", "PROVINCIA",
            "DISTRITO", "DIRECCION", "MARCA"
        ]
        for col in string_cols:
            if col in df_planos.columns:
                df_planos[col] = df_planos[col].astype(str).str.strip()
                
        if "CLIENTES" in df_planos.columns:
            df_planos["CLIENTES"] = pd.to_numeric(df_planos["CLIENTES"], errors="coerce").fillna(0).astype(int)

        # Guardar planos
        PLANOS_PARQUET.parent.mkdir(parents=True, exist_ok=True)
        df_planos.to_parquet(PLANOS_PARQUET, index=False)
        print(f"Guardado exitosamente: {PLANOS_PARQUET}")
    except Exception as e:
        print(f"Error procesando la hoja de planos: {e}")

    # 2. Procesar referidos
    try:
        df_referidos = pd.read_excel(excel_path, sheet_name="Referidos")
        print(f"Hoja 'Referidos' cargada con {len(df_referidos)} registros.")
        
        # Mapear columnas a mayúsculas estándar
        mapeo_referidos = {
            "Plano": "PLANO",
            "Cargo": "CARGO",
            "Nombre": "NOMBRE",
            "HUB": "HUB",
            "CMTS": "CMTS",
            "Cod Cliente": "COD_CLIENTE",
            "CM": "CM",
            "MTA": "MTA",
            "Modelo": "MODELO",
            "Teléfono": "TELEFONO"
        }
        df_referidos = df_referidos.rename(columns=mapeo_referidos)
        
        # Convertir tipos explícitamente para evitar problemas de tipos mixtos
        for col in df_referidos.columns:
            df_referidos[col] = df_referidos[col].astype(str).str.strip()

        # Guardar referidos
        df_referidos.to_parquet(REFERIDOS_PARQUET, index=False)
        print(f"Guardado exitosamente: {REFERIDOS_PARQUET}")
    except Exception as e:
        print(f"Error procesando la hoja de referidos: {e}")

    print("Conversión terminada.")

if __name__ == "__main__":
    main()
