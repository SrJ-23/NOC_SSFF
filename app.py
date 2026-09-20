# app.py
import os
import time

# Configurar zona horaria de Perú a nivel de entorno/OS
os.environ["TZ"] = "America/Lima"
if hasattr(time, "tzset"):
    time.tzset()

import uuid
from flask import Flask, render_template, request, redirect, url_for, flash
import datetime
import json
import re
from dataclasses import replace

# Inyección de dependencias usando tu arquitectura limpia
from src.data.sheets_client import SQLiteSheetsClient
from src.repositories.incidencias_repository import IncidenciasRepository
from src.repositories.planos_repository import PlanosRepository
from src.repositories.personal_repository import PersonalRepository
from src.services.incidencia_service import IncidenciaService
from src.core.models import TipoIncidencia, ServicioAfectado, EstadoIncidencia, Incidencia
from src.core.parsers.hfc_parser import parse_hfc_text
from src.core.parsers.ftth_parser import parse_ftth_excel, parse_ftth_text
from src.core.parsers.previous_shift_parser import separar_bloques_averias, parsear_bloque_averia
from src.core.generators.message_generator import generate_whatsapp_message
from src.utils.time_utils import calcular_semaforo, formatear_duracion, now_peru

app = Flask(__name__)
app.secret_key = "noc_fixed_services_secure_session_key"

# Instanciación de componentes
db_client = SQLiteSheetsClient()
incidencias_repo = IncidenciasRepository(db_client)
incidencia_service = IncidenciaService(incidencias_repo)
personal_repo = PersonalRepository(db_client)
planos_repo = PlanosRepository()  # Carga parquets automáticamente desde DataManager

TOP_UPDATES_TEMPLATE = [
    "Se deriva a BOSF {bosf} para su atención.",
    "PEXT en ruta demora por tráfico.",
    "Personal en desplazamiento al plano. Tiempo de llegada [X] m.",
    "Técnico informa que se encuentra en camino hacia el plano. Tiempo de llegada [X]m.",
    "PEXT informa que se encuentran en POP realizando mediciones.",
    "PEXT informa que se encuentran en plano realizando mediciones.",
    "PEXT informa que se inician fusiones de fibra óptica.",
    "PEXT informa que se continuan fusiones de fibra óptica.",
    "PEXT informa que recuperó reserva para realizar un sólo punto de empalme, inicia fusiones.",
    "OYM informa que se encuentran en camino. Tiempo de llegada [X]h.",
    "Se verifica que han reestablecido [X] clientes. Se actualiza impacto."
]

TOP_CLOSURES = [
    "Se valida restablecimiento de servicios. Se cierra notificación.",
    "Se valida retorno de energía comercial. Se restablecen servicios. Se cierra notificación.",
    "Se finaliza fusiones de FO. Se verifica servicios restablecidos. Se cierra notificacion.",
    "Se instala GGEE, Se verifica servicios restablecidos. Se cierra notificacion.",
    "Personal realiza mantenimiento en equipos de AA. Temperatura se reestablece en valores normales.",
    "Se retorna energia comercial. Se normaliza temperaturas.",
    "Retorna energia comercial. Se verifica servicios restablecidos. Se cierra notificacion."
]

FTTH_CAUSAS_RAIZ = [
    "Corte por terceros",
    "Corte por maquinaria pesada",
    "Corte por vandalismo",
    "Corte por corto circuito",
    "Corte por poda de arboles",
    "Corte por trabajo de empresa electrica",
    "Corte por paso de camion",
]

FTTH_CORRECTIVOS = [
    "Se recupero reserva y se realizo un solo punto de empalme.",
    "Cambio de seccion de cable de F.O., realizando 2 puntos de empalme.",
    "Se instalo mufa.",
    "Se tendio nuevo cable de F.O.",
    "Migracion de hilos.",
    "Fusion de hilos rotos dentro de mufa.",
]

TOP_UPDATES_FTTH = [
    "BOSF deriva a PEXT para la atencion.",
    "PEXT informa que se encuentran en desplazamiento hacia el POP [X] para las mediciones. Tiempo de llegada 30 min.",
    "PEXT informa que se encuentran en desplazamiento hacia el SITE [X] para las mediciones. Tiempo de llegada 1h 30 min.",
    "PEXT informa que se encuentran en desplazamiento para retiro de llaves del POP [X] para las mediciones. Tiempo de llegada 30 min.",
    "PEXT informa que se encuentran en desplazamiento a la zona de averia para realizar mediciones. Tiempo de llegada 1h.",
    "PEXT informa que detecta corte a [X]km desde el POP [X] hacia el tramo de fo.",
    "PEXT informa que detecta corte a [X]km desde el SITE [X] hacia el tramo de fo.",
    "PEXT informa que realiza mediciones en mufa cercana y detecta corte a [X]km desde la mufa hacia el tramo de fo.",
    "PEXT informa que se encuentra en la zona de averia ubicando punto de corte.",
    "PEXT informa que se ubica punto de averia, corte por [X]. Se encuentran evaluando correctivos a realizar.",
    "PEXT informa que se encuentra recuperando reserva para realizar un solo punto de empalme.",
    "PEXT informa que se esta realizando tendido de [X] metros de fo para realizar 2 puntos de empalme.",
    "PEXT informa que se inician fusiones de fibra optica.",
    "PEXT informa que se inician fusiones de fibra optica. Se observa el restablecimiento de [X] Clientes FTTH. Se actualiza impacto.",
    "Se observa el restablecimiento de [X] Clientes FTTH. PEXT finaliza fusiones de fibra optica. Se procede al cierre de la notificacion.",
]

def _parse_hora_averia(hora_str: str, fecha_str: str = "", arrived_on_str: str = "") -> datetime.datetime:
    """
    Convierte hora_str (HH:MM o fecha completa) a datetime en hora Perú.
    Toma la fecha de referencia en orden de prioridad:
    1. Si hora_str incluye fecha completa.
    2. fecha_str si se proporciona (YYYY-MM-DD o DD/MM/YYYY).
    3. arrived_on_str si contiene fecha.
    4. Fallback: now_peru().
    """
    from src.core.parsers.ftth_parser import _parse_flexible_datetime

    # 1. Si hora_str viene con fecha completa
    dt_full = _parse_flexible_datetime(hora_str)
    if dt_full and re.search(r"\d{1,2}:\d{2}", str(hora_str)):
        return dt_full

    # 2. Extraer hora y minuto de hora_str
    h, m = 0, 0
    m_time = re.search(r"(\d{1,2}):(\d{2})", str(hora_str))
    if m_time:
        h = int(m_time.group(1))
        m = int(m_time.group(2))
    elif not hora_str:
        now = now_peru()
        h, m = now.hour, now.minute

    # 3. Extraer fecha base de fecha_str o arrived_on_str
    base_dt = None
    if fecha_str:
        base_dt = _parse_flexible_datetime(fecha_str)
    if not base_dt and arrived_on_str:
        primera_parte = arrived_on_str.split(" a ")[0].strip()
        base_dt = _parse_flexible_datetime(primera_parte)

    if base_dt:
        return base_dt.replace(hour=h, minute=m, second=0, microsecond=0)

    now = now_peru()
    return now.replace(hour=h, minute=m, second=0, microsecond=0)

def _extraer_mapa_nodos_hfc(incidencia) -> list[dict]:
    """Extrae la lista estructurada de nodos {plano, equipo, clientes, inc} de una masiva HFC."""
    m_json = re.search(r"NODOS_MASIVA_JSON:\s*(\[[^\n]+\])", incidencia.observaciones)
    if m_json:
        try:
            return json.loads(m_json.group(1))
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback para incidencias preexistentes o individuales
    planos = _extraer_planos_de_incidencia(incidencia)
    mapa = []
    for p in planos:
        m_cli = re.search(rf"\b{re.escape(p)}\s*\((\d+)\)", incidencia.observaciones, re.IGNORECASE)
        cli = int(m_cli.group(1)) if m_cli else 0
        mapa.append({
            "plano": p,
            "equipo": "",
            "clientes": cli,
            "inc": incidencia.inc or ""
        })
    return mapa


def _extraer_planos_de_incidencia(incidencia) -> list[str]:
    """Extrae la lista de todos los códigos de planos contenidos en una incidencia (individual o masiva)."""
    # 0. Si cuenta con mapa JSON estructurado
    m_json = re.search(r"NODOS_MASIVA_JSON:\s*(\[[^\n]+\])", incidencia.observaciones)
    if m_json:
        try:
            nodos = json.loads(m_json.group(1))
            planos_from_json = [str(n.get("plano", "")).strip().upper() for n in nodos if n.get("plano")]
            if planos_from_json:
                return list(dict.fromkeys(planos_from_json))
        except (json.JSONDecodeError, TypeError):
            pass

    planos = []
    # 1. Caso masiva: Planos: AYCA001 (48), AYCA003 (55), ...
    planos_match = re.search(r"Planos:\s*([^\n]+)", incidencia.observaciones, re.IGNORECASE)
    if planos_match:
        for part in planos_match.group(1).split(","):
            part = part.strip()
            m = re.search(r"^([A-Za-z0-9_\-]+)", part)
            if m:
                planos.append(m.group(1).upper())
    # 2. Caso individual: Plano: AYCA001
    plano_match = re.search(r"Plano:\s*([A-Za-z0-9_\-]+)", incidencia.observaciones, re.IGNORECASE)
    if plano_match:
        planos.append(plano_match.group(1).upper())
    return list(dict.fromkeys(planos))


