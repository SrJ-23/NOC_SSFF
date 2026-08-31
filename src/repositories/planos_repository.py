"""Repositorio de Planos — abstrae el acceso al dato maestro planos.parquet."""

from __future__ import annotations

from src.core.models import Plano
from src.data.data_manager import DataManager, get_data_manager
from src.repositories.base import ReadOnlyRepository


class PlanosRepository(ReadOnlyRepository[Plano]):
    """
    Todo acceso a datos de plano pasa por aquí, nunca directo al
    DataManager ni al Parquet desde services/pages.
    """

    def __init__(self, data_manager: DataManager | None = None):
        self._data = data_manager or get_data_manager()

    def obtener_por_id(self, id_: str) -> Plano | None:
        return self._data.obtener_plano(id_)

    def listar_todos(self) -> list[Plano]:
        return list(self._data.planos.values())

    def filtrar_por_departamento(self, departamento: str) -> list[Plano]:
        return [p for p in self.listar_todos() if p.departamento == departamento]

    def filtrar_por_tecnologia(self, tecnologia: str) -> list[Plano]:
        return [p for p in self.listar_todos() if p.tecnologia == tecnologia]

    def total_clientes_por_distrito(self, distrito: str) -> int:
        d_clean = distrito.strip().upper()
        return sum(p.clientes for p in self.listar_todos() if p.distrito.strip().upper() == d_clean)

    def obtener_metadatos_anillos(self, registros: list[dict]) -> dict:
        """
        Calcula anillos, distritos afectados, conteo de nodos y porcentajes de impacto
        a partir de una lista de registros detectados [{'plano': ..., 'clientes': ...}].
        """
        anillos = []
        cmts_olts = []
        departamentos = []
        provincias = []
        distritos_map: dict[str, dict] = {}

        for r in registros:
            p_name = r.get("plano", "")
            clientes_afectados = int(r.get("clientes", 0) or 0)
            plano_obj = self.obtener_por_id(p_name)

            if plano_obj:
                if plano_obj.anillo_troncal and plano_obj.anillo_troncal not in ("-", "DETERMINAR"):
                    if plano_obj.anillo_troncal not in anillos:
                        anillos.append(plano_obj.anillo_troncal)
                if plano_obj.cmts_olt and plano_obj.cmts_olt not in cmts_olts:
                    cmts_olts.append(plano_obj.cmts_olt)
                if plano_obj.departamento and plano_obj.departamento not in departamentos:
                    departamentos.append(plano_obj.departamento)
                if plano_obj.provincia and plano_obj.provincia not in provincias:
                    provincias.append(plano_obj.provincia)

                dist_name = plano_obj.distrito.strip().upper() if plano_obj.distrito else "DESCONOCIDO"
            else:
                dist_name = "DESCONOCIDO"

            if dist_name not in distritos_map:
                total_dist = self.total_clientes_por_distrito(dist_name) if dist_name != "DESCONOCIDO" else 0
                distritos_map[dist_name] = {
                    "distrito": dist_name,
                    "nodos": 0,
                    "afectados": 0,
                    "total_distrito": total_dist,
                }

            distritos_map[dist_name]["nodos"] += 1
            distritos_map[dist_name]["afectados"] += clientes_afectados

        # Calcular porcentajes
        for d in distritos_map.values():
            tot = d["total_distrito"]
            af = d["afectados"]
            d["porcentaje"] = round((af / tot * 100), 2) if tot > 0 else 0.0

        anillo_str = ", ".join(anillos) if anillos else ""
        if len(anillos) == 2:
            anillo_str = f"{anillos[0]} y {anillos[1]}"
        elif len(anillos) > 2:
            anillo_str = ", ".join(anillos[:-1]) + f" y {anillos[-1]}"

        return {
            "anillos": anillos,
            "anillo_str": anillo_str,
            "cmts_olts": cmts_olts,
            "cmts_str": ", ".join(cmts_olts),
            "departamento": departamentos[0] if departamentos else "LIMA",
            "provincia": provincias[0] if provincias else "LIMA",
            "distritos": list(distritos_map.keys()),
            "distritos_str": " ".join(distritos_map.keys()),
            "distritos_stats": distritos_map
        }

    def obtener_grupos_anillo(self, registros: list[dict]) -> list[dict]:
        """
        Agrupa los registros de Grafana por Anillo/Troncal detectado, en lugar de
        combinarlos en un único resumen. Cuando dos o más anillos comparten equipo
        (p.ej. Anillo 7 y Anillo 6 sobre el mismo OLT/CMTS) se devuelven como grupos
        separados, cada uno apto para convertirse en su propia Incidencia Masiva.

        Los registros cuyo plano no tiene un anillo_troncal válido se devuelven como
        grupos de un solo nodo (es_ring_real=False), para que el frontend los trate
        como registro individual en vez de forzarlos a una masiva.
        """
        grupos_map: dict[str, list[dict]] = {}
        orden_anillos: list[str] = []

        for r in registros:
            p_name = r.get("plano", "")
            plano_obj = self.obtener_por_id(p_name)
            anillo_key = None
            if plano_obj and plano_obj.anillo_troncal and plano_obj.anillo_troncal not in ("-", "DETERMINAR"):
                anillo_key = plano_obj.anillo_troncal
            else:
                anillo_key = f"__SIN_ANILLO__{p_name}"

            if anillo_key not in grupos_map:
                grupos_map[anillo_key] = []
                orden_anillos.append(anillo_key)
            grupos_map[anillo_key].append(r)

        grupos = []
        for key in orden_anillos:
            filas = grupos_map[key]
            meta = self.obtener_metadatos_anillos(filas)
            detalle_dists = [
                f"{d_name}: {d_val['nodos']} nodos, {d_val['afectados']} de {d_val['total_distrito']} ({d_val['porcentaje']}%)"
                for d_name, d_val in meta["distritos_stats"].items()
            ]
            grupos.append({
                "anillo_key": key,
                "es_ring_real": not key.startswith("__SIN_ANILLO__"),
                "anillo_str": meta["anillo_str"] or "Anillo Principal",
                "cmts_str": meta["cmts_str"],
                "departamento": meta["departamento"],
                "provincia": meta["provincia"],
                "distritos_str": meta["distritos_str"],
                "distritos_stats": meta["distritos_stats"],
                "detalle_distritos": " | ".join(detalle_dists),
                "total_afectados": sum(int(r.get("clientes", 0) or 0) for r in filas),
                "total_nodos": len(filas),
                "nodos": [
                    {
                        "plano": r.get("plano", ""),
                        "equipo": r.get("equipo", ""),
                        "clientes": int(r.get("clientes", 0) or 0),
                        "inc": r.get("inc") or "EN PROCESO",
                    }
                    for r in filas
                ],
            })
        return grupos
