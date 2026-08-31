# src/data/sheets_client.py
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from src.utils.logging_utils import get_logger

import os

logger = get_logger(__name__)

if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    DB_PATH = Path("/tmp/noc_monitoreo.db")
else:
    DB_PATH = Path("noc_monitoreo.db")


class SheetsClient(Protocol):
    def leer_todos(self, hoja: str) -> list[dict]: ...
    def agregar_fila(self, hoja: str, fila: dict) -> None: ...
    def actualizar_fila(self, hoja: str, columna_id: str, valor_id: str, fila: dict) -> bool: ...
    def eliminar_fila(self, hoja: str, columna_id: str, valor_id: str) -> bool: ...
    def sobrescribir_hoja(self, hoja: str, filas: list[dict]) -> None: ...


class SQLiteSheetsClient:
    """
    Cliente SQLite que simula la interfaz de SheetsClient para no alterar
    los repositorios existentes en el proyecto.
    """
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._crear_tablas_si_no_existen()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Retorna registros como diccionarios
        return conn

    def _crear_tablas_si_no_existen(self):
        # Mapeo de hojas de Google Sheets a tablas SQLite locales con columnas de texto
        tables = {
            "personal": [
                "ID TEXT PRIMARY KEY", "NOMBRE TEXT", "CARGO TEXT", "TELEFONO TEXT", "ESTADO TEXT"
            ],
            "incidencias": [
                "ID TEXT PRIMARY KEY", "INC TEXT", "TIPO TEXT", "ESTADO TEXT", "TIPO_FALLA TEXT",
                "DEPARTAMENTO TEXT", "PROVINCIA TEXT", "DISTRITO TEXT", "HORA_INICIO TEXT",
                "ULTIMA_ACTUALIZACION TEXT", "BOSF TEXT", "PEXT TEXT", "SERVICIOS TEXT", "OBSERVACIONES TEXT"
            ],
            "historial": [
                "INC TEXT", "FECHA TEXT", "HORA TEXT", "TIPO_EVENTO TEXT", "TEMPLATE_VERSION_ID TEXT",
                "CLIENTES_HFC INTEGER", "CLIENTES_FTTH INTEGER", "MBTS INTEGER", "CORPORATIVOS INTEGER"
            ],
            "borradores": [
                "ID TEXT PRIMARY KEY", "INC TEXT", "TIPO_MENSAJE TEXT", "TEXTO_GENERADO TEXT",
                "TEXTO_EDITADO TEXT", "TEMPLATE_VERSION_ID TEXT", "CREADO_EN TEXT", "CONFIRMADO TEXT"
            ],
            "eventos": [
                "ID TEXT PRIMARY KEY", "TIPO TEXT", "DESCRIPCION TEXT", "PARAMETROS TEXT", "PLANTILLA TEXT"
            ],
            "plantillas": [
                "VERSION_ID TEXT PRIMARY KEY", "TIPO_MENSAJE TEXT", "CUERPO TEXT", "ACTIVA TEXT"
            ]
        }
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for table, cols in tables.items():
                cursor.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(cols)})")
            
            # Datos iniciales para pruebas en NOC
            # Actualizar o inicializar datos de personal oficial del NOC
            personal_seed = [
                ("1", "Cristhian Torres", "BOSF", "979785496", "ACTIVO"),
                ("2", "Lila Trujillo", "BOSF", "979785496", "ACTIVO"),
                ("3", "Miguel Barja", "BOSF", "979785496", "ACTIVO"),
                ("4", "Jesús Carrasco", "BOSF", "979785496", "ACTIVO"),
            ]
            cursor.execute("DELETE FROM personal")
            cursor.executemany(
                "INSERT INTO personal (ID, NOMBRE, CARGO, TELEFONO, ESTADO) VALUES (?, ?, ?, ?, ?)",
                personal_seed
            )
            conn.commit()
            logger.info("Base de datos SQLite local inicializada con personal BOSF oficial.")

    def leer_todos(self, hoja: str) -> list[dict]:
        table = hoja.lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def agregar_fila(self, hoja: str, fila: dict) -> None:
        table = hoja.lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            columns = fila.keys()
            placeholders = ", ".join(["?"] * len(columns))
            sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
            cursor.execute(sql, list(fila.values()))
            conn.commit()

    def actualizar_fila(self, hoja: str, columna_id: str, valor_id: str, fila: dict) -> bool:
        table = hoja.lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            set_clause = ", ".join([f"{k} = ?" for k in fila.keys()])
            sql = f"UPDATE {table} SET {set_clause} WHERE {columna_id} = ?"
            params = list(fila.values()) + [valor_id]
            cursor.execute(sql, params)
            conn.commit()
            return cursor.rowcount > 0

    def eliminar_fila(self, hoja: str, columna_id: str, valor_id: str) -> bool:
        table = hoja.lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            sql = f"DELETE FROM {table} WHERE {columna_id} = ?"
            cursor.execute(sql, (valor_id,))
            conn.commit()
            return cursor.rowcount > 0

    def sobrescribir_hoja(self, hoja: str, filas: list[dict]) -> None:
        table = hoja.lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM {table}")
            if filas:
                columns = filas[0].keys()
                placeholders = ", ".join(["?"] * len(columns))
                sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
                params = [list(f.values()) for f in filas]
                cursor.executemany(sql, params)
            conn.commit()
