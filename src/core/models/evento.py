"""Modelo de dominio: Evento (catálogo editable, fuente = Sheets:EVENTOS)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Evento:
    """
    Entrada de catálogo de eventos de línea de tiempo
    (ej. "Derivación", "Punto de Corte", "Restablecimiento").

    `parametros` lista los nombres de parámetros que este evento puede
    solicitar al analista (ej. ["POP", "SITE", "KM"]), y `plantilla`
    referencia el id de plantilla de mensaje asociada. La resolución real
    de parámetros -> texto vive en core/generators, no aquí.
    """

    id: str
    tipo: str                       # HFC / FTTH / ambos
    descripcion: str
    parametros: tuple[str, ...] = field(default_factory=tuple)
    plantilla_id: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Evento":
        params_raw = data.get("PARAMETROS", "")
        if isinstance(params_raw, str):
            parametros = tuple(p.strip() for p in params_raw.split(",") if p.strip())
        else:
            parametros = tuple(params_raw or ())
        return cls(
            id=str(data.get("ID", "")).strip(),
            tipo=str(data.get("TIPO", "")).strip(),
            descripcion=str(data.get("DESCRIPCION", "")).strip(),
            parametros=parametros,
            plantilla_id=str(data.get("PLANTILLA", "")).strip(),
        )

    def to_dict(self) -> dict:
        return {
            "ID": self.id,
            "TIPO": self.tipo,
            "DESCRIPCION": self.descripcion,
            "PARAMETROS": ", ".join(self.parametros),
            "PLANTILLA": self.plantilla_id,
        }
