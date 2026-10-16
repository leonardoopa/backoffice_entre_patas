import logging

from backoffice.models import FilaSync

from .contratos import ErroSincronizacao

logger = logging.getLogger(__name__)


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
