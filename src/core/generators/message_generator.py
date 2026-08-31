"""Generador de mensajes de WhatsApp formateados para las incidencias."""

from __future__ import annotations

import re
from datetime import timedelta
from src.core.models import Incidencia, Plano, EstadoIncidencia, TipoIncidencia


def generate_whatsapp_message(
    incidencia: Incidencia,
    plano: Plano | None,
    bosf_telefono: str | None = None
) -> str:
    """
    Genera el mensaje de WhatsApp para incidencias individuales o masivas de Anillo/Troncal.
    """
    # Formatear fechas y horas de inicio
    fecha_str = incidencia.hora_inicio.strftime("%d/%m/%Y")
    hora_str = incidencia.hora_inicio.strftime("%H:%M")

    # Extraer campos geográficos del Plano (o fallback a incidencia)
    distrito = plano.distrito if plano else incidencia.distrito
    departamento = plano.departamento if plano else incidencia.departamento
    provincia = plano.provincia if plano else incidencia.provincia
    cmts_olt = plano.cmts_olt if plano else ""

    bosf_name = incidencia.bosf or "Pendiente"
    telefono_str = f"-{bosf_telefono}" if bosf_telefono else ""
    telefono_ind_str = f" -{bosf_telefono}" if bosf_telefono else ""
    inc_code = incidencia.inc or "EN PROCESO"

    # Determinar si es una Incidencia Masiva (2 o más planos / distritos agrupados)
    anillo_match = re.search(r"Anillo:\s*([^\n]+)", incidencia.observaciones)
    distritos_detalle_match = re.search(r"Detalle_Distritos:\s*([^\n]+)", incidencia.observaciones)
    planos_match = re.search(r"Planos:\s*([^\n]+)", incidencia.observaciones)
    
    es_masiva_hfc = False
    if incidencia.tipo == TipoIncidencia.HFC:
        if planos_match:
            planos_items = [p.strip() for p in planos_match.group(1).split(",") if p.strip()]
            if len(planos_items) >= 2:
                es_masiva_hfc = True
        if distritos_detalle_match and distritos_detalle_match.group(1).strip():
            es_masiva_hfc = True
        elif anillo_match and not anillo_match.group(1).strip().startswith("__SIN_ANILLO__"):
            es_masiva_hfc = True

    # Determinar si está cerrada
    is_closed = incidencia.estado == EstadoIncidencia.CERRADA

    # Parsear historia desde observaciones
    historia_lines = []
    for line in incidencia.observaciones.split('\n'):
        match = re.search(r"^\[(\d{2}:\d{2})h?\]\s*(.*)", line.strip())
        if match:
            hora_val = match.group(1)
            desc_val = match.group(2)
            # Limpiar prefijos ACTUALIZACION/CIERRE
            desc_val = re.sub(r"^(ACTUALIZACION|CIERRE):\s*", "", desc_val, flags=re.IGNORECASE)
            desc_val = desc_val.strip()
            historia_lines.append(f"*{hora_val}h {desc_val}")

    historia_lines.reverse()
    if not any("Se deriva a BOSF" in l for l in historia_lines):
        historia_lines.append(f"*{hora_str}h Se deriva a BOSF {bosf_name} para su atención.")

    history_block = "\n".join(historia_lines)

    hora_solucion_dt = incidencia.hora_inicio + timedelta(hours=4)
    fecha_solucion_str = hora_solucion_dt.strftime("%d/%m/%Y")
    hora_solucion_str = hora_solucion_dt.strftime("%H:%M")

    if is_closed:
        fecha_solucion_str = incidencia.ultima_actualizacion.strftime("%d/%m/%Y")
        hora_solucion_str = incidencia.ultima_actualizacion.strftime("%H:%M")

    fecha_impacto_str = incidencia.ultima_actualizacion.strftime("%d/%m/%Y")
    hora_impacto_str = incidencia.ultima_actualizacion.strftime("%H:%M")

    # =========================================================================
    # FORMATO 1: INCIDENCIA MASIVA HFC (AGRUPA 2 O MÁS PLANOS)
    # =========================================================================
    if es_masiva_hfc:
        tipo_falla_str = incidencia.tipo_falla or "Corte de Fibra"

        # Construir bloques de distritos
        bloques_distritos = []
        if distritos_detalle_match and distritos_detalle_match.group(1).strip():
            raw_dists = distritos_detalle_match.group(1).split(" | ")
            for d_info in raw_dists:
                d_parts = d_info.split(": ")
                d_name = d_parts[0].strip().upper()
                d_stat = d_parts[1].strip() if len(d_parts) > 1 else ""
                
                m_stat = re.search(r"(\d+)\s*nodos?,\s*(\d+)\s*de\s*(\d+)\s*\(([\d\.]+%?)\)", d_stat, re.IGNORECASE)
                if m_stat:
                    n_nodos = m_stat.group(1)
                    n_afectados = m_stat.group(2)
                    n_total = m_stat.group(3)
                    n_pct = m_stat.group(4)
                    if not n_pct.endswith("%"):
                        n_pct += "%"
                    bloques_distritos.append(
                        f"{d_name}\n*HFC ({n_nodos} NODOS): {n_afectados} clientes de {n_total}  ({n_pct})"
                    )
                else:
                    bloques_distritos.append(f"{d_name}\n*{d_stat}")
        else:
            bloques_distritos.append(f"{distrito.upper()}\n*Afectación general de servicios")

        distritos_texto = "\n \n".join(bloques_distritos)
        if is_closed:
            tipo_msg = "*FINAL / CIERRE*"
        elif len(historia_lines) > 1:
            tipo_msg = "*ACTUALIZACIÓN*"
        else:
            tipo_msg = "*INICIAL*"

        if is_closed:
            msg = (
                f"*NOC SERVICIOS FIJOS*\n"
                f"TIPO DE MENSAJE: {tipo_msg}\n"
                f"TICKET ASIGNADO: {inc_code}\n\n"
                f"*FALLA:*\n"
                f"{tipo_falla_str} en Departamento de {departamento.upper()} Prov. de {provincia.upper()} Distrito de {distrito.upper()} - {fecha_str} {hora_str} h\n\n"
                f"*IMPACTO ({fecha_impacto_str} {hora_impacto_str} h)*\n\n"
                f"*SIN AFECTACIÓN DE SERVICIOS*\n\n"
                f"*ATIENDE:*            \n"
                f"* BOSF {bosf_name}{telefono_str} con {inc_code}\n\n"
                f"*SOLUCIONADO:*\n"
                f"{fecha_impacto_str}\n"
                f"{history_block}\n\n"
                f"*HORA DE SOLUCIÓN :* {fecha_solucion_str} {hora_solucion_str}h"
            )
        else:
            msg = (
                f"*NOC SERVICIOS FIJOS*\n"
                f"TIPO DE MENSAJE: {tipo_msg}\n"
                f"TICKET ASIGNADO: {inc_code}\n\n"
                f"*FALLA:*\n"
                f"{tipo_falla_str} en Departamento de {departamento.upper()} Prov. de {provincia.upper()} Distrito de {distrito.upper()} - {fecha_str} {hora_str} h\n\n"
                f"*IMPACTO ({fecha_impacto_str} {hora_impacto_str} h)*\n\n"
                f"*AFECTACIÓN DE SERVICIOS FIJOS:*   \n"
                f"1. DEPARTAMENTO DE {departamento.upper()}, PROV. DE {provincia.upper()}\n"
                f"DISTRITO(S):\n"
                f"{distritos_texto}\n\n"
                f"*ATIENDE:*            \n"
                f"* BOSF {bosf_name}{telefono_str} con {inc_code}\n\n"
                f"*ACTUALIZACIÓN:*\n"
                f"{fecha_impacto_str}\n"
                f"{history_block}\n\n"
                f"*HORA DE SOLUCIÓN :* {fecha_solucion_str} {hora_solucion_str}h"
            )
        return msg

    # =========================================================================
    # FORMATO FTTH MASIVA (incidencias tipo FTTH con Planos: en observaciones)
    # =========================================================================
    if incidencia.tipo == TipoIncidencia.FTTH:
        tipo_falla_str = incidencia.tipo_falla or "Caida de OLT FTTH"

        # Plano principal (primer plano) para mostrarlo en la linea de falla
        plano_id_ftth = ""
        if planos_match:
            primer_p = planos_match.group(1).split(",")[0].strip()
            plano_id_ftth = re.split(r"\s*\(", primer_p)[0].strip()  # quita "(48)"

        # Linea de falla con plano entre parentesis
        plano_display = f" ({plano_id_ftth})" if plano_id_ftth else ""
        linea_falla = (
            f"{tipo_falla_str} en Departamento de {departamento.upper()}, "
            f"prov. de {provincia.upper()} Distrito de {distrito.upper()}"
            f"{plano_display} - {fecha_str} {hora_str} h"
        )

        # Causa raiz y correctivo (solo si están en observaciones)
        causa_raiz_m = re.search(r"CAUSA_RAIZ:\s*([^\n]+)", incidencia.observaciones)
        correctivo_m = re.search(r"CORRECTIVO:\s*([^\n]+)", incidencia.observaciones)
        lineas_causa = ""
        if causa_raiz_m:
            lineas_causa += f"\n*CAUSA RAIZ: {causa_raiz_m.group(1).upper()}*"
        if correctivo_m:
            lineas_causa += f"\n*CORRECTIVO: {correctivo_m.group(1)}*"

        # Bloque de impacto FTTH por distrito
        bloques_distrito_ftth = []
        if distritos_detalle_match and distritos_detalle_match.group(1).strip():
            raw_dists = distritos_detalle_match.group(1).split(" | ")
            for d_info in raw_dists:
                d_parts = d_info.split(": ")
                d_name = d_parts[0].strip().upper()
                d_stat = d_parts[1].strip() if len(d_parts) > 1 else ""
                m_stat = re.search(
                    r"(\d+)\s*nodos?,\s*(\d+)\s*de\s*(\d+)\s*\(([\d.]+%?)\)",
                    d_stat, re.IGNORECASE
                )
                if m_stat:
                    af = m_stat.group(2)
                    tot = m_stat.group(3)
                    pct = m_stat.group(4)
                    if not pct.endswith("%"):
                        pct += "%"
                    bloques_distrito_ftth.append(
                        f"DISTRITO: {d_name}\n*FTTH: {af} clientes de {tot} ({pct})"
                    )
                else:
                    bloques_distrito_ftth.append(f"DISTRITO: {d_name}\n*{d_stat}")
        else:
            # fallback: usar clientes totales de observaciones
            clientes_m = re.search(r"Clientes:\s*(\d+)", incidencia.observaciones)
            clientes_val = clientes_m.group(1) if clientes_m else "?"
            bloques_distrito_ftth.append(f"DISTRITO: {distrito.upper()}\n*FTTH: {clientes_val} clientes")

        distritos_ftth_texto = "\n \n".join(bloques_distrito_ftth)

        if is_closed:
            tipo_msg = "*FINAL / CIERRE*"
            cuerpo_actualizacion = (
                f"*SOLUCIONADO:*\n"
                f"{fecha_impacto_str}\n"
                f"{history_block}"
            )
        elif len(historia_lines) > 1:
            tipo_msg = "*ACTUALIZACION*"
            cuerpo_actualizacion = (
                f"*ACTUALIZACION:*\n"
                f"{fecha_impacto_str}\n"
                f"{history_block}"
            )
        else:
            tipo_msg = "*INICIAL*"
            cuerpo_actualizacion = (
                f"*ACTUALIZACION:*\n"
                f"{fecha_impacto_str}\n"
                f"{history_block}"
            )

        impacto_block = "*SIN AFECTACION DE SERVICIOS*" if is_closed else (
            f"*AFECTACION DE SERVICIOS FIJOS:*   \n"
            f"1. DEPARTAMENTO DE {departamento.upper()}, PROV. DE {provincia.upper()}\n"
            f"{distritos_ftth_texto}"
        )

        msg = (
            f"*NOC SERVICIOS FIJOS*\n"
            f"TIPO DE MENSAJE: {tipo_msg}\n"
            f"TICKET ASIGNADO: {inc_code}\n\n"
            f"*FALLA:*\n"
            f"{linea_falla}{lineas_causa}\n\n"
            f"*IMPACTO ({fecha_impacto_str} {hora_impacto_str} h)*\n\n"
            f"{impacto_block}\n\n"
            f"*ATIENDE:*            \n"
            f"* BOSF {bosf_name}{telefono_str} con {inc_code}\n\n"
            f"{cuerpo_actualizacion}\n\n"
            f"*HORA DE SOLUCION :* {fecha_solucion_str} {hora_solucion_str}h"
        )
        return msg


    clientes_match = re.search(r"Clientes:\s*(\d+)", incidencia.observaciones)
    clientes = int(clientes_match.group(1)) if clientes_match else 0

    plano_id = plano.plano if plano else ""
    if not plano_id:
        plano_match = re.search(r"Plano:\s*(\S+)", incidencia.observaciones)
        plano_id = plano_match.group(1) if plano_match else incidencia.id

    equipo_match = re.search(r"Equipo:\s*([^\n]+)", incidencia.observaciones)
    equipo_val = cmts_olt or (equipo_match.group(1).strip() if equipo_match else "")
    nodo_display = f"{plano_id}_{equipo_val.upper()}" if equipo_val else plano_id
    tec_str = incidencia.tipo.value if hasattr(incidencia.tipo, "value") else str(incidencia.tipo)

    # Ubicación limpia para individual
    if distrito and departamento and distrito.upper() != departamento.upper():
        ubicacion_falla = f"{distrito.upper()} - {departamento.upper()}"
    else:
        ubicacion_falla = (departamento or distrito or "").upper()

    ubicacion_impacto = (distrito or departamento or "").upper()
    nombre_falla = f"Caída de nodo {tec_str} {plano_id}" if plano_id else f"Incidencia {tec_str}"

    if is_closed:
        msg = (
            f"*NOC - SERVICIOS FIJOS*\n\n"
            f"FALLA: {nombre_falla} en {ubicacion_falla} {fecha_str} {hora_str} h\n\n"
            f"*IMPACTO:* \n"
            f"*SIN AFECTACIÓN DE SERVICIOS*\n"
            f"*Atiende BOSF {bosf_name}{telefono_ind_str} con {inc_code}  \n\n"
            f"*SOLUCIONADO:* \n"
            f"{fecha_solucion_str}\n"
            f"{history_block}\n\n"
            f"*HORA DE SOLUCIÓN:* {fecha_solucion_str} {hora_solucion_str}h"
        )
    else:
        msg = (
            f"*NOC - SERVICIOS FIJOS*\n\n"
            f"FALLA: {nombre_falla} en {ubicacion_falla} {fecha_str} {hora_str} h\n\n"
            f"*IMPACTO:* \n"
            f"*Afectación de {clientes} Clientes {tec_str} en {ubicacion_impacto} (Por caída de nodo: {nodo_display})\n"
            f"*Atiende BOSF {bosf_name}{telefono_ind_str} con {inc_code}  \n\n"
            f"*ACTUALIZACION :* \n"
            f"{fecha_str}\n"
            f"{history_block}\n\n"
            f"*HORA DE SOLUCIÓN:* {fecha_solucion_str} {hora_solucion_str}h"
        )

    return msg
