"""Repositorio de Personal — config editable, vive en Sheets:PERSONAL."""

from __future__ import annotations

from src.config.settings import CACHE, SHEETS
from src.core.models import EstadoPersonal, Personal
from src.data.sheets_client import SheetsClient
from src.repositories.base import SheetsRepositoryBase, WritableRepository


class PersonalRepository(WritableRepository[Personal]):
    def __init__(self, client: SheetsClient):
        self._base = SheetsRepositoryBase[Personal](
            client=client,
            sheet_name=SHEETS.sheet_personal,
            columna_id="ID",
            from_dict=Personal.from_dict,
            to_dict=Personal.to_dict,
            ttl_seconds=CACHE.config_ttl_seconds,
            id_getter=lambda p: p.id,
        )

    def obtener_por_id(self, id_: str) -> Personal | None:
        return self._base.obtener_por_id(id_)

    def listar_todos(self) -> list[Personal]:
        return self._base.listar_todos()

    def guardar(self, entidad: Personal) -> None:
        self._base.guardar(entidad)

    def listar_activos(self) -> list[Personal]:
        return [p for p in self.listar_todos() if p.estado == EstadoPersonal.ACTIVO]

    def invalidar_cache(self) -> None:
        """Llamado por configuracion_service tras guardar cambios desde la UI."""
        self._base.invalidar_cache()
