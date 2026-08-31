"""Modelo de dominio: HistorialEvento (dato operativo, fuente = Sheets:HISTORIAL)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time


@dataclass(frozen=True, slots=True)
class HistorialEvento:
    """
    Un registro de historial = un evento, NUNCA un mensaje completo.

    El mensaje se reconstruye on-demand a partir de la plantilla + los
    datos del evento. `template_version_id` fija qué versión de la
    plantilla se usó, para que reconstruir un mensaje histórico sea
    fiel a lo que realmente se envió — incluso si la plantilla se edita
    después desde Configuración.
    """

    inc: str
    fecha: date
    hora: time
    tipo_evento: str
    template_version_id: str
    clientes_hfc: int = 0
    clientes_ftth: int = 0
    mbts: int = 0
    corporativos: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "HistorialEvento":
        return cls(
            inc=str(data.get("INC", "")).strip(),
            fecha=date.fromisoformat(str(data.get("FECHA"))),
            hora=time.fromisoformat(str(data.get("HORA"))),
            tipo_evento=str(data.get("TIPO_EVENTO", "")).strip(),
            template_version_id=str(data.get("TEMPLATE_VERSION_ID", "")).strip(),
            clientes_hfc=int(data.get("CLIENTES_HFC", 0) or 0),
            clientes_ftth=int(data.get("CLIENTES_FTTH", 0) or 0),
            mbts=int(data.get("MBTS", 0) or 0),
            corporativos=int(data.get("CORPORATIVOS", 0) or 0),
        )

    def to_dict(self) -> dict:
        return {
            "INC": self.inc,
            "FECHA": self.fecha.isoformat(),
            "HORA": self.hora.isoformat(),
            "TIPO_EVENTO": self.tipo_evento,
            "TEMPLATE_VERSION_ID": self.template_version_id,
            "CLIENTES_HFC": self.clientes_hfc,
            "CLIENTES_FTTH": self.clientes_ftth,
            "MBTS": self.mbts,
            "CORPORATIVOS": self.corporativos,
        }
