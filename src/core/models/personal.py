"""Modelo de dominio: Personal (config editable, fuente = Sheets:PERSONAL)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EstadoPersonal(str, Enum):
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"


@dataclass(frozen=True, slots=True)
class Personal:
    """Catálogo editable de personal (PEXT / técnicos / contactos)."""

    id: str
    nombre: str
    cargo: str
    telefono: str
    estado: EstadoPersonal

    @classmethod
    def from_dict(cls, data: dict) -> "Personal":
        estado_raw = str(data.get("ESTADO", EstadoPersonal.ACTIVO.value)).strip().upper()
        try:
            estado = EstadoPersonal(estado_raw)
        except ValueError:
            estado = EstadoPersonal.ACTIVO
        return cls(
            id=str(data.get("ID", "")).strip(),
            nombre=str(data.get("NOMBRE", "")).strip(),
            cargo=str(data.get("CARGO", "")).strip(),
            telefono=str(data.get("TELEFONO", "")).strip(),
            estado=estado,
        )

    def to_dict(self) -> dict:
        """Serializa para escritura en Google Sheets."""
        return {
            "ID": self.id,
            "NOMBRE": self.nombre,
            "CARGO": self.cargo,
            "TELEFONO": self.telefono,
            "ESTADO": self.estado.value,
        }
