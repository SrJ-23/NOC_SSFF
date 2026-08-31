"""
Carga cruda de archivos Parquet.

Este módulo NO debe ser importado directamente por repositories, services
o pages. El único consumidor autorizado es DataManager. Esto mantiene
un único punto de entrada para los datos maestros, tal como exige la
arquitectura (nunca leer Parquet repetidamente ni desde múltiples lugares).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


class ParquetLoadError(RuntimeError):
    """Error al cargar un archivo Parquet maestro."""


def cargar_parquet(ruta: Path) -> pd.DataFrame:
    """
    Carga un archivo Parquet a DataFrame.

    Lanza ParquetLoadError con contexto claro si el archivo no existe
    o está corrupto — mejor eso que un traceback crudo de pyarrow en
    medio de un turno del NOC.
    """
    if not ruta.exists():
        msg = f"Archivo maestro no encontrado: {ruta}"
        logger.error(msg)
        raise ParquetLoadError(msg)

    try:
        df = pd.read_parquet(ruta)
    except Exception as exc:  # noqa: BLE001 - se re-lanza con contexto
        msg = f"Error leyendo Parquet '{ruta.name}': {exc}"
        logger.error(msg)
        raise ParquetLoadError(msg) from exc

    logger.info("Parquet cargado: %s (%d filas)", ruta.name, len(df))
    return df


def guardar_parquet(df: pd.DataFrame, ruta: Path) -> None:
    """
    Escribe un DataFrame a Parquet.

    Reservado para uso administrativo/scripts de carga inicial de la
    base maestra — NO se usa en el flujo normal de la app, ya que los
    maestros son de solo lectura durante la operación.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(ruta, index=False)
    logger.info("Parquet escrito: %s (%d filas)", ruta.name, len(df))
