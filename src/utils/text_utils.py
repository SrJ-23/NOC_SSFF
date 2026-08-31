"""
Utilidades de normalización de texto, usadas por los parsers de HFC/FTTH.

Mantener esta lógica separada de los parsers permite reutilizarla y
testearla de forma aislada (ej. contra fixtures reales de Grafana/Huawei).
"""

from __future__ import annotations

import re


def normalizar_espacios(texto: str) -> str:
    """Colapsa espacios/tabs múltiples y recorta bordes."""
    return re.sub(r"[ \t]+", " ", texto).strip()


def es_fila_vacia(campos: list[str]) -> bool:
    """True si todos los campos de una fila están vacíos tras strip."""
    return all(not str(c).strip() for c in campos)


def contiene_en_proceso(texto: str) -> bool:
    """
    Detecta el valor especial "EN PROCESO" que Grafana puede mostrar
    en vez de un número de clientes, indicando que el dato aún no
    está consolidado.
    """
    return "en proceso" in texto.strip().lower()


def normalizar_columna(nombre: str) -> str:
    """
    Normaliza el nombre de una columna/encabezado para comparación
    tolerante a mayúsculas/acentos/espacios extra. Usado por el parser
    FTTH para ubicar encabezados dinámicamente (Severity, Object,
    Other Information) sin depender de posición fija.
    """
    nombre = nombre.strip().lower()
    nombre = re.sub(r"\s+", " ", nombre)
    return nombre
