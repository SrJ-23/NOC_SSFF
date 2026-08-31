"""Modelo de dominio: Referido (dato maestro, fuente = referidos.parquet)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Referido:
    """Cliente/equipo referido asociado a un plano. Solo lectura."""

    plano: str
    cargo: str
    nombre: str
    hub: str
    cmts: str
    cod_cliente: str
    cm: str
    mta: str
    modelo: str
    telefono: str

    @classmethod
    def from_dict(cls, data: dict) -> "Referido":
        return cls(
            plano=str(data.get("PLANO", "")).strip(),
            cargo=str(data.get("CARGO", "")).strip(),
            nombre=str(data.get("NOMBRE", "")).strip(),
            hub=str(data.get("HUB", "")).strip(),
            cmts=str(data.get("CMTS", "")).strip(),
            cod_cliente=str(data.get("COD_CLIENTE", "")).strip(),
            cm=str(data.get("CM", "")).strip(),
            mta=str(data.get("MTA", "")).strip(),
            modelo=str(data.get("MODELO", "")).strip(),
            telefono=str(data.get("TELEFONO", "")).strip(),
        )
