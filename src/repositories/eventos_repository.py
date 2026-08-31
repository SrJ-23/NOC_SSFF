"""Repositorio de Eventos — catálogo editable, vive en Sheets:EVENTOS."""

from __future__ import annotations

from src.config.settings import CACHE, SHEETS
from src.core.models import Evento
from src.data.sheets_client import SheetsClient
from src.repositories.base import SheetsRepositoryBase, WritableRepository


class EventosRepository(WritableRepository[Evento]):
    def __init__(self, client: SheetsClient):
        self._base = SheetsRepositoryBase[Evento](
            client=client,
            sheet_name=SHEETS.sheet_eventos,
            columna_id="ID",
            from_dict=Evento.from_dict,
            to_dict=Evento.to_dict,
            ttl_seconds=CACHE.config_ttl_seconds,
            id_getter=lambda e: e.id,
        )

    def obtener_por_id(self, id_: str) -> Evento | None:
        return self._base.obtener_por_id(id_)

    def listar_todos(self) -> list[Evento]:
        return self._base.listar_todos()

    def guardar(self, entidad: Evento) -> None:
        self._base.guardar(entidad)

    def filtrar_por_tipo(self, tipo: str) -> list[Evento]:
        return [e for e in self.listar_todos() if e.tipo == tipo]

    def invalidar_cache(self) -> None:
        self._base.invalidar_cache()
