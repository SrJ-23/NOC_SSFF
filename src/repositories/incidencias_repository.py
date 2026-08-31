"""Repositorio de Incidencias — dato operativo, vive en Sheets:INCIDENCIAS."""

from __future__ import annotations

from src.config.settings import CACHE, SHEETS
from src.core.models import EstadoIncidencia, Incidencia
from src.data.sheets_client import SheetsClient
from src.repositories.base import SheetsRepositoryBase, WritableRepository


class IncidenciasRepository(WritableRepository[Incidencia]):
    def __init__(self, client: SheetsClient):
        self._base = SheetsRepositoryBase[Incidencia](
            client=client,
            sheet_name=SHEETS.sheet_incidencias,
            columna_id="ID",
            from_dict=Incidencia.from_dict,
            to_dict=Incidencia.to_dict,
            ttl_seconds=CACHE.operational_ttl_seconds,
            id_getter=lambda i: i.id,
        )

    def obtener_por_id(self, id_: str) -> Incidencia | None:
        return self._base.obtener_por_id(id_)

    def listar_todos(self) -> list[Incidencia]:
        return self._base.listar_todos()

    def guardar(self, entidad: Incidencia) -> None:
        self._base.guardar(entidad)

    def eliminar(self, id_: str) -> bool:
        return self._base.eliminar(id_)

    def listar_activas(self) -> list[Incidencia]:
        """Para la página 'Averías Pendientes': todo lo que no está CERRADA."""
        return [i for i in self.listar_todos() if i.estado != EstadoIncidencia.CERRADA]

    def listar_cerradas(self) -> list[Incidencia]:
        """Para la página 'Histórica': todo lo que está CERRADA."""
        return [i for i in self.listar_todos() if i.estado == EstadoIncidencia.CERRADA]

    def obtener_por_inc(self, inc: str) -> Incidencia | None:
        return next((i for i in self.listar_todos() if i.inc == inc), None)
