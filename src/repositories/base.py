# src/repositories/base.py
import time
from typing import Generic, TypeVar, Callable

T = TypeVar('T')

class ReadOnlyRepository(Generic[T]):
    def obtener_por_id(self, id_: str) -> T | None:
        pass
    def listar_todos(self) -> list[T]:
        pass

class WritableRepository(ReadOnlyRepository[T], Generic[T]):
    def guardar(self, entidad: T) -> None:
        pass
    def eliminar(self, id_: str) -> bool:
        pass

class SheetsRepositoryBase(Generic[T]):
    def __init__(
        self,
        client,
        sheet_name: str,
        columna_id: str,
        from_dict: Callable[[dict], T],
        to_dict: Callable[[T], dict],
        ttl_seconds: float,
        id_getter: Callable[[T], str],
    ):
        self.client = client
        self.sheet_name = sheet_name
        self.columna_id = columna_id
        self.from_dict = from_dict
        self.to_dict = to_dict
        self.ttl_seconds = ttl_seconds
        self.id_getter = id_getter
        
        self._cache: list[T] | None = None
        self._cache_ts: float = 0.0

    def _cargar_sin_cache(self) -> list[T]:
        filas = self.client.leer_todos(self.sheet_name)
        return [self.from_dict(f) for f in filas]

    def listar_todos(self) -> list[T]:
        ahora = time.monotonic()
        if self._cache is None or (ahora - self._cache_ts) > self.ttl_seconds:
            self._cache = self._cargar_sin_cache()
            self._cache_ts = ahora
        return self._cache

    def obtener_por_id(self, id_: str) -> T | None:
        for entidad in self.listar_todos():
            if str(self.id_getter(entidad)) == str(id_):
                return entidad
        return None

    def guardar(self, entidad: T) -> None:
        id_val = self.id_getter(entidad)
        fila_dict = self.to_dict(entidad)
        
        actualizado = self.client.actualizar_fila(
            self.sheet_name, 
            self.columna_id, 
            id_val, 
            fila_dict
        )
        updated = actualizado
        if not updated:
            self.client.agregar_fila(self.sheet_name, fila_dict)
            
        self.invalidar_cache()

    def eliminar(self, id_: str) -> bool:
        eliminado = self.client.eliminar_fila(
            self.sheet_name,
            self.columna_id,
            str(id_)
        )
        self.invalidar_cache()
        return eliminado

    def invalidar_cache(self) -> None:
        self._cache = None
        self._cache_ts = 0.0
