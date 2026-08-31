"""Modelo de dominio: Plano (dato maestro, fuente = planos.parquet)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Plano:
    """
    Representa un plano/nodo de red (HFC o FTTH).

    Índice primario: `plano`.
    Solo lectura — proviene de planos.parquet, cargado una única vez
    por el DataManager al iniciar la aplicación.
    """

    plano: str
    tecnologia: str            # HFC / FTTH
    clientes: int
    cmts_olt: str
    hub: str
    anillo_troncal: str
    region: str
    site: str
    codigo_site: str
    suministro: str
    departamento: str
    provincia: str
    distrito: str
    direccion: str
    marca: str

    @classmethod
    def from_dict(cls, data: dict) -> "Plano":
        """
        Construye un Plano tolerando columnas faltantes (valor por defecto)
        y columnas adicionales (se ignoran). Esto sostiene el requisito de
        que la base maestra pueda crecer sin requerir cambios de código.
        """
        return cls(
            plano=str(data.get("PLANO", "")).strip(),
            tecnologia=str(data.get("TECNOLOGIA", "")).strip(),
            clientes=int(data.get("CLIENTES", 0) or 0),
            cmts_olt=str(data.get("CMTS_OLT", "")).strip(),
            hub=str(data.get("HUB", "")).strip(),
            anillo_troncal=str(data.get("ANILLO_TRONCAL", "")).strip(),
            region=str(data.get("REGION", "")).strip(),
            site=str(data.get("SITE", "")).strip(),
            codigo_site=str(data.get("CODIGO_SITE", "")).strip(),
            suministro=str(data.get("SUMINISTRO", "")).strip(),
            departamento=str(data.get("DEPARTAMENTO", "")).strip(),
            provincia=str(data.get("PROVINCIA", "")).strip(),
            distrito=str(data.get("DISTRITO", "")).strip(),
            direccion=str(data.get("DIRECCION", "")).strip(),
            marca=str(data.get("MARCA", "")).strip(),
        )
