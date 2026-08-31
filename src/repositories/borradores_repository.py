"""Repositorio de Borradores — dato operativo, vive en Sheets:BORRADORES."""

from __future__ import annotations

from src.config.settings import CACHE, SHEETS
from src.core.models import Borrador
from src.data.sheets_client import SheetsClient
from src.repositories.base import SheetsRepositoryBase, WritableRepository


class BorradoresRepository(WritableRepository[Borrador]):
    def __init__(self, client: SheetsClient):
        self._base = SheetsRepositoryBase[Borrador](
            client=client,
            sheet_name=SHEETS.sheet_borradores,
            columna_id="ID",
            from_dict=Borrador.from_dict,
            to_dict=Borrador.to_dict,
            ttl_seconds=CACHE.operational_ttl_seconds,
            id_getter=lambda b: b.id,
        )

    def obtener_por_id(self, id_: str) -> Borrador | None:
        return self._base.obtener_por_id(id_)

    def listar_todos(self) -> list[Borrador]:
        return self._base.listar_todos()

    def guardar(self, entidad: Borrador) -> None:
        self._base.guardar(entidad)

    def obtener_borrador_activo(self, inc: str) -> Borrador | None:
        """El borrador no confirmado más reciente para una incidencia, si existe."""
        candidatos = [b for b in self.listar_todos() if b.inc == inc and not b.confirmado]
        return max(candidatos, key=lambda b: b.creado_en, default=None)
