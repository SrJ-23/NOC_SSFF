# src/config/settings.py
from pathlib import Path
import logging

BASE_DIR = Path(__file__).resolve().parent.parent
PLANOS_PARQUET = BASE_DIR / "data" / "planos.parquet"
REFERIDOS_PARQUET = BASE_DIR / "data" / "referidos.parquet"

class SheetsConfig:
    sheet_personal = "personal"
    sheet_incidencias = "incidencias"
    sheet_borradores = "borradores"
    sheet_eventos = "eventos"
    sheet_plantillas = "plantillas"
    sheet_historial = "historial"

SHEETS = SheetsConfig()

class CacheConfig:
    operational_ttl_seconds = 1.0  # low TTL for fast local updates
    config_ttl_seconds = 5.0

CACHE = CacheConfig()

class LoggingConfig:
    level = logging.INFO
    log_dir = Path("logs")
    log_filename = "app.log"

LOGGING = LoggingConfig()

class SemaforoConfig:
    def __init__(self, amarillo_max_minutos: float = 60.0):
        self.amarillo_max_minutos = amarillo_max_minutos

SEMAFORO_DEFAULT = SemaforoConfig(amarillo_max_minutos=60.0)