def _extraer_onts_registradas_ftth(incidencia, plano_upper: str) -> int:
    """
    Extrae el número de ONTs registradas para un plano FTTH específico
    desde la línea 'Planos:' de las observaciones.
    Ej: 'Planos: PISH010-F (42), PISH011-F (15)' → para PISH010-F devuelve 42.
    """
    planos_match = re.search(r"Planos:\s*([^\n]+)", incidencia.observaciones, re.IGNORECASE)
    if not planos_match:
        # Fallback: leer el total de Clientes: si solo hay un plano
        m = re.search(r"Clientes:\s*(\d+)", incidencia.observaciones)
        return int(m.group(1)) if m else 0
    for part in planos_match.group(1).split(","):
        part = part.strip()
        m = re.match(r"([A-Za-z0-9_\-]+)\s*\((\d+)\)", part)
        if m and m.group(1).upper() == plano_upper:
            return int(m.group(2))
    return 0


def _inferir_olt_de_plano(plano: str, olts: list[str]) -> str:
    """
    Para archivos con múltiples OLTs, intenta inferir cuál corresponde al plano
    buscando el prefijo geográfico del plano en el nombre de la OLT.
    Fallback: devuelve la primera OLT disponible.
    """
    if not olts:
        return ""
    if len(olts) == 1:
        return olts[0]
    # Heurístico: primeros 4-6 caracteres del plano vs nombre de OLT
    prefix = re.sub(r"\d+.*$", "", plano).lower()  # ej: "pish" de "PISH010-F"
    for olt in olts:
        if prefix in olt.lower():
            return olt
    return olts[0]



def _obtener_plano_y_clientes(incidencia) -> tuple[str, int]:
    planos = _extraer_planos_de_incidencia(incidencia)
    clientes_match = re.search(r"Clientes:\s*(\d+)", incidencia.observaciones)
    clientes_count = int(clientes_match.group(1)) if clientes_match else 0
    plano_name = planos[0] if planos else ""
    return plano_name, clientes_count

@app.route("/ping")
@app.route("/health")
def health_check():
    """Endpoint ultra-liviano para keep-alive / cron-job (evita sobrecarga y límites de respuesta)."""
    return "OK", 200, {"Content-Type": "text/plain"}


@app.route("/")
def dashboard():
    """Muestra la lista de incidencias (Averías Pendientes) y modales de carga"""
    incidencias = incidencias_repo.listar_todos()
    
    activas = []
    cerradas = []
    activas_hfc_list = []
    
    for inc in incidencias:
        minutos_sin_actualizar = inc.minutos_desde_ultima_actualizacion
        is_closed = inc.estado == EstadoIncidencia.CERRADA
        
        p_name, _ = _obtener_plano_y_clientes(inc)
        if not is_closed and inc.tipo == TipoIncidencia.HFC:
            nodos_map = _extraer_mapa_nodos_hfc(inc)
            for nodo_item in nodos_map:
                activas_hfc_list.append({
                    "id": inc.id,
                    "inc": inc.inc,
                    "inc_nodo": nodo_item.get("inc") or inc.inc,
                    "plano": nodo_item.get("plano", ""),
                    "clientes": nodo_item.get("clientes", 0),
                    "distrito": inc.distrito,
                    "departamento": inc.departamento,
                    "es_masiva": len(nodos_map) > 1
                })
            if not nodos_map:
                activas_hfc_list.append({
                    "id": inc.id,
                    "inc": inc.inc,
                    "inc_nodo": inc.inc,
                    "plano": "",
                    "distrito": inc.distrito,
                    "departamento": inc.departamento,
                    "es_masiva": False
                })
        planos_inc = _extraer_planos_de_incidencia(inc)
        planos_str = ", ".join(planos_inc) if planos_inc else (p_name or "")
        
        # Extraer OLT / Troncal o Anillo
        olt_troncal = ""
        m_eti = re.search(r"ETIQUETA_FALLA:\s*([^\n]+)", inc.observaciones)
        if m_eti:
            olt_troncal = m_eti.group(1).strip()
        else:
            m_olt = re.search(r"OLT:\s*([^\n]+)", inc.observaciones, re.IGNORECASE)
            if m_olt:
                olt_troncal = m_olt.group(1).strip()
            else:
                m_anillo = re.search(r"Anillo\s*(\d+)", inc.observaciones, re.IGNORECASE)
                if m_anillo:
                    olt_troncal = f"Anillo {m_anillo.group(1)}"
                else:
                    m_cmts = re.search(r"CMTS:\s*([^\n]+)", inc.observaciones, re.IGNORECASE)
                    if m_cmts:
                        olt_troncal = m_cmts.group(1).strip()

        inc_dto = {
            "obj": inc,
            "semaforo": calcular_semaforo(minutos_sin_actualizar, is_closed=is_closed).value,
            "duracion_inicio": formatear_duracion(inc.minutos_desde_inicio),
            "duracion_actualizacion": formatear_duracion(minutos_sin_actualizar),
            "servicios_str": ", ".join(s.value for s in inc.servicios) or "—",
            "planos_list": planos_inc,
            "planos_str": planos_str,
            "planos_count": len(planos_inc),
            "olt_troncal": olt_troncal,
            "tipo_tag": inc.tipo.value if hasattr(inc.tipo, "value") else str(inc.tipo)
        }
        
        if is_closed:
            cerradas.append(inc_dto)
        else:
            activas.append(inc_dto)
            
    # Ordenar activas por criticidad
    activas_ordenadas = sorted(activas, key=lambda i: i["obj"].minutos_desde_ultima_actualizacion, reverse=True)
    
    personal_activos = personal_repo.listar_activos()
    hora_actual = now_peru().strftime("%H:%M")
    
    # ID de incidencia recién creada en FTTH para completar datos si aplica
    completar_id = request.args.get("completar_id")
    inc_completar = incidencias_repo.obtener_por_id(completar_id) if completar_id else None
    
    import json
    return render_template(
        "dashboard.html",
        incidencias=activas_ordenadas,
        activas_hfc_json=json.dumps(activas_hfc_list),
        personal_list=personal_activos,
        hora_actual=hora_actual,
        inc_completar=inc_completar,
        tipos_incidencia=[t.value for t in TipoIncidencia],
        servicios=[s.value for s in ServicioAfectado]
    )


@app.route("/historica")
def historica():
    """Página de consulta histórica de averías cerradas con filtro de fechas"""
    fecha_desde = request.args.get("fecha_desde", "").strip()
    fecha_hasta = request.args.get("fecha_hasta", "").strip()
    
    cerradas_raw = incidencias_repo.listar_cerradas()
    cerradas_dto = []
    
    for inc in cerradas_raw:
        dt_cierre = inc.ultima_actualizacion
        fecha_inc_str = dt_cierre.strftime("%Y-%m-%d")
        
        # Filtro de fecha desde
        if fecha_desde and fecha_inc_str < fecha_desde:
            continue
        # Filtro de fecha hasta
        if fecha_hasta and fecha_inc_str > fecha_hasta:
            continue
            
        p_name, _ = _obtener_plano_y_clientes(inc)
        cerradas_dto.append({
            "obj": inc,
            "plano": p_name,
            "duracion_total": formatear_duracion((inc.ultima_actualizacion - inc.hora_inicio).total_seconds() / 60),
            "servicios_str": ", ".join(s.value for s in inc.servicios) or "—",
            "fecha_cierre": inc.ultima_actualizacion.strftime("%d/%m/%Y"),
            "hora_cierre": inc.ultima_actualizacion.strftime("%H:%M"),
            "hora_inicio": inc.hora_inicio.strftime("%d/%m/%Y %H:%M"),
        })
        
    cerradas_ordenadas = sorted(cerradas_dto, key=lambda i: i["obj"].ultima_actualizacion, reverse=True)
    
    return render_template(
        "historica.html",
        cerradas=cerradas_ordenadas,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        total_cerradas=len(cerradas_ordenadas)
    )


@app.route("/eliminar-incidencia/<id_>", methods=["POST"])
def eliminar_incidencia(id_):
    """Elimina una incidencia tras confirmación del usuario"""
    inc = incidencias_repo.obtener_por_id(id_)
    if inc:
        inc_label = inc.inc if inc.inc and inc.inc != "EN PROCESO" else id_
        incidencias_repo.eliminar(id_)
        flash(f"Incidencia {inc_label} eliminada correctamente.", "success")
    else:
        flash("Incidencia no encontrada.", "danger")
    return redirect(url_for("dashboard"))


@app.route("/nueva-averia", methods=["GET", "POST"])
def nueva_averia():
    """Formulario para registro manual de incidencias"""
    if request.method == "POST":
        inc = request.form.get("inc", "").strip()
        tipo = request.form.get("tipo")
        tipo_falla = request.form.get("tipo_falla")
        bosf = request.form.get("bosf", "").strip()
        departamento = request.form.get("departamento", "").strip()
        provincia = request.form.get("provincia", "").strip()
        distrito = request.form.get("distrito", "").strip()
        pext = request.form.get("pext", "").strip()
        servicios_sel = request.form.getlist("servicios")
        observaciones = request.form.get("observaciones", "").strip()
        hora_averia_str = request.form.get("hora_averia", "").strip()
        dt_inicio = _parse_hora_averia(hora_averia_str)
        
        if not inc or not departamento or not provincia or not distrito or not servicios_sel:
            flash("Todos los campos marcados con (*) son obligatorios.", "danger")
            return redirect(url_for("dashboard"))
            
        incidencia_service.crear(
            inc=inc,
            tipo=TipoIncidencia(tipo),
            tipo_falla=tipo_falla,
            departamento=departamento,
            provincia=provincia,
            distrito=distrito,
            bosf=bosf,
            pext=pext,
            servicios=tuple(ServicioAfectado(s) for s in servicios_sel),
            observaciones=observaciones,
            hora_inicio=dt_inicio,
        )
        flash(f"Incidencia {inc} creada exitosamente.", "success")
        return redirect(url_for("dashboard"))
        
    return render_template(
        "nueva_averia.html",
        tipos_incidencia=[t.value for t in TipoIncidencia],
        servicios=[s.value for s in ServicioAfectado]
    )


