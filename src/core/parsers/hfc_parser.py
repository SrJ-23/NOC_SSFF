"""Parser para procesar tablas pegadas de averías HFC (Grafana)."""

from __future__ import annotations

import re
from src.core.models.hfc_ftth_registro import HFCRegistro


def parse_hfc_text(text: str) -> list[HFCRegistro]:
    """
    Parsea texto copiado y pegado de la tabla de Grafana.
    Soporta formato tabular (separado por tabuladores/espacios)
    y formato de columna única (valores separados por saltos de línea).
    """
    if not text or not text.strip():
        return []

    # Limpiar líneas vacías
    raw_lines = [line.strip() for line in text.splitlines()]
    clean_lines = [l for l in raw_lines if l]

    if not clean_lines:
        return []

    # Determinar si el texto es tabular (múltiples columnas por línea)
    # o si viene como columna única (un dato por línea)
    has_tabs_or_spaces = False
    for line in clean_lines[:5]:
        if "\t" in line or re.search(r"\s{2,}", line):
            has_tabs_or_spaces = True
            break

    rows = []
    if has_tabs_or_spaces:
        for line in clean_lines:
            # Dividir por tabulación o por 2+ espacios consecutivos
            parts = [p.strip() for p in re.split(r"\t|\s{2,}", line) if p.strip()]
            if len(parts) >= 3:
                # Ignorar encabezados
                first_part_upper = parts[0].upper()
                if any(h in first_part_upper for h in ("PLANO", "EQUIPO", "AFECTADOS", "INCIDENT_ID", "AFECTACIÓN", "AFECTACION")):
                    continue
                plano = parts[0]
                equipo = parts[1]

                try:
                    clientes = int(parts[2])
                except ValueError:
                    continue

                inc = parts[3] if len(parts) > 3 else ""
                if not inc.strip().upper().startswith("INC"):
                    continue

                rows.append(HFCRegistro(
                    plano=plano,
                    equipo=equipo,
                    clientes=clientes,
                    inc=inc,
                    en_proceso=False
                ))
    else:
        # Columna única: filtrar líneas de títulos y encabezados conocidos
        data_values = []
        for line in clean_lines:
            up_line = line.upper()
            if any(h in up_line for h in ("PLANO", "EQUIPO", "AFECTADOS", "INCIDENT_ID", "AFECTACIÓN", "AFECTACION")):
                continue
            data_values.append(line)

        # Agrupar de 4 en 4
        for i in range(0, len(data_values), 4):
            chunk = data_values[i:i+4]
            if len(chunk) < 3:
                continue
            plano = chunk[0]
            equipo = chunk[1]
            try:
                clientes = int(chunk[2])
            except ValueError:
                continue
            inc = chunk[3] if len(chunk) > 3 else ""
            if not inc.strip().upper().startswith("INC"):
                continue

            rows.append(HFCRegistro(
                plano=plano,
                equipo=equipo,
                clientes=clientes,
                inc=inc,
                en_proceso=False
            ))

    return rows
