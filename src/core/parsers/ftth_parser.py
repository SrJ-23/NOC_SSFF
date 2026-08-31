"""Parser para archivos Excel de alarmas FTTH exportados desde Huawei NCE."""

from __future__ import annotations

import re
import io
from dataclasses import dataclass

try:
    import pandas as pd
    PANDAS_OK = True
except ImportError:
    PANDAS_OK = False


@dataclass
class FtthReporte:
    """Resultado del parseo de un archivo Excel FTTH."""
    planos: list[dict]          # [{"plano": str, "onts": int}, ...]
    total_onts: int
    olts: list[str]             # Nombres de OLT detectadas
    arrived_on_str: str         # Rango de fechas de las alarmas
    hora_deteccion: str         # Primera hora detectada "HH:MM" o ""
    ok: bool
    error: str


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
            if fila.astype(str).str.contains("Arrived On", case=False, na=False).any():
                fila_cabecera = idx
                break

        # 2. Cargar datos reales
        df = pd.read_excel(buf, skiprows=fila_cabecera, engine="openpyxl")
        df.columns = df.columns.str.strip()

        mapa = {col.lower(): col for col in df.columns}
        col_user_label  = mapa.get("user label")
        col_alarm_source = mapa.get("alarm source")
        col_other_info  = mapa.get("other information")
        col_arrived_on  = mapa.get("arrived on (st)")

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
        if col_arrived_on and col_arrived_on in df.columns:
            fechas = pd.to_datetime(df[col_arrived_on], errors="coerce").dropna()
            if not fechas.empty:
                f_min = fechas.min()
                f_max = fechas.max()
                min_str = f_min.strftime("%Y-%m-%d %H:%M:%S")
                max_str = f_max.strftime("%Y-%m-%d %H:%M:%S")
                arrived_on_str = min_str if min_str == max_str else f"{min_str} a {max_str}"
                hora_deteccion = f_min.strftime("%H:%M")

        return FtthReporte(
            planos=planos,
            total_onts=total_onts,
            olts=olts,
            arrived_on_str=arrived_on_str,
            hora_deteccion=hora_deteccion,
            ok=True,
            error=""
        )

    except Exception as exc:
        return FtthReporte([], 0, [], "", "", False, str(exc))


def parse_ftth_text(text: str) -> FtthReporte:
    """
    Parsea texto copiado desde Huawei NCE/iManager (formato TSV con cabecera).
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
        if "user label" in line.lower() or "arrived on" in line.lower():
            header_idx = i
            break

    if header_idx is None:
        return FtthReporte([], 0, [], "", "", False,
                           "No se detectó cabecera (columnas 'User Label' / 'Arrived On').")

    # Parsear cabecera
    headers = [h.strip().lower() for h in lines[header_idx].split("\t")]

    def col(name: str) -> int | None:
        for i, h in enumerate(headers):
            if name in h:
                return i
        return None

    idx_user_label   = col("user label")
    idx_arrived_on   = col("arrived on")
    idx_alarm_source = col("alarm source")
    idx_other_info   = col("other information")

    if idx_user_label is None or idx_other_info is None:
        return FtthReporte([], 0, [], "", "", False,
                           "Columnas 'User Label' u 'Other Information' no encontradas en el texto.")

    planos_map: dict[str, int] = {}
    olts_set: set[str] = set()
    fechas_list = []

    for line in lines[header_idx + 1:]:
        if not line.strip():
            continue
        parts = line.split("\t")

        def get(idx):
            if idx is None or idx >= len(parts):
                return ""
            return parts[idx].strip()

        user_label  = get(idx_user_label)
        other_info  = get(idx_other_info)
        alarm_source = get(idx_alarm_source) if idx_alarm_source is not None else ""
        arrived_on  = get(idx_arrived_on) if idx_arrived_on is not None else ""

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
            try:
                from datetime import datetime as _dt
                fechas_list.append(_dt.fromisoformat(arrived_on))
            except Exception:
                pass

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
    if fechas_list:
        f_min = min(fechas_list)
        f_max = max(fechas_list)
        min_str = f_min.strftime("%Y-%m-%d %H:%M:%S")
        max_str = f_max.strftime("%Y-%m-%d %H:%M:%S")
        arrived_on_str = min_str if min_str == max_str else f"{min_str} a {max_str}"
        hora_deteccion = f_min.strftime("%H:%M")

    return FtthReporte(
        planos=planos,
        total_onts=total_onts,
        olts=olts,
        arrived_on_str=arrived_on_str,
        hora_deteccion=hora_deteccion,
        ok=True,
        error=""
    )