BOSF_OFICIALES = [
    "Cristhian Torres",
    "Lila Trujillo",
    "Miguel Barja",
    "Jesús Carrasco"
]

@app.route("/api/analizar-hfc", methods=["POST"])
def api_analizar_hfc():
    """Analiza registros de Grafana para detectar anillos/troncales separados, con
    estadísticas distritales por cada grupo, y estadísticas globales combinadas."""
    data = request.get_json(silent=True) or {}
    rows = data.get("rows", [])
    if not rows:
        raw_text = data.get("raw_text", "")
        if raw_text:
            reg_objs = parse_hfc_text(raw_text)
            rows = [{"plano": r.plano, "equipo": r.equipo, "clientes": r.clientes, "inc": r.inc} for r in reg_objs]

    # Regla HFC: en la columna de INCIDENT_ID sí o sí debe iniciar con INC
    rows = [r for r in rows if str(r.get("inc", "")).strip().upper().startswith("INC")]

    grupos = planos_repo.obtener_grupos_anillo(rows)
    for g in grupos:
        primer_inc_g = "EN PROCESO"
        for r in g["nodos"]:
            if r.get("inc") and r["inc"] != "EN PROCESO":
                primer_inc_g = r["inc"]
                break
        g["primer_inc"] = primer_inc_g

    meta = planos_repo.obtener_metadatos_anillos(rows)
    
    # Obtener primer INC disponible
    primer_inc = "EN PROCESO"
    for r in rows:
        if r.get("inc") and r.get("inc") != "EN PROCESO":
            primer_inc = r.get("inc")
            break
            
    total_afectados = sum(int(r.get("clientes", 0) or 0) for r in rows)
    planos_str = ", ".join(f"{r.get('plano')} ({r.get('clientes')})" for r in rows)
    
    # Formatear detalle distrital
    detalle_dists = []
    for d_name, d_val in meta["distritos_stats"].items():
        detalle_dists.append(f"{d_name}: {d_val['nodos']} nodos, {d_val['afectados']} de {d_val['total_distrito']} ({d_val['porcentaje']}%)")
        
    return {
        "grupos": grupos,
        "anillos": meta["anillos"],
        "anillo_str": meta["anillo_str"] or "Anillo Principal",
        "cmts_str": meta["cmts_str"],
        "departamento": meta["departamento"],
        "provincia": meta["provincia"],
        "distritos_str": meta["distritos_str"],
        "distritos_stats": meta["distritos_stats"],
        "detalle_distritos": " | ".join(detalle_dists),
        "primer_inc": primer_inc,
        "total_afectados": total_afectados,
        "planos_str": planos_str,
        "total_nodos": len(rows)
    }

def _crear_incidencias_individuales(planos, equipos, incs, clientes_list, bosfs, horas, hfc_activas):
    """
    Crea una Incidencia HFC individual por cada plano recibido (usado tanto por el
    Registro Individual por Nodo como por los nodos EXCLUIDOS de una Incidencia Masiva).
    Devuelve la lista de incidencias creadas.
    """
    creadas = []
    for i in range(len(planos)):
        p_name = planos[i].strip()
        if not p_name:
            continue
        eq_name = equipos[i].strip() if i < len(equipos) else ""
        inc_code = incs[i].strip() if i < len(incs) and incs[i].strip() else ""
        if not inc_code.upper().startswith("INC"):
            continue

        # Validar que no exista ya activa para evitar duplicaciones
        p_up = p_name.upper()
        existente = next((
            a for a in hfc_activas 
            if a.inc == inc_code 
            or p_up in _extraer_planos_de_incidencia(a)
        ), None)
        if existente:
            continue

        try:
            cnt_clientes = int(clientes_list[i]) if i < len(clientes_list) else 0
        except ValueError:
            cnt_clientes = 0

        bosf_val = bosfs[i].strip() if i < len(bosfs) else ""
        hora_val = horas[i].strip() if i < len(horas) else ""
        dt_inicio = _parse_hora_averia(hora_val)

        pl = planos_repo.obtener_por_id(p_name)
        dept = pl.departamento if pl else "DESCONOCIDO"
        prov = pl.provincia if pl else "DESCONOCIDO"
        dist = pl.distrito if pl else "DESCONOCIDO"

        obs = f"Plano: {p_name}\nClientes: {cnt_clientes}\nEquipo: {eq_name}"
        if bosf_val:
            obs += f"\n[{dt_inicio.strftime('%H:%M')}h] Se deriva a BOSF {bosf_val} para su atención."

        nueva = incidencia_service.crear(
            inc=inc_code,
            tipo=TipoIncidencia.HFC,
            tipo_falla="FALLA DE EQUIPO",
            departamento=dept,
            provincia=prov,
            distrito=dist,
            bosf=bosf_val,
            pext="",
            servicios=(ServicioAfectado.HFC,),
            observaciones=obs,
            hora_inicio=dt_inicio,
        )
        creadas.append(nueva)
    return creadas


