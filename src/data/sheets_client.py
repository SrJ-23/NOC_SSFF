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


try:
    import psycopg2
    from psycopg2 import pool
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


class PostgresSheetsClient:
    """
    Cliente PostgreSQL que implementa SheetsClient usando un pool de conexiones (ThreadedConnectionPool).
    Compatible con cadenas de conexión DATABASE_URL estándar de PostgreSQL.
    """
    def __init__(self, dsn: str):
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError(
                "La librería 'psycopg2' no está instalada. Ejecute: pip install psycopg2-binary"
            )
        self.dsn = dsn
        # Pool de conexiones: mínimo 1 conexión, máximo 20 concurrentes
        self.pool = pool.ThreadedConnectionPool(minconn=1, maxconn=20, dsn=self.dsn)
        self._crear_tablas_si_no_existen()

    def _get_connection(self):
        conn = self.pool.getconn()
        conn.autocommit = False
        return conn

    def _release_connection(self, conn):
        self.pool.putconn(conn)

    def _crear_tablas_si_no_existen(self):
        tables = {
            "personal": [
                "id TEXT PRIMARY KEY", "nombre TEXT", "cargo TEXT", "telefono TEXT", "estado TEXT"
            ],
            "incidencias": [
                "id TEXT PRIMARY KEY", "inc TEXT", "tipo TEXT", "estado TEXT", "tipo_falla TEXT",
                "departamento TEXT", "provincia TEXT", "distrito TEXT", "hora_inicio TEXT",
                "ultima_actualizacion TEXT", "bosf TEXT", "pext TEXT", "servicios TEXT", "observaciones TEXT"
            ],
            "historial": [
                "inc TEXT", "fecha TEXT", "hora TEXT", "tipo_evento TEXT", "template_version_id TEXT",
                "clientes_hfc INTEGER", "clientes_ftth INTEGER", "mbts INTEGER", "corporativos INTEGER"
            ],
            "borradores": [
                "id TEXT PRIMARY KEY", "inc TEXT", "tipo_mensaje TEXT", "texto_generado TEXT",
                "texto_editado TEXT", "template_version_id TEXT", "creado_en TEXT", "confirmado TEXT"
            ],
            "eventos": [
                "id TEXT PRIMARY KEY", "tipo TEXT", "descripcion TEXT", "parametros TEXT", "plantilla TEXT"
            ],
            "plantillas": [
                "version_id TEXT PRIMARY KEY", "tipo_mensaje TEXT", "cuerpo TEXT", "activa TEXT"
            ]
        }
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                for table, cols in tables.items():
                    cursor.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(cols)});")

                cursor.execute("SELECT COUNT(*) FROM personal;")
                count = cursor.fetchone()[0]
                if count == 0:
                    personal_seed = [
                        ("1", "Cristhian Torres", "BOSF", "979785496", "ACTIVO"),
                        ("2", "Lila Trujillo", "BOSF", "979785496", "ACTIVO"),
                        ("3", "Miguel Barja", "BOSF", "979785496", "ACTIVO"),
                        ("4", "Jesús Carrasco", "BOSF", "979785496", "ACTIVO"),
                    ]
                    cursor.executemany(
                        "INSERT INTO personal (id, nombre, cargo, telefono, estado) VALUES (%s, %s, %s, %s, %s);",
                        personal_seed
                    )
            conn.commit()
            logger.info("Base de datos PostgreSQL inicializada correctamente con esquema NOC.")
        except Exception:
            conn.rollback()
            raise
        finally:
            self._release_connection(conn)

    def leer_todos(self, hoja: str) -> list[dict]:
        table = hoja.lower()
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(f"SELECT * FROM {table};")
                rows = cursor.fetchall()
                # Retornar con claves en mayúsculas para total compatibilidad con los modelos existentes
                return [{k.upper(): v for k, v in dict(r).items()} for r in rows]
        finally:
            self._release_connection(conn)

    def agregar_fila(self, hoja: str, fila: dict) -> None:
        table = hoja.lower()
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cols = [f'"{k.lower()}"' for k in fila.keys()]
                placeholders = ", ".join(["%s"] * len(cols))
                sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders});"
                cursor.execute(sql, list(fila.values()))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._release_connection(conn)

    def actualizar_fila(self, hoja: str, columna_id: str, valor_id: str, fila: dict) -> bool:
        table = hoja.lower()
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                set_clauses = [f'"{k.lower()}" = %s' for k in fila.keys()]
                sql = f'UPDATE {table} SET {", ".join(set_clauses)} WHERE "{columna_id.lower()}" = %s;'
                params = list(fila.values()) + [valor_id]
                cursor.execute(sql, params)
                rowcount = cursor.rowcount
            conn.commit()
            return rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            self._release_connection(conn)

    def eliminar_fila(self, hoja: str, columna_id: str, valor_id: str) -> bool:
        table = hoja.lower()
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = f'DELETE FROM {table} WHERE "{columna_id.lower()}" = %s;'
                cursor.execute(sql, (valor_id,))
                rowcount = cursor.rowcount
            conn.commit()
            return rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            self._release_connection(conn)

    def sobrescribir_hoja(self, hoja: str, filas: list[dict]) -> None:
        table = hoja.lower()
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"DELETE FROM {table};")
                if filas:
                    cols = [f'"{k.lower()}"' for k in filas[0].keys()]
                    placeholders = ", ".join(["%s"] * len(cols))
                    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders});"
                    params = [list(f.values()) for f in filas]
                    cursor.executemany(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._release_connection(conn)
