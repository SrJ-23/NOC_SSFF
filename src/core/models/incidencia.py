"""Modelo de dominio: Incidencia (dato operativo, fuente = Sheets:INCIDENCIAS)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TipoIncidencia(str, Enum):
    HFC = "HFC"
    FTTH = "FTTH"
    MIXTA = "MIXTA"


class EstadoIncidencia(str, Enum):
    """
    Máquina de estados de una incidencia.

    Importante: el ciclo NO es lineal de punta a punta. Una incidencia
    real transiciona muchas veces entre ACTIVA <-> BORRADOR <-> ACTUALIZADA
    (una vez por cada actualización que se envía) antes de llegar a
    CERRADA. Las transiciones válidas se validan en core/rules/incidencia_rules.py,
    no aquí — este enum solo define los valores posibles.
    """

    NUEVA = "NUEVA"
    ACTIVA = "ACTIVA"
    BORRADOR = "BORRADOR"
    ACTUALIZADA = "ACTUALIZADA"
    CERRADA = "CERRADA"


class ServicioAfectado(str, Enum):
    HFC = "HFC"
    FTTH = "FTTH"
    MBTS = "MBTS"
    CORPORATIVO = "CORPORATIVO"


@dataclass(frozen=True, slots=True)
class Incidencia:
    """Incidencia activa o cerrada gestionada por el NOC."""

    id: str
    inc: str
    tipo: TipoIncidencia
    estado: EstadoIncidencia
    tipo_falla: str
    departamento: str
    provincia: str
    distrito: str
    hora_inicio: datetime
    ultima_actualizacion: datetime
    bosf: str
    pext: str
    servicios: tuple[ServicioAfectado, ...] = field(default_factory=tuple)
    observaciones: str = ""

    @property
    def minutos_desde_ultima_actualizacion(self) -> float:
        delta = datetime.now() - self.ultima_actualizacion
        return delta.total_seconds() / 60

    @property
    def minutos_desde_inicio(self) -> float:
        delta = datetime.now() - self.hora_inicio
        return delta.total_seconds() / 60

    @classmethod
    def from_dict(cls, data: dict) -> "Incidencia":
        servicios_raw = data.get("SERVICIOS", "")
        if isinstance(servicios_raw, str):
            servicios = tuple(
                ServicioAfectado(s.strip().upper())
                for s in servicios_raw.split(",")
                if s.strip()
            )
        else:
            servicios = tuple(servicios_raw or ())

        return cls(
            id=str(data.get("ID", "")).strip(),
            inc=str(data.get("INC", "")).strip(),
            tipo=TipoIncidencia(str(data.get("TIPO", "HFC")).strip().upper()),
            estado=EstadoIncidencia(str(data.get("ESTADO", "NUEVA")).strip().upper()),
            tipo_falla=str(data.get("TIPO_FALLA", "")).strip(),
            departamento=str(data.get("DEPARTAMENTO", "")).strip(),
            provincia=str(data.get("PROVINCIA", "")).strip(),
            distrito=str(data.get("DISTRITO", "")).strip(),
            hora_inicio=_parse_datetime(data.get("HORA_INICIO")),
            ultima_actualizacion=_parse_datetime(data.get("ULTIMA_ACTUALIZACION")),
            bosf=str(data.get("BOSF", "")).strip(),
            pext=str(data.get("PEXT", "")).strip(),
            servicios=servicios,
            observaciones=str(data.get("OBSERVACIONES", "")).strip(),
        )

    def to_dict(self) -> dict:
        return {
            "ID": self.id,
            "INC": self.inc,
            "TIPO": self.tipo.value,
            "ESTADO": self.estado.value,
            "TIPO_FALLA": self.tipo_falla,
            "DEPARTAMENTO": self.departamento,
            "PROVINCIA": self.provincia,
            "DISTRITO": self.distrito,
            "HORA_INICIO": self.hora_inicio.isoformat(),
            "ULTIMA_ACTUALIZACION": self.ultima_actualizacion.isoformat(),
            "BOSF": self.bosf,
            "PEXT": self.pext,
            "SERVICIOS": ", ".join(s.value for s in self.servicios),
            "OBSERVACIONES": self.observaciones,
        }


def _parse_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if not value:
        return datetime.now()
    return datetime.fromisoformat(str(value))
