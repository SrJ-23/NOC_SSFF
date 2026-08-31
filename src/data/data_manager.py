"""
DataManager: único punto de acceso a los datos MAESTROS (Parquet).

Ningún otro módulo debe leer planos.parquet / referidos.parquet
directamente. Siempre a través de una instancia de DataManager, obtenida
vía `get_data_manager()` (singleton simple, cargado una sola vez por
proceso del servidor Flask).

Los datos OPERATIVOS (Incidencias, Historial, Borradores) y la
CONFIGURACIÓN EDITABLE (Personal, Eventos, Plantillas, Semáforo,
Tipos de falla) NO viven aquí — esos van en Google Sheets y se acceden
vía los repositorios correspondientes en src/repositories/, cada uno
con su propio TTL de caché corto (ver src/config/settings.py::CacheConfig).
"""

from __future__ import annotations

from src.config.settings import PLANOS_PARQUET, REFERIDOS_PARQUET
from src.core.models import Plano, Referido
from src.data.parquet_loader import cargar_parquet
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


class DataManager:
    """
    Mantiene los datos maestros cargados en memoria para toda la sesión
    del proceso. La carga ocurre de forma perezosa (lazy) en el primer
    acceso a cada propiedad, no en __init__, para no penalizar el
    arranque si una página no necesita cierta base.
    """

    def __init__(self) -> None:
        self._planos: dict[str, Plano] | None = None
        self._referidos: list[Referido] | None = None

    # ------------------------------------------------------------------
    # Planos
    # ------------------------------------------------------------------

    @property
    def planos(self) -> dict[str, Plano]:
        """Diccionario indexado por PLANO para lookup O(1)."""
        if self._planos is None:
            df = cargar_parquet(PLANOS_PARQUET)
            self._planos = {
                row["PLANO"]: Plano.from_dict(row)
                for row in df.to_dict(orient="records")
            }
            logger.info("DataManager: %d planos indexados en memoria", len(self._planos))
        return self._planos

    def obtener_plano(self, plano_id: str) -> Plano | None:
        if not plano_id:
            return None
        # 1. Búsqueda exacta
        direct = self.planos.get(plano_id)
        if direct:
            return direct
        # 2. Búsqueda en mayúsculas
        up_id = plano_id.strip().upper()
        for k, p in self.planos.items():
            if k.upper() == up_id:
                return p
        # 3. Búsqueda por prefijo
        for k, p in self.planos.items():
            if k.upper().startswith(up_id) or up_id.startswith(k.upper()):
                return p
        return None

    # ------------------------------------------------------------------
    # Referidos
    # ------------------------------------------------------------------

    @property
    def referidos(self) -> list[Referido]:
        if self._referidos is None:
            df = cargar_parquet(REFERIDOS_PARQUET)
            self._referidos = [Referido.from_dict(row) for row in df.to_dict(orient="records")]
            logger.info("DataManager: %d referidos cargados en memoria", len(self._referidos))
        return self._referidos

    def referidos_de_plano(self, plano_id: str) -> list[Referido]:
        return [r for r in self.referidos if r.plano == plano_id]

    # ------------------------------------------------------------------
    # Invalidación manual (uso administrativo, no en flujo normal)
    # ------------------------------------------------------------------

    def invalidar_todo(self) -> None:
        """
        Fuerza recarga en el próximo acceso. Los maestros son read-only
        durante la operación normal; esto solo se usa si se reemplaza
        el archivo Parquet físico y se necesita refrescar sin reiniciar
        el proceso completo.
        """
        self._planos = None
        self._referidos = None
        logger.info("DataManager: caché de maestros invalidada manualmente")


def _build_data_manager() -> DataManager:
    return DataManager()


_singleton: DataManager | None = None


def get_data_manager() -> DataManager:
    """
    Punto de entrada usado por el resto de la app: singleton simple en
    memoria de proceso (Flask sirve en un solo proceso/hilo de worker,
    no necesita el cache_resource de Streamlit).
    """
    global _singleton
    if _singleton is None:
        _singleton = _build_data_manager()
    return _singleton


_singleton: DataManager | None = None
