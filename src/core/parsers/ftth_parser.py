"""Parser para archivos Excel de alarmas FTTH exportados desde Huawei NCE."""

from __future__ import annotations

import re
import io
from dataclasses import dataclass
from datetime import datetime

try:
    import pandas as pd
    PANDAS_OK = True
except ImportError:
    PANDAS_OK = False


def _parse_flexible_datetime(val) -> datetime | None:
    """Parsea una fecha/hora en múltiples formatos comunes (ISO, DD/MM/YYYY, etc.)"""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip().strip("'\"")
    if not s or s.lower() in ("nan", "nat", "none", "null", "-"):
        return None

    # Si empieza con año YYYY
    if re.match(r"^\d{4}[-/]", s):
        try:
            dt = pd.to_datetime(s, errors="coerce") if PANDAS_OK else None
            if dt is not None and not pd.isna(dt):
                return dt.to_pydatetime() if hasattr(dt, "to_pydatetime") else dt
        except Exception:
            pass
    else:
        # Formato día primero DD/MM/YYYY
        try:
            dt = pd.to_datetime(s, dayfirst=True, errors="coerce") if PANDAS_OK else None
            if dt is not None and not pd.isna(dt):
                return dt.to_pydatetime() if hasattr(dt, "to_pydatetime") else dt
        except Exception:
            pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass

    m = re.search(r"(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})\s+(\d{1,2}:\d{2}(?::\d{2})?)", s)
    if m and PANDAS_OK:
        try:
            dt = pd.to_datetime(f"{m.group(1)} {m.group(2)}", dayfirst=True, errors="coerce")
            if not pd.isna(dt):
                return dt.to_pydatetime() if hasattr(dt, "to_pydatetime") else dt
        except Exception:
            pass

    return None


@dataclass
class FtthReporte:
    """Resultado del parseo de un archivo Excel o texto FTTH."""
    planos: list[dict]          # [{"plano": str, "onts": int}, ...]
    total_onts: int
    olts: list[str]             # Nombres de OLT detectadas
    arrived_on_str: str         # Rango de fechas de las alarmas
    hora_deteccion: str         # Primera hora detectada "HH:MM" o ""
    ok: bool
    error: str
    fecha_deteccion_str: str = "" # Primera fecha detectada "YYYY-MM-DD" o ""
    dt_deteccion: datetime | None = None # Objeto datetime de la primera detección


def parse_ftth_excel(file_bytes: bytes, filename: str = "") -> FtthReporte:
    """
    Parsea un archivo Excel (.xlsx) de alarmas FTTH exportado desde Huawei NCE.
    Devuelve un FtthReporte con los planos agrupados y sus ONTs sumadas.
    """
    if not PANDAS_OK:
        return FtthReporte([], 0, [], "", "", False, "pandas no está instalado.")

    try:
        buf = io.BytesIO(file_bytes)

        # 1. Detectar dinámicamente la fila de cabecera buscando "Arrived On"
        df_temp = pd.read_excel(buf, header=None, engine="openpyxl")
        buf.seek(0)

        fila_cabecera = 5  # fallback
        for idx, fila in df_temp.iterrows():
            if fila.astype(str).str.contains(r"arrived\s*on", case=False, na=False, regex=True).any():
                fila_cabecera = idx
                break

        # 2. Cargar datos reales
        df = pd.read_excel(buf, skiprows=fila_cabecera, engine="openpyxl")
        df.columns = [re.sub(r"\s+", " ", str(col)).strip() for col in df.columns]

        def find_col(pat: str):
            for col in df.columns:
                if re.search(pat, col, re.IGNORECASE):
                    return col
            return None

        col_user_label   = find_col(r"user\s*label")
        col_alarm_source = find_col(r"alarm\s*source")
        col_other_info   = find_col(r"other\s*information")
        col_arrived_on   = find_col(r"arrived\s*on")

        if not col_user_label or not col_other_info:
            return FtthReporte([], 0, [], "", "", False,
                               "No se encontraron las columnas 'User Label' u 'Other Information'.")

        # 3. Extraer plano y ONTs
        def extraer_plano(label):
            if pd.isna(label):
                return "DESCONOCIDO"
            partes = re.split(r"[-_][Tt][Rr]?\d+", str(label).strip())
            return partes[0].strip() if partes else str(label).strip()

        def extraer_onts(info):
            if pd.isna(info):
                return 0
            m = re.search(r"The number of affected ONTs=(\d+)", str(info))
            return int(m.group(1)) if m else 0

        df["Plano"]         = df[col_user_label].apply(extraer_plano)
        df["ONTs Afectadas"] = df[col_other_info].apply(extraer_onts)

        # Filtrar filas sin datos útiles
        df = df[df["Plano"] != "DESCONOCIDO"]
        df = df[df["ONTs Afectadas"] > 0]

        # 4. Tabla dinámica agrupada por plano
        tabla = df.groupby("Plano")["ONTs Afectadas"].sum().reset_index()
        tabla = tabla.sort_values("ONTs Afectadas", ascending=False)
        planos = [
            {"plano": row["Plano"], "onts": int(row["ONTs Afectadas"])}
            for _, row in tabla.iterrows()
        ]
        total_onts = int(tabla["ONTs Afectadas"].sum())

        # 5. OLTs detectadas
        olts = []
        if col_alarm_source and col_alarm_source in df.columns:
            olts = [str(x) for x in df[col_alarm_source].dropna().unique()]

        # 6. Rango de fechas de las alarmas
        arrived_on_str = ""
        hora_deteccion = ""
        fecha_deteccion_str = ""
        dt_deteccion = None
        if col_arrived_on and col_arrived_on in df.columns:
            fechas_parsed = []
            for val in df[col_arrived_on].dropna():
                dt = _parse_flexible_datetime(val)
                if dt:
                    fechas_parsed.append(dt)
            if fechas_parsed:
                f_min = min(fechas_parsed)
                f_max = max(fechas_parsed)
                min_str = f_min.strftime("%Y-%m-%d %H:%M:%S")
                max_str = f_max.strftime("%Y-%m-%d %H:%M:%S")
                arrived_on_str = min_str if min_str == max_str else f"{min_str} a {max_str}"
                hora_deteccion = f_min.strftime("%H:%M")
                fecha_deteccion_str = f_min.strftime("%Y-%m-%d")
                dt_deteccion = f_min

        return FtthReporte(
            planos=planos,
            total_onts=total_onts,
            olts=olts,
            arrived_on_str=arrived_on_str,
            hora_deteccion=hora_deteccion,
            ok=True,
            error="",
            fecha_deteccion_str=fecha_deteccion_str,
            dt_deteccion=dt_deteccion
        )

    except Exception as exc:
        return FtthReporte([], 0, [], "", "", False, str(exc))


