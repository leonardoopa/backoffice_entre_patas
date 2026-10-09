import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from backoffice.models import Devolucao, EstoqueMovimento, PedidoItem

from .estoque import movimentar

logger = logging.getLogger(__name__)

TRANSICOES = {
    Devolucao.Status.SOLICITADA: {Devolucao.Status.APROVADA, Devolucao.Status.RECUSADA},
    Devolucao.Status.APROVADA: {Devolucao.Status.RECEBIDA, Devolucao.Status.RECUSADA},
    Devolucao.Status.RECEBIDA: {Devolucao.Status.REEMBOLSADA},
    Devolucao.Status.REEMBOLSADA: set(),
    Devolucao.Status.RECUSADA: set(),
}


class DevolucaoInvalida(Exception):
    pass


def validar_quantidade(item: PedidoItem, quantidade: int) -> None:
    ja_devolvido = (
        Devolucao.objects.filter(pedido_item=item).exclude(status=Devolucao.Status.RECUSADA)
        .aggregate(total=Sum("quantidade"))["total"] or 0
    )
    restante = item.quantidade - ja_devolvido
    if quantidade < 1 or quantidade > restante:
        raise DevolucaoInvalida(f"Só é possível devolver até {restante} unidade(s) deste item.")


@transaction.atomic
def solicitar(item: PedidoItem, quantidade: int, motivo: str, observacao: str = "") -> Devolucao:
    item = PedidoItem.objects.select_for_update().get(pk=item.pk)
    validar_quantidade(item, quantidade)
    devolucao = Devolucao.objects.create(pedido_item=item, quantidade=quantidade, motivo=motivo, observacao=observacao)
    logger.info("devolucao_solicitada devolucao=%s item=%s quantidade=%d", devolucao.pk, item.pk, quantidade)
    return devolucao


def _mudar(devolucao: Devolucao, novo: str) -> Devolucao:
    if novo not in TRANSICOES[devolucao.status]:
        raise DevolucaoInvalida(f"Não é possível passar de {devolucao.status} para {novo}.")
    devolucao.status = novo
    devolucao.save(update_fields=["status"])
    logger.info("devolucao_status devolucao=%s status=%s", devolucao.pk, novo)
    return devolucao


@transaction.atomic
def aprovar(devolucao: Devolucao) -> Devolucao:
    return _mudar(devolucao, Devolucao.Status.APROVADA)


@transaction.atomic
def recusar(devolucao: Devolucao) -> Devolucao:
    return _mudar(devolucao, Devolucao.Status.RECUSADA)


@transaction.atomic
def receber(devolucao: Devolucao) -> Devolucao:
    """Marca como recebida e devolve ao estoque quando o item ainda aponta para um produto do catálogo."""
    _mudar(devolucao, Devolucao.Status.RECEBIDA)
    item = devolucao.pedido_item
    if item.produto_id:
        movimentar(item.produto, devolucao.quantidade, EstoqueMovimento.Motivo.DEVOLUCAO, f"devolucao:{devolucao.pk}")
    return devolucao


@transaction.atomic
def reembolsar(devolucao: Devolucao, valor: Decimal | None = None) -> Devolucao:
    devolucao.valor_reembolso = valor if valor is not None else devolucao.pedido_item.preco_unitario * devolucao.quantidade
    devolucao.save(update_fields=["valor_reembolso"])
    return _mudar(devolucao, Devolucao.Status.REEMBOLSADA)
