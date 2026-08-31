"""
Modelos de dominio para registros parseados de HFC (Grafana) y FTTH (Huawei).

Estos NO son datos maestros ni operativos persistidos directamente;
son la salida estructurada de los parsers (core/parsers) antes de pasar
por el comparador correspondiente.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HFCRegistro:
    """Una fila interpretada de una tabla pegada desde Grafana."""

    plano: str
    equipo: str
    clientes: int
    inc: str
    en_proceso: bool = False  # marcado cuando la fila trae el valor "EN PROCESO"


@dataclass(frozen=True, slots=True)
class FTTHRegistro:
    """
    Un registro extraído de la columna "Other Information" del Excel Huawei.

    Nunca se retornan solo totales — cada registro conserva el detalle de
    OLT/puerto para que el comparador pueda hacer diffs a nivel de puerto,
    no solo de agregados.
    """

    olt: str
    port: str
    affected_onts: int
    description: str = ""