@app.route("/carga-hfc", methods=["POST"])
def carga_hfc():
    """Soporte para pegado masivo desde Grafana con detección y asignación de BOSF / HORA y agrupación por Anillo"""
    incidencias_activas = incidencias_repo.listar_activas()
    hfc_activas = [i for i in incidencias_activas if i.tipo == TipoIncidencia.HFC]
    
    # Recoger todos los planos presentes en el reporte actual (para detectar desapariciones)
    planos_en_reporte = set()
    raw_text = request.form.get("grafana_paste", "").strip()
    if raw_text:
        reg_raw = parse_hfc_text(raw_text)
        planos_en_reporte.update(r.plano for r in reg_raw)

    # -------------------------------------------------------------
    # CASO A: Registro agrupado en 1 o varias Incidencias Masivas de Anillo,
    # más (opcionalmente) nodos EXCLUIDOS que se registran individualmente.
    # -------------------------------------------------------------
    if request.form.get("es_masiva_anillo") == "1":
        grupos_creados = 0
        primer_anillo_str = ""

        grupos_json = request.form.get("grupos_json", "").strip()
        if grupos_json:
            try:
                grupos = json.loads(grupos_json)
            except (json.JSONDecodeError, TypeError):
                grupos = []
        else:
            # Compatibilidad con el envío antiguo de un solo grupo
            grupos = [{
                "inc_principal": request.form.get("inc_principal", ""),
                "tipo_falla": request.form.get("tipo_falla", ""),
                "bosf": request.form.get("bosf_principal", ""),
                "hora": request.form.get("hora_principal", ""),
                "anillo_str": request.form.get("anillo_str", ""),
                "distritos_str": request.form.get("distritos_str", ""),
                "detalle_distritos": request.form.get("detalle_distritos", ""),
                "planos_str": request.form.get("planos_str", ""),
                "total_afectados": request.form.get("total_afectados", 0),
            }]

        for grupo in grupos:
            planos_str = (grupo.get("planos_str") or "").strip()
            if not planos_str:
                continue

            # Evitar crear masiva duplicada si todos sus planos ya están activos
            planos_grupo = [p.split("(")[0].strip().upper() for p in planos_str.split(",") if p.strip()]
            planos_ya_activos = set()
            for a in hfc_activas:
                planos_ya_activos.update(_extraer_planos_de_incidencia(a))

            if planos_grupo and all(p in planos_ya_activos for p in planos_grupo):
                continue

            inc_principal = (grupo.get("inc_principal") or "").strip() or "EN PROCESO"
            tipo_falla = (grupo.get("tipo_falla") or "").strip() or "Corte de Fibra"
            bosf_val = (grupo.get("bosf") or "").strip()
            hora_val = (grupo.get("hora") or "").strip()
            dt_inicio = _parse_hora_averia(hora_val)

            anillo_str = (grupo.get("anillo_str") or "").strip() or "Anillo Principal"
            distritos_str = (grupo.get("distritos_str") or "").strip() or "LIMA"
            detalle_distritos = (grupo.get("detalle_distritos") or "").strip()
            try:
                total_afectados = int(grupo.get("total_afectados") or 0)
            except (TypeError, ValueError):
                total_afectados = 0

            # Extraer departamento y provincia del primer plano
            primer_plano = planos_str.split(",")[0].split("(")[0].strip() if planos_str else ""
            pl_obj = planos_repo.obtener_por_id(primer_plano) if primer_plano else None
            dept = pl_obj.departamento if pl_obj else "LIMA"
            prov = pl_obj.provincia if pl_obj else "LIMA"

            nodos_lista = grupo.get("nodos") or []
            if not nodos_lista:
                for p in planos_grupo:
                    nodos_lista.append({
                        "plano": p,
                        "equipo": "",
                        "clientes": 0,
                        "inc": inc_principal
                    })
            nodos_json_str = json.dumps(nodos_lista)

            obs = (
                f"Anillo: {anillo_str}\n"
                f"Planos: {planos_str}\n"
                f"Clientes: {total_afectados}\n"
                f"Detalle_Distritos: {detalle_distritos}\n"
                f"NODOS_MASIVA_JSON: {nodos_json_str}\n"
                f"[{dt_inicio.strftime('%H:%M')}h] Se deriva a BOSF {bosf_val or 'Pendiente'} para su atención."
            )

            incidencia_service.crear(
                inc=inc_principal,
                tipo=TipoIncidencia.HFC,
                tipo_falla=tipo_falla,
                departamento=dept,
                provincia=prov,
                distrito=distritos_str,
                bosf=bosf_val,
                pext="",
                servicios=(ServicioAfectado.HFC,),
                observaciones=obs,
                hora_inicio=dt_inicio,
            )
            grupos_creados += 1
            if not primer_anillo_str:
                primer_anillo_str = anillo_str

        # Nodos EXCLUIDOS de la(s) masiva(s): se registran como incidencias individuales
        creadas_individuales = []
        if "plano_row[]" in request.form:
            planos = request.form.getlist("plano_row[]")
            equipos = request.form.getlist("equipo_row[]")
            incs = request.form.getlist("inc_row[]")
            clientes_list = request.form.getlist("clientes_row[]")
            bosfs = request.form.getlist("bosf_row[]")
            horas = request.form.getlist("hora_row[]")

            creadas_individuales = _crear_incidencias_individuales(
                planos, equipos, incs, clientes_list, bosfs, horas, hfc_activas
            )

        # Detectar averías que estaban activas y ya no figuran en el reporte de Grafana
        planos_en_reporte_up = {p.upper() for p in planos_en_reporte}
        # Construir lista de rows de grafana para calcular impacto nuevo en restauraciones
        grafana_rows_raw = [
            {"plano": r.plano, "clientes": r.clientes}
            for r in (parse_hfc_text(raw_text) if raw_text else [])
        ]
        cierres_completos, restauraciones_parciales = _separar_cierres_y_restauraciones(
            hfc_activas, planos_en_reporte_up, grafana_rows_raw
        )

        total_creadas = grupos_creados + len(creadas_individuales)
        if restauraciones_parciales:
            return render_template(
                "restauracion_parcial.html",
                restauraciones=restauraciones_parciales,
                cierres_completos=cierres_completos,
                creadas_count=total_creadas,
                top_closures=TOP_CLOSURES
            )
        if cierres_completos:
            return render_template("cierre_masivo.html", desaparecidas=cierres_completos, creadas_count=total_creadas, top_closures=TOP_CLOSURES)

        if grupos_creados == 0:
            flash("No se pudo crear ninguna Incidencia Masiva: no se recibieron nodos agrupados.", "warning")
        elif grupos_creados == 1:
            msg = f"Incidencia Masiva ({primer_anillo_str}) creada exitosamente."
            if creadas_individuales:
                msg += f" Además se registraron {len(creadas_individuales)} incidencia(s) individual(es) para los nodos excluidos."
            flash(msg, "success")
        else:
            msg = f"Se crearon {grupos_creados} Incidencias Masivas separadas por anillo."
            if creadas_individuales:
                msg += f" Además se registraron {len(creadas_individuales)} incidencia(s) individual(es) para los nodos excluidos."
            flash(msg, "success")
        return redirect(url_for("dashboard"))
        
    # -------------------------------------------------------------
    # CASO B: Registro individual por cada plano / nodo
    # -------------------------------------------------------------
    if "inc_row[]" in request.form or "plano_row[]" in request.form:
        planos = request.form.getlist("plano_row[]")
        equipos = request.form.getlist("equipo_row[]")
        incs = request.form.getlist("inc_row[]")
        clientes_list = request.form.getlist("clientes_row[]")
        bosfs = request.form.getlist("bosf_row[]")
        horas = request.form.getlist("hora_row[]")
        
        planos_en_reporte.update(planos)
        
        creadas = _crear_incidencias_individuales(
            planos, equipos, incs, clientes_list, bosfs, horas, hfc_activas
        )
            
        # Detectar averías que estaban activas y ya no figuran en el reporte de Grafana
        planos_en_reporte_up = {p.upper() for p in planos_en_reporte}
        grafana_rows_raw = [
            {"plano": r.plano, "clientes": r.clientes}
            for r in (parse_hfc_text(raw_text) if raw_text else [])
        ]
        cierres_completos, restauraciones_parciales = _separar_cierres_y_restauraciones(
            hfc_activas, planos_en_reporte_up, grafana_rows_raw
        )
        if restauraciones_parciales:
            return render_template(
                "restauracion_parcial.html",
                restauraciones=restauraciones_parciales,
                cierres_completos=cierres_completos,
                creadas_count=len(creadas),
                top_closures=TOP_CLOSURES
            )
        if cierres_completos:
            return render_template("cierre_masivo.html", desaparecidas=cierres_completos, creadas_count=len(creadas), top_closures=TOP_CLOSURES)
            
        flash(f"Sincronización HFC exitosa. Se registraron {len(creadas)} nuevas averías.", "success")
        return redirect(url_for("dashboard"))

    # Si viene desde el pegado directo simple
    hora_averia_str = request.form.get("hora_averia", "").strip()
    bosf_general = request.form.get("bosf_general", "").strip()
    hora_inicio = _parse_hora_averia(hora_averia_str)
    
    if not raw_text:
        flash("La entrada de texto de Grafana está vacía.", "warning")
        return redirect(url_for("dashboard"))
        
    registros = parse_hfc_text(raw_text)
    if not registros:
        flash("No se detectó un formato tabular de Grafana válido.", "danger")
        return redirect(url_for("dashboard"))
        
    # Construir set de planos activos en el NOC (incluye todos los planos de masivas)
    planos_ya_activos = set()
    incs_ya_activos = set()
    for a in hfc_activas:
        planos_ya_activos.update(_extraer_planos_de_incidencia(a))
        if a.inc:
            incs_ya_activos.add(a.inc)

    creadas = []
    planos_nuevos = {r.plano.upper() for r in registros}
    for r in registros:
        inc_code = r.inc if r.inc else ""
        if not inc_code.upper().startswith("INC"):
            continue
        p_up = r.plano.upper()
        # Saltar si el plano o el ticket ya está activo en el NOC
        if p_up in planos_ya_activos or inc_code in incs_ya_activos:
            continue
            
        pl = planos_repo.obtener_por_id(r.plano)
        dept = pl.departamento if pl else "DESCONOCIDO"
        prov = pl.provincia if pl else "DESCONOCIDO"
        dist = pl.distrito if pl else "DESCONOCIDO"
        
        obs = f"Plano: {r.plano}\nClientes: {r.clientes}\nEquipo: {r.equipo}"
        if bosf_general:
            obs += f"\n[{hora_inicio.strftime('%H:%M')}h] Se deriva a BOSF {bosf_general} para su atención."
            
        nueva = incidencia_service.crear(
            inc=inc_code,
            tipo=TipoIncidencia.HFC,
            tipo_falla="FALLA DE EQUIPO",
            departamento=dept,
            provincia=prov,
            distrito=dist,
            bosf=bosf_general,
            pext="",
            servicios=(ServicioAfectado.HFC,),
            observaciones=obs,
            hora_inicio=hora_inicio,
        )
        creadas.append(nueva)
        
    # Detectar averías que estaban activas y ya no figuran en el reporte de Grafana
    grafana_rows_raw = [{"plano": r.plano, "clientes": r.clientes} for r in registros]
    cierres_completos, restauraciones_parciales = _separar_cierres_y_restauraciones(
        hfc_activas, planos_nuevos, grafana_rows_raw
    )
    if restauraciones_parciales:
        return render_template(
            "restauracion_parcial.html",
            restauraciones=restauraciones_parciales,
            cierres_completos=cierres_completos,
            creadas_count=len(creadas),
            top_closures=TOP_CLOSURES
        )
    if cierres_completos:
        return render_template("cierre_masivo.html", desaparecidas=cierres_completos, creadas_count=len(creadas), top_closures=TOP_CLOSURES)
        
    flash(f"Sincronización HFC completa. Se registraron {len(creadas)} nuevas averías.", "success")
    return redirect(url_for("dashboard"))


def _separar_cierres_y_restauraciones(hfc_activas, planos_en_reporte_up: set, grafana_rows: list[dict]):
    """
    Clasifica incidencias activas en:
    - cierres_completos: todos sus planos desaparecieron de Grafana
    - restauraciones_parciales: solo algunos planos de una masiva desaparecieron
    Devuelve (cierres_completos, restauraciones_parciales)
    """
    cierres_completos = []
    restauraciones_parciales = []

    grafana_clientes = {r["plano"].upper(): int(r.get("clientes", 0) or 0) for r in grafana_rows}

    for inc_act in hfc_activas:
        mapa_nodos = _extraer_mapa_nodos_hfc(inc_act)
        if not mapa_nodos:
            continue

        nodos_en_grafana = [n for n in mapa_nodos if n.get("plano", "").upper() in planos_en_reporte_up]
        nodos_fuera = [n for n in mapa_nodos if n.get("plano", "").upper() not in planos_en_reporte_up]

        if not nodos_fuera:
            continue  # todos siguen activos, nada que hacer

        if not nodos_en_grafana:
            # Todos los planos desaparecieron → cierre completo
            cierres_completos.append(inc_act)
        else:
            # Parcial: algunos planos se recuperaron dentro de una masiva
            for n in nodos_en_grafana:
                p_up = n.get("plano", "").upper()
                if p_up in grafana_clientes and grafana_clientes[p_up] > 0:
                    n["clientes"] = grafana_clientes[p_up]

            nuevos_registros = [
                {"plano": n["plano"], "clientes": n.get("clientes", 0)}
                for n in nodos_en_grafana
            ]
            meta_nueva = planos_repo.obtener_metadatos_anillos(nuevos_registros)
            nuevo_total = sum(n.get("clientes", 0) for n in nodos_en_grafana)

            planos_recuperados_info = [
                {"plano": n["plano"], "clientes": n.get("clientes", 0), "inc": n.get("inc", "")}
                for n in nodos_fuera
            ]
            clientes_recuperados = sum(x["clientes"] for x in planos_recuperados_info)

            detalle_dists_nueva = []
            for d_name, d_val in meta_nueva["distritos_stats"].items():
                n_nod = d_val["nodos"]
                af = d_val["afectados"]
                tot = d_val["total_distrito"]
                pct = d_val["porcentaje"]
                detalle_dists_nueva.append(f"{d_name}: {n_nod} nodos, {af} de {tot} ({pct}%)")

            planos_restantes_nombres = [n["plano"] for n in nodos_en_grafana]
            planos_restantes_str = ", ".join(f"{n['plano']} ({n['clientes']})" for n in nodos_en_grafana)

            restauraciones_parciales.append({
                "inc": inc_act,
                "planos_restantes": planos_restantes_nombres,
                "planos_restantes_str": planos_restantes_str,
                "nodos_restantes_json": json.dumps(nodos_en_grafana),
                "planos_recuperados": planos_recuperados_info,
                "clientes_recuperados": clientes_recuperados,
                "nuevo_total_clientes": nuevo_total,
                "nuevo_n_nodos": len(nodos_en_grafana),
                "detalle_distritos_nuevo": " | ".join(detalle_dists_nueva),
                "meta_nueva": meta_nueva,
            })

    return cierres_completos, restauraciones_parciales


