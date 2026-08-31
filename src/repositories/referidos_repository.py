"""Repositorio de Referidos — abstrae el acceso al dato maestro referidos.parquet."""

from __future__ import annotations

from src.core.models import Referido
from src.data.data_manager import DataManager, get_data_manager
from src.repositories.base import ReadOnlyRepository


class ReferidosRepository(ReadOnlyRepository[Referido]):
    def __init__(self, data_manager: DataManager | None = None):
        self._data = data_manager or get_data_manager()

    def obtener_por_id(self, id_: str) -> Referido | None:
        # No hay índice primario propio; se filtra por plano y se toma el primero.
        coincidencias = self.filtrar_por_plano(id_)
        return coincidencias[0] if coincidencias else None

    def listar_todos(self) -> list[Referido]:
        return list(self._data.referidos)

    def filtrar_por_plano(self, plano_id: str) -> list[Referido]:
        return self._data.referidos_de_plano(plano_id)
