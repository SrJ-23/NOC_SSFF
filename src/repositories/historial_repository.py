"""Repositorio de Historial — dato operativo, vive en Sheets:HISTORIAL.

Solo almacena eventos (nunca el mensaje completo). No usa `id` como
identificador único porque un mismo INC puede tener múltiples eventos;
por eso este repositorio no implementa `guardar()` como upsert, sino
como "append-only" — cada actualización es una fila nueva.
"""

from __future__ import annotations

from src.config.settings import CACHE, SHEETS
from src.core.models import HistorialEvento
from src.data.sheets_client import SheetsClient
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


class HistorialRepository:
    def __init__(self, client: SheetsClient):
        self._client = client
        self._sheet_name = SHEETS.sheet_historial
        self._ttl = CACHE.operational_ttl_seconds
        self._cache: list[HistorialEvento] | None = None
        self._cache_ts = 0.0

    def _listar_sin_cache(self) -> list[HistorialEvento]:
        filas = self._client.leer_todos(self._sheet_name)
        return [HistorialEvento.from_dict(f) for f in filas]

    def listar_todos(self) -> list[HistorialEvento]:
        import time

        ahora = time.monotonic()
        if self._cache is None or (ahora - self._cache_ts) > self._ttl:
            self._cache = self._listar_sin_cache()
            self._cache_ts = ahora
        return self._cache

    def listar_por_inc(self, inc: str) -> list[HistorialEvento]:
        """Retorna eventos ordenados cronológicamente ascendente (orden interno)."""
        eventos = [e for e in self.listar_todos() if e.inc == inc]
        return sorted(eventos, key=lambda e: (e.fecha, e.hora))

    def agregar_evento(self, evento: HistorialEvento) -> None:
        """
        Append-only: nunca se sobrescribe un evento histórico existente.
        """
        self._client.agregar_fila(self._sheet_name, evento.to_dict())
        self._cache = None  # invalidar
        logger.info("Evento de historial agregado para INC=%s (%s)", evento.inc, evento.tipo_evento)