@app.route("/restauracion-parcial", methods=["POST"])
def restauracion_parcial():
    """Guarda la actualización de impacto cuando una masiva pierde algunos nodos parcialmente."""
    hora_actual = now_peru()
    hora_str = hora_actual.strftime("%H:%M")

    for key, value in request.form.items():
        if key.startswith("nota_"):
            inc_id = key.replace("nota_", "")
            nota = value.strip() or "Se verifica que han restablecido clientes. Se actualiza impacto."

            # Leer datos de planos restantes y detalle
            planos_restantes_str = request.form.get(f"planos_restantes_{inc_id}", "")
            detalle_nuevo = request.form.get(f"detalle_distritos_{inc_id}", "")
            nodos_restantes_json = request.form.get(f"nodos_restantes_json_{inc_id}", "")
            nuevo_total_cli = request.form.get(f"nuevo_total_clientes_{inc_id}", "")

            inc_match = incidencias_repo.obtener_por_id(inc_id)
            if inc_match:
                obs = inc_match.observaciones
                if nodos_restantes_json:
                    if re.search(r"NODOS_MASIVA_JSON:\s*\[[^\n]+\]", obs):
                        obs = re.sub(r"NODOS_MASIVA_JSON:\s*\[[^\n]+\]", f"NODOS_MASIVA_JSON: {nodos_restantes_json}", obs)
                    else:
                        obs = f"NODOS_MASIVA_JSON: {nodos_restantes_json}\n" + obs

                if planos_restantes_str:
                    obs = re.sub(r"Planos:\s*[^\n]+", f"Planos: {planos_restantes_str}", obs)
                if nuevo_total_cli:
                    obs = re.sub(r"Clientes:\s*\d+", f"Clientes: {nuevo_total_cli}", obs)
                if detalle_nuevo:
                    obs = re.sub(r"Detalle_Distritos:\s*[^\n]+", f"Detalle_Distritos: {detalle_nuevo}", obs)

                # Añadir la actualización al historial
                obs += f"\n[{hora_str}h] ACTUALIZACION: {nota}"

                inc_actualizada = replace(
                    inc_match,
                    observaciones=obs,
                    ultima_actualizacion=hora_actual
                )
                incidencias_repo.guardar(inc_actualizada)

    # También procesar cierres completos que vengan embebidos en el mismo formulario
    for key, value in request.form.items():
        if key.startswith("cierre_"):
            inc_id = key.replace("cierre_", "")
            motivo = value.strip() or "Se valida restablecimiento de servicios. Se cierra notificacion."
            inc_match = incidencias_repo.obtener_por_id(inc_id)
            if inc_match:
                obs_c = inc_match.observaciones + f"\n[{hora_str}h] CIERRE: {motivo}"
                inc_c = replace(inc_match, estado=EstadoIncidencia.CERRADA,
                                observaciones=obs_c, ultima_actualizacion=hora_actual)
                incidencias_repo.guardar(inc_c)

    flash("Actualizacion de impacto guardada correctamente.", "success")
    return redirect(url_for("dashboard"))


@app.route("/carga-ftth", methods=["GET", "POST"])
def carga_ftth():
    """Procesa alarmas FTTH: acepta archivo Excel (.xlsx) O texto pegado (TSV de Huawei NCE)."""
    if request.method == "GET":
        return redirect(url_for("dashboard"))

    archivo = request.files.get("ftth_xlsx")

    raw_text = request.form.get("ftth_paste", "").strip()

    reporte = None

    # 1. Prioridad: archivo Excel
    if archivo and archivo.filename and archivo.filename.lower().endswith((".xlsx", ".xls")):
        reporte = parse_ftth_excel(archivo.read(), archivo.filename)
        if not reporte.ok:
            flash(f"Error al procesar el archivo FTTH: {reporte.error}", "danger")
            return redirect(url_for("dashboard"))

    # 2. Fallback: texto pegado
    elif raw_text:
        reporte = parse_ftth_text(raw_text)
        if not reporte.ok:
            flash(f"Error al procesar el texto FTTH: {reporte.error}", "danger")
            return redirect(url_for("dashboard"))

    else:
        flash("Por favor sube un archivo .xlsx o pega el texto de alarmas FTTH.", "warning")
        return redirect(url_for("dashboard"))

    if not reporte.planos:
        flash("No se detectaron planos con ONTs afectadas.", "warning")
        return redirect(url_for("dashboard"))

    # ─── Agrupar planos por OLT (troncal) de la avería confirmada ────────────
    # En FTTH el analista sube exclusivamente los datos de la avería confirmada.
    # Se agrupan los planos del reporte sin interferir con otras averías activas.
    olt_grupos: dict[str, list] = {}
    for p in reporte.planos:
        olt_key = reporte.olts[0] if len(reporte.olts) == 1 else _inferir_olt_de_plano(p["plano"], reporte.olts)
        olt_key = olt_key or "OLT_DESCONOCIDA"
        olt_grupos.setdefault(olt_key, []).append(p)

    grupos_nuevos = [
        {
            "olt": olt,
            "planos": planos_lista,
            "total_onts": sum(p["onts"] for p in planos_lista),
            "es_masiva": len(planos_lista) >= 2,
        }
        for olt, planos_lista in olt_grupos.items()
    ]

    personal_activos = personal_repo.listar_activos()
    hora_actual = now_peru().strftime("%H:%M")
    fecha_actual = now_peru().strftime("%Y-%m-%d")

    return render_template(
        "ftth_preview.html",
        reporte=reporte,
        grupos_nuevos=grupos_nuevos,
        personal_activos=personal_activos,
        hora_actual=reporte.hora_deteccion or hora_actual,
        fecha_averia=reporte.fecha_deteccion_str or fecha_actual,
    )


@app.route("/ftth-confirmar", methods=["POST"])
def ftth_confirmar():
    """Crea la incidencia FTTH masiva con los datos del formulario de previsualización."""
    hora_averia_str = request.form.get("hora_averia", "").strip()
    fecha_averia_str = request.form.get("fecha_averia", "").strip()
    bosf_val = request.form.get("bosf", "").strip()
    inc_code = request.form.get("inc", "").strip() or "EN PROCESO"
    tipo_falla = request.form.get("tipo_falla", "Corte de Fibra").strip()
    olt_name = request.form.get("olt_name", "").strip()
    planos_json = request.form.get("planos_json", "[]").strip()
    total_onts = int(request.form.get("total_onts", "0") or 0)
    arrived_on_str = request.form.get("arrived_on_str", "").strip()

    dt_inicio = _parse_hora_averia(hora_averia_str, fecha_str=fecha_averia_str, arrived_on_str=arrived_on_str)

    try:
        planos_list = json.loads(planos_json)
    except (json.JSONDecodeError, TypeError):
        planos_list = []

    if not planos_list:
        flash("No hay planos FTTH para registrar.", "warning")
        return redirect(url_for("dashboard"))

    # Calcular metadatos geográficos a partir del primer plano conocido
    primer_plano_obj = None
    for p in planos_list:
        obj = planos_repo.obtener_por_id(p["plano"])
        if obj:
            primer_plano_obj = obj
            break

    dept = primer_plano_obj.departamento if primer_plano_obj else "DESCONOCIDO"
    prov = primer_plano_obj.provincia if primer_plano_obj else "DESCONOCIDO"

    # Calcular metadatos de distritos
    registros_meta = [{"plano": p["plano"], "clientes": p["onts"]} for p in planos_list]
    meta = planos_repo.obtener_metadatos_anillos(registros_meta)
    distritos_str = meta["distritos_str"]
    detalle_dists = [
        f"{d_name}: {d_val['nodos']} nodos, {d_val['afectados']} de {d_val['total_distrito']} ({d_val['porcentaje']}%)"
        for d_name, d_val in meta["distritos_stats"].items()
    ]
    detalle_distritos = " | ".join(detalle_dists)

    planos_str = ", ".join(f"{p['plano']} ({p['onts']})" for p in planos_list)

    obs = (
        f"OLT: {olt_name}\n"
        f"Planos: {planos_str}\n"
        f"Clientes: {total_onts}\n"
        f"Detalle_Distritos: {detalle_distritos}\n"
        f"Arrived_On: {arrived_on_str}\n"
    )
    # Primera actualización por defecto a los 5 minutos de la falla
    dt_primera_act = dt_inicio + datetime.timedelta(minutes=5)
    hora_primera_act_str = dt_primera_act.strftime("%H:%M")
    bosf_mostrar = bosf_val or "Pendiente"
    obs += f"[{hora_primera_act_str}h] Se deriva a BOSF {bosf_mostrar} para su atención."

    # Servicios adicionales de otros NOC (HFC / MBTS / Corporativo)
    hfc_nodos = request.form.get("hfc_nodos", "").strip()
    hfc_clientes_afectados = request.form.get("hfc_clientes_afectados", "").strip()
    mbts_detalle = request.form.get("mbts_detalle", "").strip()
    corp_detalle = request.form.get("corp_detalle", "").strip()

    if hfc_nodos or hfc_clientes_afectados:
        hfc_nodos_val = hfc_nodos or "0"
        hfc_cli_val = hfc_clientes_afectados or "0"
        distrito_target = primer_plano_obj.distrito if primer_plano_obj else distritos_str
        total_hfc_distrito = sum(
            p.clientes for p in planos_repo.listar_todos()
            if p.tecnologia.upper() == "HFC"
            and p.distrito.strip().upper() == (distrito_target or "").strip().upper()
        ) if distrito_target else 0
        obs += f"\nHFC_ADICIONAL: {hfc_nodos_val} nodos, {hfc_cli_val} afectados, total_hfc={total_hfc_distrito}"

    if mbts_detalle:
        obs += f"\nMBTS_ADICIONAL: {mbts_detalle.replace(chr(10), ' | ')}"

    if corp_detalle:
        obs += f"\nCORP_ADICIONAL: {corp_detalle.replace(chr(10), ' | ')}"

    etiqueta_falla = request.form.get("etiqueta_falla", "").strip()
    if etiqueta_falla:
        obs += f"\nETIQUETA_FALLA: {etiqueta_falla}"

    nueva = incidencia_service.crear(
        inc=inc_code,
        tipo=TipoIncidencia.FTTH,
        tipo_falla=tipo_falla,
        departamento=dept,
        provincia=prov,
        distrito=distritos_str,
        bosf=bosf_val,
        pext="",
        servicios=(ServicioAfectado.FTTH,),
        observaciones=obs,
        hora_inicio=dt_inicio,
    )

    flash(f"Incidencia FTTH ({nueva.inc}) registrada correctamente con {len(planos_list)} plano(s) y {total_onts} ONTs.", "success")
    return redirect(url_for("dashboard"))


