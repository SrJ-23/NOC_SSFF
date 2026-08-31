"""
Repositorio de Plantillas — config editable, vive en Sheets:PLANTILLAS.

Las plantillas son append-only por versión (ver core/models/plantilla.py):
editar desde Configuración crea una fila NUEVA con nuevo version_id y
marca la anterior como inactiva, en vez de sobrescribir. Esto sostiene
la trazabilidad de HistorialEvento.template_version_id.
"""

from __future__ import annotations

from src.config.settings import CACHE, SHEETS
from src.core.models import Plantilla, TipoMensaje
from src.data.sheets_client import SheetsClient
from src.repositories.base import SheetsRepositoryBase, WritableRepository


class PlantillasRepository(WritableRepository[Plantilla]):
    def __init__(self, client: SheetsClient):
        self._base = SheetsRepositoryBase[Plantilla](
            client=client,
            sheet_name=SHEETS.sheet_plantillas,
            columna_id="VERSION_ID",
            from_dict=Plantilla.from_dict,
            to_dict=Plantilla.to_dict,
            ttl_seconds=CACHE.config_ttl_seconds,
            id_getter=lambda p: p.version_id,
        )

    def obtener_por_id(self, id_: str) -> Plantilla | None:
        return self._base.obtener_por_id(id_)

    def listar_todos(self) -> list[Plantilla]:
        return self._base.listar_todos()

    def guardar(self, entidad: Plantilla) -> None:
        self._base.guardar(entidad)

    def obtener_activa(self, tipo_mensaje: TipoMensaje) -> Plantilla | None:
        """La plantilla vigente hoy para un tipo de mensaje dado."""
        candidatas = [
            p for p in self.listar_todos()
            if p.tipo_mensaje == tipo_mensaje and p.activa
        ]
        return candidatas[0] if candidatas else None

    def invalidar_cache(self) -> None:
        self._base.invalidar_cache()
