from typing import Protocol

from backoffice.models import FilaSync


class ErroSincronizacao(Exception):
    pass


class AdaptadorCanal(Protocol):
    def sincronizar(self, item: FilaSync) -> None: ...