@app.route("/ftth-actualizar-impacto", methods=["POST"])
def ftth_actualizar_impacto():
    """
    Procesa actualizaciones de impacto FTTH cuando una nueva carga de alarmas
    indica reducción de ONTs o planos completamente recuperados.
    """
    hora_str = request.form.get("hora", now_peru().strftime("%H:%M")).strip()
    try:
        h, m = [int(x) for x in hora_str.split(":")[:2]]
        hora_actual = now_peru().replace(hour=h, minute=m, second=0, microsecond=0)
    except Exception:
        hora_actual = now_peru()

    actualizados = 0

    # ── Actualizar impacto parcial (reducción de ONTs) ──────────────────────
    for key, value in request.form.items():
        if not key.startswith("nota_upd_"):
            continue
        inc_id = key.replace("nota_upd_", "")
        nota = value.strip() or "Se actualiza impacto. Se verifica restablecimiento parcial de clientes FTTH."
        planos_nuevos_str = request.form.get(f"planos_nuevos_str_{inc_id}", "").strip()
        total_nuevo = request.form.get(f"total_nuevo_{inc_id}", "").strip()

        inc_obj = incidencias_repo.obtener_por_id(inc_id)
        if not inc_obj:
            continue

        obs = inc_obj.observaciones
        # Actualizar línea Planos: con los nuevos valores
        if planos_nuevos_str:
            obs = re.sub(r"Planos:\s*[^\n]+", f"Planos: {planos_nuevos_str}", obs)
        # Actualizar línea Clientes:
        if total_nuevo:
            obs = re.sub(r"Clientes:\s*\d+", f"Clientes: {total_nuevo}", obs)

        obs += f"\n[{hora_str}h] ACTUALIZACION: {nota}"

        inc_upd = replace(
            inc_obj,
            observaciones=obs,
            ultima_actualizacion=hora_actual,
        )
        incidencias_repo.guardar(inc_upd)
        actualizados += 1

    # ── Cerrar planos completamente recuperados ─────────────────────────────
    for key, value in request.form.items():
        if not key.startswith("cierre_ftth_"):
            continue
        inc_id = key.replace("cierre_ftth_", "")
        motivo = value.strip() or "Se valida restablecimiento de servicios FTTH. Se cierra notificacion."

        inc_obj = incidencias_repo.obtener_por_id(inc_id)
        if not inc_obj:
            continue

        obs_c = inc_obj.observaciones + f"\n[{hora_str}h] CIERRE: {motivo}"
        inc_c = replace(
            inc_obj,
            estado=EstadoIncidencia.CERRADA,
            observaciones=obs_c,
            ultima_actualizacion=hora_actual,
        )
        incidencias_repo.guardar(inc_c)
        actualizados += 1

    if actualizados:
        flash(f"Impacto FTTH actualizado en {actualizados} incidencia(s).", "success")
    else:
        flash("No se aplicaron cambios.", "info")
    return redirect(url_for("dashboard"))




@app.route("/completar-incidencia/<id_>", methods=["POST"])
def completar_incidencia(id_):
    """Guarda los datos faltantes (INC, BOSF, PEXT, etc.) de una incidencia detectada"""
    inc = incidencias_repo.obtener_por_id(id_)
    if not inc:
        flash("Incidencia no encontrada.", "danger")
        return redirect(url_for("dashboard"))
        
    inc_code = request.form.get("inc", "").strip() or inc.inc
    bosf = request.form.get("bosf", "").strip()
    pext = request.form.get("pext", "").strip()
    tipo_falla = request.form.get("tipo_falla", "").strip() or inc.tipo_falla
    observaciones = request.form.get("observaciones", "").strip()
    
    inc_actualizada = replace(
        inc,
        inc=inc_code,
        bosf=bosf,
        pext=pext,
        tipo_falla=tipo_falla,
        observaciones=observaciones or inc.observaciones,
        ultima_actualizacion=now_peru()
    )
    incidencias_repo.guardar(inc_actualizada)
    flash(f"Incidencia {inc_code} completada y registrada exitosamente.", "success")
    return redirect(url_for("dashboard"))


@app.route("/procesar-cierre-masivo", methods=["POST"])
def procesar_cierre_masivo():
    """Procesa los motivos de cierre ingresados para las averías recuperadas"""
    hora_actual = now_peru().strftime("%H:%M")
    
    for key, value in request.form.items():
        if key.startswith("motivo_"):
            inc_id = key.replace("motivo_", "")
            motivo = value.strip() or "Se valida restablecimiento de servicios. Se cierra notificación."
            
            inc_match = incidencias_repo.obtener_por_id(inc_id)
            if inc_match:
                linea_cierre = f"\n[{hora_actual}h] CIERRE: {motivo}"
                obs_actualizada = inc_match.observaciones + linea_cierre
                
                inc_actualizada = replace(
                    inc_match,
                    estado=EstadoIncidencia.CERRADA,
                    observaciones=obs_actualizada,
                    ultima_actualizacion=now_peru()
                )
                incidencias_repo.guardar(inc_actualizada)
                
    flash("Cierres masivos procesados de manera exitosa.", "success")
    return redirect(url_for("dashboard"))


@app.route("/api/detalle/<id_>")
@app.route("/detalle/<id_>")
def detalle(id_):
    """Muestra detalles del contratista y copia el texto estructurado para WhatsApp (soporta JSON para pop-up)."""
    inc = incidencias_repo.obtener_por_id(id_)
    is_json_request = (
        request.path.startswith("/api/")
        or request.args.get("format") == "json"
        or request.headers.get("Accept") == "application/json"
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )
    if not inc:
        if is_json_request:
            return {"ok": False, "error": "Incidencia no encontrada."}, 404
        flash("Incidencia no encontrada.", "danger")
        return redirect(url_for("dashboard"))
        
    plano_name, _ = _obtener_plano_y_clientes(inc)
    plano_obj = planos_repo.obtener_por_id(plano_name) if plano_name else None
    
    # Extraer todos los planos afectados para mostrarlos detalladamente en la vista
    planos_ids = _extraer_planos_de_incidencia(inc)
    if not planos_ids and plano_name:
        planos_ids = [plano_name]
        
    planos_detalle = []
    olt_match = re.search(r"OLT:\s*([^\n]+)", inc.observaciones, re.IGNORECASE)
    olt_val = olt_match.group(1).strip() if olt_match else ""

    for pid in planos_ids:
        pobj = planos_repo.obtener_por_id(pid)
        if inc.tipo == TipoIncidencia.FTTH:
            onts = _extraer_onts_registradas_ftth(inc, pid)
        else:
            m_cli = re.search(rf"{re.escape(pid)}\s*\((\d+)\)", inc.observaciones, re.IGNORECASE)
            onts = int(m_cli.group(1)) if m_cli else (pobj.clientes if pobj else 0)
            
        planos_detalle.append({
            "id": pid,
            "clientes": onts,
            "departamento": pobj.departamento if pobj else inc.departamento,
            "provincia": pobj.provincia if pobj else inc.provincia,
            "distrito": pobj.distrito if pobj else inc.distrito,
            "hub": pobj.hub if pobj else "—",
            "cmts_olt": pobj.cmts_olt if pobj else (olt_val or "—")
        })

    personal_list = personal_repo.listar_activos()
    pers_obj = next((p for p in personal_list if p.nombre == inc.bosf), None)
    tel = pers_obj.telefono if pers_obj else None
    
    whatsapp_msg = generate_whatsapp_message(inc, plano_obj, tel)
    
    if is_json_request:
        hub_val = plano_obj.hub if plano_obj and plano_obj.hub else (planos_detalle[0]["hub"] if planos_detalle and planos_detalle[0]["hub"] != "—" else "—")
        equipo_val = plano_obj.cmts_olt if plano_obj and plano_obj.cmts_olt else (planos_detalle[0]["cmts_olt"] if planos_detalle and planos_detalle[0]["cmts_olt"] != "—" else (olt_val or "—"))
        return {
            "ok": True,
            "inc": {
                "id": inc.id,
                "inc": inc.inc,
                "tipo": inc.tipo.value,
                "estado": inc.estado.value,
                "departamento": inc.departamento,
                "provincia": inc.provincia,
                "distrito": inc.distrito,
                "tipo_falla": inc.tipo_falla,
                "bosf": inc.bosf or "Sin asignar",
            },
            "contratista": {
                "nombre": pers_obj.nombre if pers_obj else (inc.bosf or "Sin asignar"),
                "cargo": pers_obj.cargo if pers_obj else "Rol no especificado",
                "telefono": tel or "—",
            },
            "ubicacion": {
                "hub": hub_val,
                "cmts_olt": equipo_val,
            },
            "planos_detalle": planos_detalle,
            "whatsapp_msg": whatsapp_msg,
        }

    return render_template(
        "detalle.html",
        inc=inc,
        plano=plano_obj,
        planos_detalle=planos_detalle,
        contratista=pers_obj,
        telefono=tel,
        whatsapp_msg=whatsapp_msg
    )


