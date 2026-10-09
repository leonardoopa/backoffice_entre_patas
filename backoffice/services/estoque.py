import logging

from django.db import transaction

from backoffice.models import Estoque, EstoqueMovimento, Produto

logger = logging.getLogger(__name__)


class EstoqueInsuficiente(Exception):
    def __init__(self, produto: Produto, disponivel: int, pedido: int):
        super().__init__(f"Estoque insuficiente para {produto.sku}: disponível {disponivel}, pedido {pedido}")
        self.produto = produto
        self.disponivel = disponivel
        self.pedido = pedido


@transaction.atomic
def movimentar(produto: Produto, quantidade: int, motivo: str, referencia: str = "") -> EstoqueMovimento:
    estoque, _ = Estoque.objects.select_for_update().get_or_create(produto=produto, defaults={"quantidade": 0})
    if estoque.quantidade + quantidade < 0:
        logger.warning("estoque_insuficiente sku=%s disponivel=%d pedido=%d", produto.sku, estoque.quantidade, -quantidade)
        raise EstoqueInsuficiente(produto, estoque.quantidade, -quantidade)
    estoque.quantidade += quantidade
    estoque.save(update_fields=["quantidade"])
    movimento = EstoqueMovimento.objects.create(produto=produto, quantidade=quantidade, motivo=motivo, referencia=referencia)
    logger.info("estoque_movimentado sku=%s delta=%+d motivo=%s saldo=%d", produto.sku, quantidade, motivo, estoque.quantidade)
    return movimento


def saldo_atual(produto: Produto) -> int:
    return Estoque.objects.filter(produto=produto).values_list("quantidade", flat=True).first() or 0


def definir_saldo(produto: Produto, saldo: int, motivo: str, referencia: str = "") -> None:
    atual = saldo_atual(produto)
    if saldo != atual:
        movimentar(produto, saldo - atual, motivo, referencia)