def parse_ftth_text(text: str) -> FtthReporte:
    """
    Parsea texto copiado desde Huawei NCE/iManager (formato TSV o tabla con cabecera).
    Columnas esperadas: Operation, Comments, Arrived On (ST), Last Occurred (ST),
    Occurrences, User Label, Severity, Alarm ID, Name, Alarm Source, Other Information, ...
    Devuelve un FtthReporte igual que parse_ftth_excel.
    """
    if not text or not text.strip():
        return FtthReporte([], 0, [], "", "", False, "Texto vacío.")

    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return FtthReporte([], 0, [], "", "", False, "Sin líneas válidas.")

    # Detectar la fila cabecera (contiene "User Label" o "Arrived On")
    header_idx = None
    for i, line in enumerate(lines):
        if re.search(r"user\s*label", line, re.I) or re.search(r"arrived\s*on", line, re.I):
            header_idx = i
            break

    if header_idx is None:
        return FtthReporte([], 0, [], "", "", False,
                           "No se detectó cabecera (columnas 'User Label' / 'Arrived On').")

    raw_header = lines[header_idx]
    delim = "\t" if "\t" in raw_header else ("," if "," in raw_header else None)
    if delim:
        headers = [re.sub(r"\s+", " ", h).strip().lower() for h in raw_header.split(delim)]
    else:
        headers = [re.sub(r"\s+", " ", h).strip().lower() for h in re.split(r"\s{2,}", raw_header)]

    def col(pat: str) -> int | None:
        for i, h in enumerate(headers):
            if re.search(pat, h, re.IGNORECASE):
                return i
        return None

    idx_user_label   = col(r"user\s*label")
    idx_arrived_on   = col(r"arrived\s*on")
    idx_alarm_source = col(r"alarm\s*source")
    idx_other_info   = col(r"other\s*information")

    if idx_user_label is None or idx_other_info is None:
        return FtthReporte([], 0, [], "", "", False,
                           "Columnas 'User Label' u 'Other Information' no encontradas en el texto.")

    planos_map: dict[str, int] = {}
    olts_set: set[str] = set()
    fechas_list = []

    for line in lines[header_idx + 1:]:
        if not line.strip():
            continue
        parts = line.split(delim) if delim else re.split(r"\s{2,}", line)

        def get(idx):
            if idx is None or idx >= len(parts):
                return ""
            return parts[idx].strip()

        user_label   = get(idx_user_label)
        other_info   = get(idx_other_info)
        alarm_source = get(idx_alarm_source) if idx_alarm_source is not None else ""
        arrived_on   = get(idx_arrived_on) if idx_arrived_on is not None else ""

        if not user_label:
            continue

        # Extraer plano (quitar sufijo -TRxxx o _Txxx)
        plano = re.split(r"[-_][Tt][Rr]?\d+", user_label.strip())[0].strip()
        if not plano:
            continue

        # Extraer ONTs
        m = re.search(r"The number of affected ONTs=(\d+)", other_info)
        onts = int(m.group(1)) if m else 0
        if onts == 0:
            continue

        planos_map[plano] = planos_map.get(plano, 0) + onts

        if alarm_source:
            olts_set.add(alarm_source)

        if arrived_on:
            dt_parsed = _parse_flexible_datetime(arrived_on)
            if dt_parsed:
                fechas_list.append(dt_parsed)

    if not planos_map:
        return FtthReporte([], 0, [], "", "", False,
                           "No se detectaron planos con ONTs > 0 en el texto pegado.")

    planos = sorted(
        [{"plano": k, "onts": v} for k, v in planos_map.items()],
        key=lambda x: x["onts"], reverse=True
    )
    total_onts = sum(p["onts"] for p in planos)
    olts = sorted(olts_set)

    arrived_on_str = ""
    hora_deteccion = ""
    fecha_deteccion_str = ""
    dt_deteccion = None
    if fechas_list:
        f_min = min(fechas_list)
        f_max = max(fechas_list)
        min_str = f_min.strftime("%Y-%m-%d %H:%M:%S")
        max_str = f_max.strftime("%Y-%m-%d %H:%M:%S")
        arrived_on_str = min_str if min_str == max_str else f"{min_str} a {max_str}"
        hora_deteccion = f_min.strftime("%H:%M")
        fecha_deteccion_str = f_min.strftime("%Y-%m-%d")
        dt_deteccion = f_min

    return FtthReporte(
        planos=planos,
        total_onts=total_onts,
        olts=olts,
        arrived_on_str=arrived_on_str,
        hora_deteccion=hora_deteccion,
        ok=True,
        error="",
        fecha_deteccion_str=fecha_deteccion_str,
        dt_deteccion=dt_deteccion
    )



