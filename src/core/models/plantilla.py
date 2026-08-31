"""Modelo de dominio: Plantilla de mensaje (config editable, fuente = Sheets:PLANTILLAS)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TipoMensaje(str, Enum):
    INICIAL = "INICIAL"
    ACTUALIZACION = "ACTUALIZACION"
    CIERRE = "CIERRE"


@dataclass(frozen=True, slots=True)
class Plantilla:
    """
    Plantilla de mensaje versionada.

    `version_id` es estable e inmutable una vez creada: si el analista
    edita el texto desde Configuración, se debe generar una NUEVA fila
    con un nuevo version_id (append-only), nunca sobrescribir la
    existente. Esto es lo que permite reconstruir mensajes históricos
    con fidelidad exacta (ver HistorialEvento.template_version_id).
    """

    version_id: str
    tipo_mensaje: TipoMensaje
    cuerpo: str          # texto con placeholders, ej. "{inc}", "{hora_inicio}"
    activa: bool = True  # solo una plantilla por tipo debe estar activa a la vez

    @classmethod
    def from_dict(cls, data: dict) -> "Plantilla":
        return cls(
            version_id=str(data.get("VERSION_ID", "")).strip(),
            tipo_mensaje=TipoMensaje(str(data.get("TIPO_MENSAJE", "INICIAL")).strip().upper()),
            cuerpo=str(data.get("CUERPO", "")),
            activa=str(data.get("ACTIVA", "TRUE")).strip().upper() == "TRUE",
        )

    def to_dict(self) -> dict:
        return {
            "VERSION_ID": self.version_id,
            "TIPO_MENSAJE": self.tipo_mensaje.value,
            "CUERPO": self.cuerpo,
            "ACTIVA": "TRUE" if self.activa else "FALSE",
        }
