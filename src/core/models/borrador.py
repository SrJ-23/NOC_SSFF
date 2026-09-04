"""Modelo de dominio: Borrador (dato operativo, fuente = Sheets:BORRADORES).

Representa el estado intermedio "Comparación -> Borrador -> Edición"
antes de que el analista confirme el guardado. La aplicación NUNCA
guarda automáticamente en Historial/Incidencias — siempre pasa por aquí.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from src.utils.time_utils import now_peru


class TipoMensajeBorrador(str, Enum):
    INICIAL = "INICIAL"
    ACTUALIZACION = "ACTUALIZACION"
    CIERRE = "CIERRE"


@dataclass(frozen=True, slots=True)
class Borrador:
    id: str
    inc: str
    tipo_mensaje: TipoMensajeBorrador
    texto_generado: str      # salida cruda del generador, antes de edición
    texto_editado: str       # lo que el analista efectivamente edita
    template_version_id: str
    creado_en: datetime
    confirmado: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "Borrador":
        return cls(
            id=str(data.get("ID", "")).strip(),
            inc=str(data.get("INC", "")).strip(),
            tipo_mensaje=TipoMensajeBorrador(str(data.get("TIPO_MENSAJE", "INICIAL")).strip().upper()),
            texto_generado=str(data.get("TEXTO_GENERADO", "")),
            texto_editado=str(data.get("TEXTO_EDITADO", "")),
            template_version_id=str(data.get("TEMPLATE_VERSION_ID", "")).strip(),
            creado_en=datetime.fromisoformat(str(data.get("CREADO_EN")))
            if data.get("CREADO_EN")
            else now_peru(),
            confirmado=str(data.get("CONFIRMADO", "FALSE")).strip().upper() == "TRUE",
        )

    def to_dict(self) -> dict:
        return {
            "ID": self.id,
            "INC": self.inc,
            "TIPO_MENSAJE": self.tipo_mensaje.value,
            "TEXTO_GENERADO": self.texto_generado,
            "TEXTO_EDITADO": self.texto_editado,
            "TEMPLATE_VERSION_ID": self.template_version_id,
            "CREADO_EN": self.creado_en.isoformat(),
            "CONFIRMADO": "TRUE" if self.confirmado else "FALSE",
        }
