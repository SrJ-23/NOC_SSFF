"""Utilidades de tiempo: formateo de duraciones y cálculo de semáforo."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from src.config.settings import SEMAFORO_DEFAULT, SemaforoConfig


class ColorSemaforo(str, Enum):
    VERDE = "VERDE"
    AMARILLO = "AMARILLO"
    ROJO = "ROJO"


def formatear_duracion(minutos: float) -> str:
    """
    Convierte minutos a formato legible corto: "5 min", "1h 20min".
    Pensado para mostrarse directo en las tarjetas de incidencia.
    """
    minutos = max(0, int(minutos))
    horas, resto = divmod(minutos, 60)
    if horas == 0:
        return f"{resto} min"
    return f"{horas}h {resto}min"


def calcular_semaforo(
    minutos_transcurridos: float,
    is_closed: bool = False,
    config: SemaforoConfig = SEMAFORO_DEFAULT,
) -> ColorSemaforo:
    """
    Determina el color de semáforo según el estado de la incidencia y tiempo transcurrido.
    - VERDE: si está cerrada (solucionada).
    - AMARILLO (Ámbar): si está activa y se encuentra actualizada recientemente (<= amarillo_max_minutos, máx 1 hora).
    - ROJO: si está activa y supera el tiempo máximo sin actualizar (> amarillo_max_minutos, alerta).
    """
    if is_closed:
        return ColorSemaforo.VERDE
    if minutos_transcurridos <= config.amarillo_max_minutos:
        return ColorSemaforo.AMARILLO
    return ColorSemaforo.ROJO


def tiempo_transcurrido_desde(momento: datetime) -> float:
    """Minutos transcurridos desde `momento` hasta ahora."""
    return (datetime.now() - momento).total_seconds() / 60