@app.route("/api/carga-anterior", methods=["POST"])
def api_carga_anterior():
    """Procesa el mensaje consolidado del turno anterior y carga/actualiza las incidencias."""
    data = request.get_json(silent=True) or {}
    raw_text = data.get("raw_text") or request.form.get("raw_text", "")
    if not raw_text.strip():
        if request.is_json or request.path.startswith("/api/"):
            return {"ok": False, "error": "El texto del turno anterior está vacío."}, 400
        flash("El texto ingresado está vacío.", "warning")
        return redirect(url_for("dashboard"))

    bloques = separar_bloques_averias(raw_text)
    if not bloques:
        if request.is_json or request.path.startswith("/api/"):
            return {"ok": False, "error": "No se detectaron bloques de incidencias válidos en el texto."}, 400
        flash("No se detectaron bloques de incidencias en el texto.", "warning")
        return redirect(url_for("dashboard"))

    creadas = 0
    actualizadas = 0
    detalles = []

    for b in bloques:
        p = parsear_bloque_averia(b, planos_repo)
        
        # Buscar si ya existe por código INC o por plano activo
        inc_existente = None
        if p.inc and p.inc != "EN PROCESO":
            inc_existente = incidencias_repo.obtener_por_inc(p.inc)
        
        if not inc_existente and p.plano:
            for act in incidencias_repo.listar_activas():
                p_id, _ = _obtener_plano_y_clientes(act)
                planos_act = _extraer_planos_de_incidencia(act)
                if p.plano == p_id or p.plano in planos_act:
                    inc_existente = act
                    break

        if inc_existente:
            # Actualizar incidencia existente
            inc_act = replace(
                inc_existente,
                inc=p.inc if (p.inc and p.inc != "EN PROCESO") else inc_existente.inc,
                bosf=p.bosf if p.bosf and p.bosf != "Pendiente" else inc_existente.bosf,
                estado=p.estado,
                observaciones=p.observaciones,
                ultima_actualizacion=now_peru()
            )
            incidencias_repo.guardar(inc_act)
            actualizadas += 1
            detalles.append({
                "id": inc_act.id,
                "inc": inc_act.inc,
                "tipo": inc_act.tipo.value,
                "accion": "actualizada",
                "plano": p.plano
            })
        else:
            # Crear nueva incidencia
            nuevo_id = str(uuid.uuid4())[:8].upper()
            nueva = Incidencia(
                id=nuevo_id,
                inc=p.inc,
                tipo=p.tipo,
                estado=p.estado,
                tipo_falla=p.tipo_falla,
                departamento=p.departamento,
                provincia=p.provincia,
                distrito=p.distrito,
                hora_inicio=p.hora_inicio or now_peru(),
                ultima_actualizacion=now_peru(),
                bosf=p.bosf,
                pext=p.pext,
                servicios=tuple(p.servicios),
                observaciones=p.observaciones
            )
            incidencias_repo.guardar(nueva)
            creadas += 1
            detalles.append({
                "id": nueva.id,
                "inc": nueva.inc,
                "tipo": nueva.tipo.value,
                "accion": "creada",
                "plano": p.plano
            })

    if request.is_json or request.path.startswith("/api/"):
        return {
            "ok": True,
            "total_bloques": len(bloques),
            "creadas": creadas,
            "actualizadas": actualizadas,
            "detalles": detalles
        }

    flash(f"Carga anterior completada: {creadas} incidencias creadas, {actualizadas} actualizadas.", "success")
    return redirect(url_for("dashboard"))


@app.route("/api/resumen-turno", methods=["GET"])
def api_resumen_turno():
    """Genera el consolidado de WhatsApp de todas las averías pendientes para el relevo de turno."""
    activas = incidencias_repo.listar_activas()
    if not activas:
        return {
            "ok": True,
            "total": 0,
            "resumen": "=================\n=====AVERÍAS=====\n=================\n\n*No hay averías activas pendientes en el turno.*"
        }

    # Ordenar cronológicamente (más recientes primero)
    activas_ordenadas = sorted(activas, key=lambda x: x.hora_inicio, reverse=True)
    personal_list = personal_repo.listar_activos()

    mensajes = []
    for inc in activas_ordenadas:
        plano_name, _ = _obtener_plano_y_clientes(inc)
        plano_obj = planos_repo.obtener_por_id(plano_name) if plano_name else None
        pers_obj = next((p for p in personal_list if p.nombre == inc.bosf), None)
        tel = pers_obj.telefono if pers_obj else None
        
        msg_ind = generate_whatsapp_message(inc, plano_obj, tel)
        mensajes.append(msg_ind.strip())

    separador = "\n\n***********************************************************\n\n"
    cuerpo = separador.join(mensajes)
    resumen_final = f"=================\n=====AVERÍAS=====\n=================\n\n{cuerpo}"

    return {
        "ok": True,
        "total": len(activas_ordenadas),
        "resumen": resumen_final
    }


@app.route("/api/evaluar-recuperacion-ftth/<id_>", methods=["POST"])
def api_evaluar_recuperacion_ftth(id_):
    """Evalúa la recuperación de ONTs para una incidencia FTTH específica comparando
    el reporte actual de alarmas (NCE) contra los planos de dicha incidencia."""
    inc = incidencias_repo.obtener_por_id(id_)
    if not inc:
        return {"ok": False, "error": "Incidencia no encontrada."}, 404

    data = request.get_json(silent=True) or {}
    raw_text = data.get("raw_text", "").strip()
    if not raw_text:
        return {"ok": False, "error": "Por favor ingrese el texto de alarmas de Huawei NCE."}, 400

    reporte = parse_ftth_text(raw_text)
    if not reporte.ok:
        return {"ok": False, "error": f"Error al procesar el texto: {reporte.error}"}, 400

    # Mapa de {PLANO_UPPER -> ONTs actuales}
    nuevas_alarmas_map = {p["plano"].upper(): p["onts"] for p in reporte.planos}

    # Planos registrados en ESTA incidencia
    planos_inc = _extraer_planos_de_incidencia(inc)
    if not planos_inc:
        p_name, _ = _obtener_plano_y_clientes(inc)
        if p_name:
            planos_inc = [p_name]

    if not planos_inc:
        return {"ok": False, "error": "La incidencia no tiene planos registrados para comparar."}, 400

    planos_comparativa = []
    total_antes = 0
    total_ahora = 0

    for pid in planos_inc:
        pid_upper = pid.upper()
        onts_antes = _extraer_onts_registradas_ftth(inc, pid_upper)
        onts_ahora = nuevas_alarmas_map.get(pid_upper, 0)
        recuperados = max(0, onts_antes - onts_ahora)

        total_antes += onts_antes
        total_ahora += onts_ahora

        planos_comparativa.append({
            "plano": pid,
            "onts_antes": onts_antes,
            "onts_ahora": onts_ahora,
            "recuperados": recuperados
        })

    total_recuperados = max(0, total_antes - total_ahora)
    es_recuperacion_total = (total_ahora == 0)

    if es_recuperacion_total:
        sugerencia_nota = f"Se valida restablecimiento total de servicios FTTH ({total_antes} clientes recuperados). Se procede con el cierre."
        accion_sugerida = "CIERRE"
    elif total_recuperados > 0:
        sugerencia_nota = f"Se observa restablecimiento {total_recuperados} clientes FTTH. Quedan {total_ahora} clientes afectados. Se mantendrá en monitoreo."
        accion_sugerida = "ACTUALIZACION"
    else:
        sugerencia_nota = f"Se verifica monitoreo de alarmas FTTH. Se mantienen {total_ahora} clientes afectados."
        accion_sugerida = "ACTUALIZACION"

    # Preparar string para actualizar observaciones de la incidencia
    planos_nuevos_str = ", ".join(f"{p['plano']} ({p['onts_ahora']})" for p in planos_comparativa if p['onts_ahora'] > 0)
    if not planos_nuevos_str:
        planos_nuevos_str = ", ".join(f"{p['plano']} (0)" for p in planos_comparativa)

    return {
        "ok": True,
        "inc": inc.inc,
        "total_antes": total_antes,
        "total_ahora": total_ahora,
        "total_recuperados": total_recuperados,
        "es_recuperacion_total": es_recuperacion_total,
        "accion_sugerida": accion_sugerida,
        "sugerencia_nota": sugerencia_nota,
        "planos_comparativa": planos_comparativa,
        "planos_nuevos_str": planos_nuevos_str
    }


