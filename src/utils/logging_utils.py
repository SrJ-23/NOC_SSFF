"""
Logging centralizado.

Cada acción importante (creación de incidencia, carga, comparación,
mensaje generado, cierre, errores) debe pasar por aquí. No es visible
para el analista, pero es esencial para depuración en producción.
"""

from __future__ import annotations

import logging
import sys
from functools import lru_cache

from src.config.settings import LOGGING


@lru_cache(maxsize=1)
def get_logger(name: str = "noc_app") -> logging.Logger:
    """
    Logger singleton (cacheado por nombre gracias a lru_cache).
    Escribe a stdout siempre, y a archivo si el directorio de logs
    existe o puede crearse.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # ya configurado, evita handlers duplicados

    logger.setLevel(LOGGING.level)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    try:
        LOGGING.log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(LOGGING.log_dir / LOGGING.log_filename)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # En entornos read-only (ej. algunos deploys) el file handler puede
        # fallar; no debe tumbar la app por esto.
        logger.warning("No se pudo crear el archivo de log; se continúa solo con stdout.")

    return logger
