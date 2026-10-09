import logging
from typing import Protocol

from backoffice.models import FilaSync

logger = logging.getLogger(__name__)


class ErroSincronizacao(Exception):
    pass


class AdaptadorCanal(Protocol):
    def sincronizar(self, item: FilaSync) -> None: ...


class AdaptadorSimulado:
    """Registra no log o que enviaria. Serve para desenvolvimento e testes, nunca fala com um marketplace."""

    def __init__(self, falhar_com: str | None = None):
        self.falhar_com = falhar_com
        self.enviados: list[tuple[str, str, str]] = []

    def sincronizar(self, item: FilaSync) -> None:
        if self.falhar_com:
            raise ErroSincronizacao(self.falhar_com)
        self.enviados.append((item.canal.codigo, item.tipo, item.produto.sku))
        logger.info("sync_simulada canal=%s tipo=%s sku=%s", item.canal.codigo, item.tipo, item.produto.sku)


def adaptadores_padrao(simulados: bool) -> dict[str, AdaptadorCanal]:
    if not simulados:
        return {}
    adaptador = AdaptadorSimulado()
    return {"mercado_livre": adaptador, "amazon": adaptador}
