# src/services/incidencia_service.py
from __future__ import annotations

import uuid
from datetime import datetime
from src.core.models import Incidencia, TipoIncidencia, EstadoIncidencia, ServicioAfectado, HFCRegistro
from src.utils.time_utils import now_peru

class IncidenciaService:
    def __init__(self, repo):
        self._repo = repo

    def listar_pendientes(self) -> list[Incidencia]:
        return self._repo.listar_activas()

    def marcar_activa(self, inc: Incidencia) -> None:
        from dataclasses import replace
        if inc.estado == EstadoIncidencia.NUEVA:
            inc_act = replace(inc, estado=EstadoIncidencia.ACTIVA, ultima_actualizacion=now_peru())
            self._repo.guardar(inc_act)

    def crear(
        self,
        inc: str,
        tipo: TipoIncidencia,
        tipo_falla: str,
        departamento: str,
        provincia: str,
        distrito: str,
        bosf: str,
        pext: str,
        servicios: tuple[ServicioAfectado, ...],
        observaciones: str,
        hora_inicio: datetime | None = None,
    ) -> Incidencia:
        dt_inicio = hora_inicio or now_peru()
        nueva_inc = Incidencia(
            id=str(uuid.uuid4())[:8].upper(),
            inc=inc,
            tipo=tipo,
            estado=EstadoIncidencia.NUEVA,
            tipo_falla=tipo_falla,
            departamento=departamento,
            provincia=provincia,
            distrito=distrito,
            hora_inicio=dt_inicio,
            ultima_actualizacion=now_peru(),
            bosf=bosf,
            pext=pext,
            servicios=servicios,
            observaciones=observaciones,
        )
        self._repo.guardar(nueva_inc)
        return nueva_inc

    def registrar_bulk_hfc(self, registros: list[HFCRegistro], planos_repo, hora_inicio: datetime | None = None) -> list[Incidencia]:
        creadas = []
        for r in registros:
            inc_code = r.inc if r.inc else "EN PROCESO"
            
            existente = None
            for activa in self._repo.listar_activas():
                if inc_code != "EN PROCESO" and activa.inc == inc_code:
                    existente = activa
                    break
                if inc_code == "EN PROCESO":
                    if f"Plano: {r.plano}" in activa.observaciones:
                        existente = activa
                        break
            
            if existente:
                continue
                
            pl = planos_repo.obtener_por_id(r.plano)
            dept = pl.departamento if pl else "DESCONOCIDO"
            prov = pl.provincia if pl else "DESCONOCIDO"
            dist = pl.distrito if pl else "DESCONOCIDO"
            
            obs = f"Plano: {r.plano}\nClientes: {r.clientes}\nEquipo: {r.equipo}"
            
            nueva = self.crear(
                inc=inc_code,
                tipo=TipoIncidencia.HFC,
                tipo_falla="FALLA DE EQUIPO",
                departamento=dept,
                provincia=prov,
                distrito=dist,
                bosf="",
                pext="",
                servicios=(ServicioAfectado.HFC,),
                observaciones=obs,
                hora_inicio=hora_inicio,
            )
            creadas.append(nueva)
        return creadas

    def registrar_bulk_ftth(self, registros: list[dict], planos_repo, hora_inicio: datetime | None = None) -> list[Incidencia]:
        creadas = []
        for r in registros:
            olt = r.get("olt", "OLT_FTTH")
            puerto = r.get("puerto", "")
            clientes = r.get("clientes", 0)
            
            # Buscar plano coincidente con el OLT en base maestra de planos
            pl = planos_repo.obtener_por_id(olt)
            dept = pl.departamento if pl else "DESCONOCIDO"
            prov = pl.provincia if pl else "DESCONOCIDO"
            dist = pl.distrito if pl else "DESCONOCIDO"
            
            obs = f"Plano: {olt}\nPuerto: {puerto}\nClientes: {clientes}\nEquipo: {olt}"
            
            nueva = self.crear(
                inc="EN PROCESO",
                tipo=TipoIncidencia.FTTH,
                tipo_falla="CAÍDA MASIVA FTTH",
                departamento=dept,
                provincia=prov,
                distrito=dist,
                bosf="",
                pext="",
                servicios=(ServicioAfectado.FTTH,),
                observaciones=obs,
                hora_inicio=hora_inicio,
            )
            creadas.append(nueva)
        return creadas
