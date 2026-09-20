"""Parser para procesar tablas pegadas de averías HFC (Grafana)."""

from __future__ import annotations

import re
from src.core.models.hfc_ftth_registro import HFCRegistro
from src.data.data_manager import get_data_manager


def _resolver_plano_y_inc(plano_raw: str, inc_raw: str) -> tuple[str, str, bool] | None:
    """
    Valida y resuelve el plano y la incidencia:
    - Si inc empieza con 'INC': es una fila válida normal.
    - Si inc es 'EN PROCESO' (o no empieza con 'INC'):
      se verifica si añadiendo '-A' o '-B' (o si ya los tiene) coincide con un plano gemelo en el catálogo maestro.
      Si coincide, se normaliza el plano al nombre gemelo oficial, se fija inc='EN PROCESO' y se acepta.
      Si no coincide, se descarta (retorna None).
    """
    p_clean = plano_raw.strip()
    inc_clean = inc_raw.strip()
    inc_upper = inc_clean.upper()

    if inc_upper.startswith("INC"):
        return p_clean, inc_clean, False

    if "PROCESO" in inc_upper or not inc_upper:
        try:
            dm = get_data_manager()
            p_up = p_clean.upper()
            if p_up.endswith(("-A", "-B")):
                for k, p in dm.planos.items():
                    if k.upper() == p_up:
                        return p.plano, "EN PROCESO", True
            for cand in (f"{p_up}-A", f"{p_up}-B"):
                for k, p in dm.planos.items():
                    if k.upper() == cand:
                        return p.plano, "EN PROCESO", True
        except Exception:
            pass

    return None


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
                res = _resolver_plano_y_inc(plano, inc)
                if not res:
                    continue
                final_plano, final_inc, en_proceso = res

                rows.append(HFCRegistro(
                    plano=final_plano,
                    equipo=equipo,
                    clientes=clientes,
                    inc=final_inc,
                    en_proceso=en_proceso
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
            res = _resolver_plano_y_inc(plano, inc)
            if not res:
                continue
            final_plano, final_inc, en_proceso = res

            rows.append(HFCRegistro(
                plano=final_plano,
                equipo=equipo,
                clientes=clientes,
                inc=final_inc,
                en_proceso=en_proceso
            ))

    return rows
