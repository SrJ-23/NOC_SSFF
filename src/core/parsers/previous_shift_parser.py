"""Parser para mensajes consolidados de WhatsApp del turno anterior."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from src.core.models import TipoIncidencia, EstadoIncidencia, ServicioAfectado
from src.utils.time_utils import now_peru


@dataclass
class ParsedIncidenciaAnterior:
    raw_block: str
    inc: str = "EN PROCESO"
    tipo: TipoIncidencia = TipoIncidencia.FTTH
    estado: EstadoIncidencia = EstadoIncidencia.ACTIVA
    tipo_falla: str = "Corte de Fibra"
    departamento: str = "LIMA"
    provincia: str = "LIMA"
    distrito: str = "LIMA"
    plano: str = ""
    equipo: str = ""
    etiqueta: str = ""
    clientes: int = 0
    clientes_totales: int = 0
    porcentaje: str = ""
    hora_inicio: datetime | None = None
    hora_solucion: str = ""
    bosf: str = "Pendiente"
    telefono: str = ""
    pext: str = ""
    servicios: list[ServicioAfectado] = field(default_factory=list)
    actualizaciones: list[str] = field(default_factory=list)
    planos_lista: list[str] = field(default_factory=list)
    hfc_adicional: str = ""
    mbts_adicional: str = ""
    corp_adicional: str = ""
    observaciones: str = ""


def separar_bloques_averias(texto_completo: str) -> list[str]:
    """Separa el texto consolidado del turno anterior en bloques individuales de avería."""
    if not texto_completo or not texto_completo.strip():
        return []

    # Quitar cabeceras generales iniciales como =====AVERÍAS===== o =================
    limpio = re.sub(r"^\s*=+\s*(?:AVER[ÍI]AS)?\s*=+\s*", "", texto_completo, flags=re.IGNORECASE).strip()

    # Separar por líneas de asteriscos (10 o más) o líneas de iguales
    partes = re.split(r"(?:\r?\n\s*\*+[*\s]{8,}\*+\s*\r?\n)|(?:\r?\n\s*={8,}\s*\r?\n)", limpio)
    
    bloques = []
    for p in partes:
        p_str = p.strip()
        # Verificar que el bloque tenga contenido de avería
        if p_str and ("*NOC" in p_str or "FALLA" in p_str or "IMPACTO" in p_str or "TICKET" in p_str or "INC" in p_str):
            bloques.append(p_str)

    # Si no se separó por asteriscos pero contiene múltiples *NOC, intentar separar por *NOC
    if len(bloques) <= 1 and limpio.count("*NOC") > 1:
        partes_noc = re.split(r"(?=(?:\r?\n|^)\s*\*NOC\s*[-–]?\s*SERVICIOS\s*FIJOS\*)", limpio, flags=re.IGNORECASE)
        bloques_noc = [b.strip() for b in partes_noc if b.strip() and ("FALLA" in b or "IMPACTO" in b)]
        if len(bloques_noc) > len(bloques):
            bloques = bloques_noc

    return bloques


def _parse_fecha_hora(fecha_str: str, hora_str: str) -> datetime | None:
    """Parsea fecha DD/MM/YYYY y hora HH:MM a un objeto datetime."""
    try:
        f_parts = [int(x) for x in fecha_str.strip().split("/")]
        h_parts = [int(x) for x in hora_str.strip().replace("h", "").split(":")]
        return datetime(f_parts[2], f_parts[1], f_parts[0], h_parts[0], h_parts[1])
    except Exception:
        return None


def parsear_bloque_averia(bloque: str, planos_repo=None) -> ParsedIncidenciaAnterior:
    """Parsea un bloque individual de mensaje WhatsApp y extrae todos los datos de la incidencia."""
    res = ParsedIncidenciaAnterior(raw_block=bloque)

    # 1. Determinar si está CERRADA / SOLUCIONADA
    if "FINAL / CIERRE" in bloque.upper() or "*SOLUCIONADO:*" in bloque.upper():
        res.estado = EstadoIncidencia.CERRADA
    else:
        res.estado = EstadoIncidencia.ACTIVA

    # 2. Extraer Ticket Asignado / INC
    m_inc = re.search(r"TICKET\s*ASIGNADO\s*:\s*([^\n\r]+)", bloque, re.IGNORECASE)
    if m_inc:
        val_inc = m_inc.group(1).strip().replace("*", "")
        if val_inc.upper() != "EN PROCESO":
            m_code = re.search(r"(INC\d+)", val_inc, re.IGNORECASE)
            res.inc = m_code.group(1).upper() if m_code else val_inc.upper()
        else:
            res.inc = "EN PROCESO"
    else:
        m_inc_fallback = re.search(r"con\s+(INC\d+)", bloque, re.IGNORECASE)
        if m_inc_fallback:
            res.inc = m_inc_fallback.group(1).upper()

    # 3. Determinar Tecnología (FTTH vs HFC)
    es_ftth = bool(
        re.search(r"FTTH", bloque, re.IGNORECASE)
        or re.search(r"Corte de Fibra", bloque, re.IGNORECASE)
        or re.search(r"OLT", bloque, re.IGNORECASE)
    )
    es_hfc = bool(
        re.search(r"Caída de nodo HFC", bloque, re.IGNORECASE)
        or re.search(r"Clientes HFC", bloque, re.IGNORECASE)
        or re.search(r"\*HFC", bloque, re.IGNORECASE)
    )

    if es_ftth and es_hfc:
        # Si tiene sección principal FTTH con bloque adicional HFC
        if "Corte de Fibra" in bloque or "* FTTH:" in bloque:
            res.tipo = TipoIncidencia.FTTH
            res.servicios = [ServicioAfectado.FTTH, ServicioAfectado.HFC]
        else:
            res.tipo = TipoIncidencia.HFC
            res.servicios = [ServicioAfectado.HFC, ServicioAfectado.FTTH]
    elif es_hfc:
        res.tipo = TipoIncidencia.HFC
        res.servicios = [ServicioAfectado.HFC]
    else:
        res.tipo = TipoIncidencia.FTTH
        res.servicios = [ServicioAfectado.FTTH]

    # 4. Extraer BOSF y Teléfono
    m_atiende = re.search(r"\*ATIENDE:\*\s*(?:[^\n\r]*\r?\n)?\s*\*?\s*BOSF\s+([A-Za-zÁÉÍÓÚáéíóúñÑ\s]+?)(?:-(\d{9})|\s+con|\s*\r?\n|$)", bloque, re.IGNORECASE)
    if not m_atiende:
        m_atiende = re.search(r"\*Atiende\s+BOSF\s+([A-Za-zÁÉÍÓÚáéíóúñÑ\s]+?)(?:-(\d{9})|\s+con|\s*\r?\n|$)", bloque, re.IGNORECASE)

    if m_atiende:
        res.bosf = m_atiende.group(1).strip().replace("*", "")
        if m_atiende.group(2):
            res.telefono = m_atiende.group(2).strip()

    if not res.telefono:
        m_tel = re.search(r"-(\d{9})", bloque)
        if m_tel:
            res.telefono = m_tel.group(1).strip()

    # 5. Extraer Falla, Hora de inicio, Ubicación y Plano/Etiqueta
    m_falla = re.search(r"\*FALLA:\*\s*([^\n\r]+(?:\r?\n(?!\*|\r?\n)[^\n\r]+)*)", bloque, re.IGNORECASE)
    if not m_falla:
        m_falla = re.search(r"FALLA:\s*([^\n\r]+(?:\r?\n(?!\*|\r?\n)[^\n\r]+)*)", bloque, re.IGNORECASE)

    falla_texto = m_falla.group(1).strip() if m_falla else ""

    # Fecha y Hora de inicio desde la línea de falla
    m_dt = re.search(r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}:\d{2})\s*h?", falla_texto)
    if m_dt:
        res.hora_inicio = _parse_fecha_hora(m_dt.group(1), m_dt.group(2))
    else:
        # Fallback a cualquier fecha/hora en el bloque
        m_dt_fb = re.search(r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}:\d{2})\s*h?", bloque)
        if m_dt_fb:
            res.hora_inicio = _parse_fecha_hora(m_dt_fb.group(1), m_dt_fb.group(2))
        else:
            res.hora_inicio = now_peru()

    # Hora de solución
    m_sol = re.search(r"\*HORA DE SOLUCI[ÓO]N\s*:\*\s*([^\n\r]+)", bloque, re.IGNORECASE)
    if m_sol:
        res.hora_solucion = m_sol.group(1).strip().replace("*", "")

    # Tipo de falla
    if "Corte de Fibra" in falla_texto:
        res.tipo_falla = "Corte de Fibra"
    elif "Caída de nodo" in falla_texto or "Caida de nodo" in falla_texto:
        res.tipo_falla = "Caída de nodo HFC" if res.tipo == TipoIncidencia.HFC else "Caída de nodo"
    elif "Caida de OLT" in falla_texto or "Caída de OLT" in falla_texto:
        res.tipo_falla = "Caída de OLT FTTH"
    else:
        res.tipo_falla = "Corte de Fibra" if res.tipo == TipoIncidencia.FTTH else "Caída de nodo HFC"

    # Etiqueta / Plano entre paréntesis en la línea de falla
    m_etiqueta = re.search(r"\(([^)]+)\)", falla_texto)
    if m_etiqueta:
        res.etiqueta = m_etiqueta.group(1).strip()

    # Si es HFC individual
    if res.tipo == TipoIncidencia.HFC:
        # Caída de nodo HFC CHI059 en CHICLAYO - LAMBAYEQUE
        m_hfc_nodo = re.search(r"nodo\s+HFC\s+([A-Za-z0-9_-]+)", falla_texto, re.IGNORECASE)
        if m_hfc_nodo:
            res.plano = m_hfc_nodo.group(1).strip().upper()

        m_nodo_caida = re.search(r"Por caída de nodo:\s*([A-Za-z0-9_-]+)", bloque, re.IGNORECASE)
        if m_nodo_caida:
            nodo_full = m_nodo_caida.group(1).strip()
            if "_" in nodo_full:
                parts = nodo_full.split("_", 1)
                if not res.plano:
                    res.plano = parts[0].strip().upper()
                res.equipo = parts[1].strip().upper()
            elif not res.plano:
                res.plano = nodo_full.upper()

        m_cli_hfc = re.search(r"Afectación de\s*(\d+)\s*Clientes", bloque, re.IGNORECASE)
        if m_cli_hfc:
            res.clientes = int(m_cli_hfc.group(1))

        # Ubicación en HFC: en DISTRITO - DEPARTAMENTO
        m_ubi_hfc = re.search(r"en\s+([A-Za-zÁÉÍÓÚáéíóúñÑ\s]+?)(?:\s*-\s*([A-Za-zÁÉÍÓÚáéíóúñÑ\s]+?))?\s+\d{1,2}/\d{1,2}/\d{4}", falla_texto)
        if m_ubi_hfc:
            p1 = m_ubi_hfc.group(1).strip()
            p2 = m_ubi_hfc.group(2).strip() if m_ubi_hfc.group(2) else ""
            if p2:
                res.distrito = p1.upper()
                res.departamento = p2.upper()
                res.provincia = p1.upper()
            else:
                res.departamento = p1.upper()
                res.provincia = p1.upper()
                res.distrito = p1.upper()

    else:
        # FTTH Ubicación
        m_dep = re.search(r"Departamento de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ\s]+?)(?:,|\s+Prov|\s+prov|\s+Distrito|\s*\(|\s*-|$)", falla_texto, re.IGNORECASE)
        if not m_dep:
            m_dep = re.search(r"DEPARTAMENTO DE\s+([A-Za-zÁÉÍÓÚáéíóúñÑ\s,]+)", bloque, re.IGNORECASE)
        if m_dep:
            res.departamento = m_dep.group(1).split(",")[0].strip().upper()

        m_prov = re.search(r"Prov(?:incia|\.)\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ\s]+?)(?:,|\s+Distrito|\s*\(|\s*-|$)", falla_texto, re.IGNORECASE)
        if not m_prov:
            m_prov = re.search(r"PROVINCIA\s*:\s*([A-Za-zÁÉÍÓÚáéíóúñÑ\s]+)", bloque, re.IGNORECASE)
        if m_prov:
            res.provincia = m_prov.group(1).strip().upper()
        else:
            res.provincia = res.departamento

        m_dist = re.search(r"Distrito de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ\s]+?)(?:,|\s*\(|\s*-|$)", falla_texto, re.IGNORECASE)
        if not m_dist:
            m_dist = re.search(r"DISTRITO\s*:\s*([A-Za-zÁÉÍÓÚáéíóúñÑ\s]+)", bloque, re.IGNORECASE)
        if m_dist:
            res.distrito = m_dist.group(1).strip().upper()
        else:
            res.distrito = res.provincia

        # Clientes FTTH
        m_cli_ftth = re.search(r"\*\s*FTTH:\s*(\d+)\s*clientes(?:\s*de\s*(\d+))?(?:\s*\(([\d\.]+%?)\))?", bloque, re.IGNORECASE)
        if m_cli_ftth:
            res.clientes = int(m_cli_ftth.group(1))
            if m_cli_ftth.group(2):
                res.clientes_totales = int(m_cli_ftth.group(2))
            if m_cli_ftth.group(3):
                res.porcentaje = m_cli_ftth.group(3).strip()

        # Planos al pie del mensaje (códigos de plano como UCPA003-F o LMLO020...)
        lineas_finales = bloque.strip().split("\n")[-6:]
        posibles_planos = []
        for lf in lineas_finales:
            lf_str = lf.strip()
            if re.match(r"^[A-Z]{4}\d{3}[A-Z0-9_-]*$", lf_str):
                posibles_planos.append(lf_str)
            elif re.match(r"^[A-Z]{2,4}[A-Z0-9_-]{4,20}$", lf_str) and not any(k in lf_str for k in ["NOC", "FALLA", "HORA", "SOLUCION", "BOSF"]):
                posibles_planos.append(lf_str)

        if posibles_planos:
            res.planos_lista = posibles_planos
            res.plano = posibles_planos[0]
        elif res.etiqueta and re.match(r"^[A-Z]{4}\d{3}", res.etiqueta):
            res.plano = res.etiqueta
            res.planos_lista = [res.etiqueta]

    # 6. Complementar datos geográficos desde planos_repo si el plano existe
    if planos_repo and res.plano:
        pobj = planos_repo.obtener_por_id(res.plano)
        if pobj:
            if not res.departamento or res.departamento == "LIMA":
                res.departamento = pobj.departamento
            if not res.provincia or res.provincia == "LIMA":
                res.provincia = pobj.provincia
            if not res.distrito or res.distrito == "LIMA":
                res.distrito = pobj.distrito
            if not res.equipo and pobj.cmts_olt:
                res.equipo = pobj.cmts_olt

    # 7. Extraer Historial de Actualizaciones
    m_act_sec = re.search(r"\*ACTUALIZACI[ÓO]N\s*:\*\s*(?:[^\n\r]*\r?\n)?([\s\S]*?)(?=\*HORA DE SOLUCI[ÓO]N|\*SOLUCIONADO|\Z)", bloque, re.IGNORECASE)
    if not m_act_sec:
        m_act_sec = re.search(r"\*SOLUCIONADO:\*\s*(?:[^\n\r]*\r?\n)?([\s\S]*?)(?=\*HORA DE SOLUCI[ÓO]N|\Z)", bloque, re.IGNORECASE)

    if m_act_sec:
        sec_texto = m_act_sec.group(1)
        for linea in sec_texto.split("\n"):
            linea_s = linea.strip()
            # Capturar líneas con hora *HH:MMh ...
            m_line = re.search(r"^\*?(\d{1,2}:\d{2})\s*h?\s*(.*)", linea_s)
            if m_line:
                hora_h = m_line.group(1)
                desc = m_line.group(2).strip()
                res.actualizaciones.append(f"[{hora_h}] {desc}")

    # 8. Extraer servicios adicionales si hubiesen
    m_hfc_ad = re.search(r"(\*HFC\s*\(\d+\s*NODOS\):[^\n\r]+)", bloque, re.IGNORECASE)
    if m_hfc_ad:
        res.hfc_adicional = m_hfc_ad.group(1).strip()

    m_mbts = re.search(r"\*AFECTACIÓN DE SERVICIOS MÓVILES \(MBTS\)\*([\s\S]*?)(?=\*AFECTACIÓN|\*ATIENDE|\*ACTUALIZACI|$)", bloque, re.IGNORECASE)
    if m_mbts:
        res.mbts_adicional = m_mbts.group(1).strip().replace("\n", " | ")
        if ServicioAfectado.MBTS not in res.servicios:
            res.servicios.append(ServicioAfectado.MBTS)

    m_corp = re.search(r"\*AFECTACIÓN DE SERVICIOS CORPORATIVOS:\*([\s\S]*?)(?=\*ATIENDE|\*ACTUALIZACI|$)", bloque, re.IGNORECASE)
    if m_corp:
        res.corp_adicional = m_corp.group(1).strip().replace("\n", " | ")
        if ServicioAfectado.CORPORATIVO not in res.servicios:
            res.servicios.append(ServicioAfectado.CORPORATIVO)

    # 9. Construir Observaciones estructuradas para el generador de mensajes
    obs_lines = []
    if res.tipo == TipoIncidencia.FTTH:
        if res.planos_lista:
            planos_str = ", ".join(f"{p} ({res.clientes})" for p in res.planos_lista)
            obs_lines.append(f"Planos: {planos_str}")
        elif res.plano:
            obs_lines.append(f"Planos: {res.plano} ({res.clientes})")

        if res.etiqueta:
            obs_lines.append(f"ETIQUETA_FALLA: {res.etiqueta}")

        # Detalle de distrito
        tot = res.clientes_totales or res.clientes
        pct = res.porcentaje or (f"{round(res.clientes/tot*100, 2)}%" if tot > 0 else "0%")
        obs_lines.append(f"Detalle_Distritos: {res.distrito}: 1 nodos, {res.clientes} de {tot} ({pct})")

        if res.hfc_adicional:
            obs_lines.append(f"HFC_ADICIONAL: {res.hfc_adicional}")
        if res.mbts_adicional:
            obs_lines.append(f"MBTS_ADICIONAL: {res.mbts_adicional}")
        if res.corp_adicional:
            obs_lines.append(f"CORP_ADICIONAL: {res.corp_adicional}")

    else:
        # HFC
        if res.plano:
            obs_lines.append(f"Plano: {res.plano}")
        if res.equipo:
            obs_lines.append(f"Equipo: {res.equipo}")
        obs_lines.append(f"Clientes: {res.clientes}")

    # Agregar actualizaciones cronológicamente ordenadas (desde la más antigua a la más nueva)
    if res.actualizaciones:
        for act in reversed(res.actualizaciones):
            obs_lines.append(act)
    else:
        hora_der = res.hora_inicio.strftime("%H:%M") if res.hora_inicio else "00:00"
        obs_lines.append(f"[{hora_der}] Se deriva a BOSF {res.bosf} para su atención.")

    res.observaciones = "\n".join(obs_lines)
    return res