@app.route("/actualizar/<id_>", methods=["GET", "POST"])
def actualizar(id_):
    """Panel individual de actualización y cierres de incidencias"""
    inc = incidencias_repo.obtener_por_id(id_)
    if not inc:
        flash("Incidencia no encontrada.", "danger")
        return redirect(url_for("dashboard"))
        
    if request.method == "POST":
        tipo_actualizacion = request.form.get("tipo_actualizacion")  # ACTUALIZACION o CIERRE
        hora = request.form.get("hora") or now_peru().strftime("%H:%M")
        novedad = request.form.get("novedad", "").strip()
        causa_raiz = request.form.get("causa_raiz", "").strip()
        correctivo = request.form.get("correctivo", "").strip()
        if novedad:
            linea_nueva = f"\n[{hora}h] {tipo_actualizacion}: {novedad}"
        elif inc.tipo == TipoIncidencia.FTTH:
            linea_nueva = f"\n[{hora}h] {tipo_actualizacion}: Actualización de impacto"
        else:
            linea_nueva = f"\n[{hora}h] {tipo_actualizacion}"
        obs_actualizada = inc.observaciones + linea_nueva

        # Para FTTH: guardar/actualizar causa raiz y correctivo en observaciones
        if inc.tipo == TipoIncidencia.FTTH:
            if causa_raiz:
                if re.search(r"CAUSA_RAIZ:", obs_actualizada):
                    obs_actualizada = re.sub(r"CAUSA_RAIZ:[^\n]*", f"CAUSA_RAIZ: {causa_raiz}", obs_actualizada)
                else:
                    obs_actualizada = re.sub(r"(Arrived_On:[^\n]*\n?)", r"\1" + f"CAUSA_RAIZ: {causa_raiz}\n", obs_actualizada)
                    if "CAUSA_RAIZ:" not in obs_actualizada:
                        obs_actualizada = f"CAUSA_RAIZ: {causa_raiz}\n" + obs_actualizada
            if correctivo:
                if re.search(r"CORRECTIVO:", obs_actualizada):
                    obs_actualizada = re.sub(r"CORRECTIVO:[^\n]*", f"CORRECTIVO: {correctivo}", obs_actualizada)
                else:
                    obs_actualizada = re.sub(r"(CAUSA_RAIZ:[^\n]*\n?)", r"\1" + f"CORRECTIVO: {correctivo}\n", obs_actualizada)
                    if "CORRECTIVO:" not in obs_actualizada:
                        obs_actualizada += f"\nCORRECTIVO: {correctivo}"
        
        nuevo_estado = EstadoIncidencia.ACTUALIZADA if tipo_actualizacion == "ACTUALIZACION" else EstadoIncidencia.CERRADA
        
        # Para FTTH: guardar servicios adicionales (HFC/MBTS/Corporativo) si se llenaron
        if inc.tipo == TipoIncidencia.FTTH:
            hfc_nodos = request.form.get("hfc_nodos", "").strip()
            hfc_clientes_afectados = request.form.get("hfc_clientes_afectados", "").strip()
            mbts_detalle = request.form.get("mbts_detalle", "").strip()
            corp_detalle = request.form.get("corp_detalle", "").strip()

            # Calcular total HFC del anillo desde la base de datos
            if hfc_nodos or hfc_clientes_afectados:
                hfc_nodos_val = hfc_nodos or "0"
                hfc_cli_val = hfc_clientes_afectados or "0"
                # Calcular total HFC del distrito afectado desde planos.parquet
                distrito_inc = inc.distrito or ""
                total_hfc_distrito = sum(
                    p.clientes for p in planos_repo.listar_todos()
                    if p.tecnologia.upper() == "HFC"
                    and p.distrito.strip().upper() == distrito_inc.strip().upper()
                ) if distrito_inc else 0
                hfc_tag = f"HFC_ADICIONAL: {hfc_nodos_val} nodos, {hfc_cli_val} afectados, total_hfc={total_hfc_distrito}"
                if re.search(r"HFC_ADICIONAL:", obs_actualizada):
                    obs_actualizada = re.sub(r"HFC_ADICIONAL:[^\n]*", hfc_tag, obs_actualizada)
                else:
                    obs_actualizada += f"\n{hfc_tag}"

            if mbts_detalle:
                mbts_tag = f"MBTS_ADICIONAL: {mbts_detalle.replace(chr(10), ' | ')}"
                if re.search(r"MBTS_ADICIONAL:", obs_actualizada):
                    obs_actualizada = re.sub(r"MBTS_ADICIONAL:[^\n]*", mbts_tag, obs_actualizada)
                else:
                    obs_actualizada += f"\n{mbts_tag}"

            if corp_detalle:
                corp_tag = f"CORP_ADICIONAL: {corp_detalle.replace(chr(10), ' | ')}"
                if re.search(r"CORP_ADICIONAL:", obs_actualizada):
                    obs_actualizada = re.sub(r"CORP_ADICIONAL:[^\n]*", corp_tag, obs_actualizada)
                else:
                    obs_actualizada += f"\n{corp_tag}"

            etiqueta_falla = request.form.get("etiqueta_falla", "").strip()
            if etiqueta_falla:
                if re.search(r"ETIQUETA_FALLA:", obs_actualizada):
                    obs_actualizada = re.sub(r"ETIQUETA_FALLA:[^\n]*", f"ETIQUETA_FALLA: {etiqueta_falla}", obs_actualizada)
                else:
                    obs_actualizada += f"\nETIQUETA_FALLA: {etiqueta_falla}"

            # Si se envió actualización de planos/onts desde la herramienta de recuperación:
            planos_nuevos_str = request.form.get("planos_nuevos_str", "").strip()
            nuevo_total_onts = request.form.get("nuevo_total_onts", "").strip()
            if planos_nuevos_str:
                if re.search(r"Planos:\s*[^\n]+", obs_actualizada):
                    obs_actualizada = re.sub(r"Planos:\s*[^\n]+", f"Planos: {planos_nuevos_str}", obs_actualizada)
                else:
                    obs_actualizada = f"Planos: {planos_nuevos_str}\n" + obs_actualizada

            if nuevo_total_onts.isdigit():
                tot_int = int(nuevo_total_onts)
                if re.search(r"Clientes:\s*\d+", obs_actualizada):
                    obs_actualizada = re.sub(r"Clientes:\s*\d+", f"Clientes: {tot_int}", obs_actualizada)
                m_dist_det = re.search(r"Detalle_Distritos:\s*([^:]+):\s*(\d+)\s*nodos?,\s*(\d+)\s*de\s*(\d+)\s*\(([\d\.]+%?)\)", obs_actualizada)
                if m_dist_det:
                    d_nom = m_dist_det.group(1)
                    d_nod = m_dist_det.group(2)
                    d_tot = int(m_dist_det.group(4))
                    d_pct = round(tot_int / d_tot * 100, 3) if d_tot > 0 else 0
                    nuevo_det = f"Detalle_Distritos: {d_nom}: {d_nod} nodos, {tot_int} de {d_tot} ({d_pct}%)"
                    obs_actualizada = re.sub(r"Detalle_Distritos:[^\n]+", nuevo_det, obs_actualizada)

        
        inc_actualizada = replace(
            inc,
            estado=nuevo_estado,
            observaciones=obs_actualizada,
            ultima_actualizacion=now_peru()
        )
        incidencias_repo.guardar(inc_actualizada)
        flash("Soporte operativo registrado en la base de datos.", "success")
        return redirect(url_for("dashboard"))
        
    bosf_val = inc.bosf or "[Nombre]"
    # Para FTTH, usar actualizaciones especificas + causas raiz + correctivos + servicios adicionales
    if inc.tipo == TipoIncidencia.FTTH:
        top_updates = TOP_UPDATES_FTTH
        causa_raiz_actual = ""
        correctivo_actual = ""
        m_cr = re.search(r"CAUSA_RAIZ:\s*([^\n]+)", inc.observaciones)
        m_co = re.search(r"CORRECTIVO:\s*([^\n]+)", inc.observaciones)
        if m_cr:
            causa_raiz_actual = m_cr.group(1).strip()
        if m_co:
            correctivo_actual = m_co.group(1).strip()

        m_eti = re.search(r"ETIQUETA_FALLA:\s*([^\n]+)", inc.observaciones)
        etiqueta_falla_actual = m_eti.group(1).strip() if m_eti else ""

        m_hfc = re.search(r"HFC_ADICIONAL:\s*(\d+)\s*nodos?,\s*(\d+)\s*afectados", inc.observaciones)
        hfc_nodos_actual = m_hfc.group(1) if m_hfc else ""
        hfc_afectados_actual = m_hfc.group(2) if m_hfc else ""

        m_mbts = re.search(r"MBTS_ADICIONAL:\s*([^\n]+)", inc.observaciones)
        mbts_actual = m_mbts.group(1).replace(" | ", "\n") if m_mbts else ""

        m_corp = re.search(r"CORP_ADICIONAL:\s*([^\n]+)", inc.observaciones)
        corp_actual = m_corp.group(1).replace(" | ", "\n") if m_corp else ""
    else:
        top_updates = [item.replace("{bosf}", bosf_val) for item in TOP_UPDATES_TEMPLATE]
        causa_raiz_actual = None
        correctivo_actual = None
        etiqueta_falla_actual = ""
        hfc_nodos_actual = ""
        hfc_afectados_actual = ""
        mbts_actual = ""
        corp_actual = ""

    return render_template(
        "actualizar.html",
        inc=inc,
        top_updates=top_updates,
        top_closures=TOP_CLOSURES,
        hora_actual=now_peru().strftime("%H:%M"),
        es_ftth=(inc.tipo == TipoIncidencia.FTTH),
        causas_raiz=FTTH_CAUSAS_RAIZ,
        correctivos=FTTH_CORRECTIVOS,
        causa_raiz_actual=causa_raiz_actual,
        correctivo_actual=correctivo_actual,
        etiqueta_falla_actual=etiqueta_falla_actual,
        hfc_nodos_actual=hfc_nodos_actual,
        hfc_afectados_actual=hfc_afectados_actual,
        mbts_actual=mbts_actual,
        corp_actual=corp_actual,
    )


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)


