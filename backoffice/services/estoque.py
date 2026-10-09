import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from backoffice.models import Canal, Estoque, EstoqueMovimento, Produto, ReservaEstoque

logger = logging.getLogger(__name__)

MINUTOS_DE_RESERVA = 30


class EstoqueInsuficiente(Exception):
    def __init__(self, produto: Produto, disponivel: int, pedido: int):
        super().__init__(f"Estoque insuficiente para {produto.sku}: disponível {disponivel}, pedido {pedido}")
        self.produto = produto
        self.disponivel = disponivel
        self.pedido = pedido


class ReservaInvalida(Exception):
    pass


def _travar(produto: Produto) -> Estoque:
    estoque, _ = Estoque.objects.select_for_update().get_or_create(produto=produto, defaults={"quantidade": 0})
    return estoque


@transaction.atomic
def movimentar(produto: Produto, quantidade: int, motivo: str, referencia: str = "") -> EstoqueMovimento:
    estoque = _travar(produto)
    if estoque.quantidade + quantidade < 0:
        logger.warning("estoque_insuficiente sku=%s disponivel=%d pedido=%d", produto.sku, estoque.quantidade, -quantidade)
        raise EstoqueInsuficiente(produto, estoque.quantidade, -quantidade)
    estoque.quantidade += quantidade
    estoque.save(update_fields=["quantidade"])
    movimento = EstoqueMovimento.objects.create(produto=produto, quantidade=quantidade, motivo=motivo, referencia=referencia)
    logger.info("estoque_movimentado sku=%s delta=%+d motivo=%s saldo=%d", produto.sku, quantidade, motivo, estoque.quantidade)
    return movimento


@transaction.atomic
def vender(produto: Produto, quantidade: int, referencia: str) -> EstoqueMovimento:
    """Baixa estoque respeitando o que está reservado e o estoque de segurança."""
    estoque = _travar(produto)
    if estoque.disponivel < quantidade:
        logger.warning("venda_sem_estoque sku=%s disponivel=%d pedido=%d", produto.sku, estoque.disponivel, quantidade)
        raise EstoqueInsuficiente(produto, estoque.disponivel, quantidade)
    return movimentar(produto, -quantidade, EstoqueMovimento.Motivo.VENDA, referencia)


def saldo_atual(produto: Produto) -> int:
    return Estoque.objects.filter(produto=produto).values_list("quantidade", flat=True).first() or 0


def disponivel(produto: Produto) -> int:
    estoque = Estoque.objects.filter(produto=produto).first()
    return estoque.disponivel if estoque else 0


def definir_saldo(produto: Produto, saldo: int, motivo: str, referencia: str = "") -> None:
    atual = saldo_atual(produto)
    if saldo != atual:
        movimentar(produto, saldo - atual, motivo, referencia)


def definir_seguranca(produto: Produto, quantidade: int) -> None:
    Estoque.objects.update_or_create(produto=produto, defaults={"seguranca": quantidade})


@transaction.atomic
def reservar(produto: Produto, quantidade: int, canal: Canal, referencia: str, minutos: int = MINUTOS_DE_RESERVA) -> ReservaEstoque:
    existente = ReservaEstoque.objects.filter(
        produto=produto, canal=canal, referencia=referencia, status=ReservaEstoque.Status.ATIVA,
    ).first()
    if existente:
        return existente
    estoque = _travar(produto)
    if estoque.disponivel < quantidade:
        raise EstoqueInsuficiente(produto, estoque.disponivel, quantidade)
    estoque.reservado += quantidade
    estoque.save(update_fields=["reservado"])
    reserva = ReservaEstoque.objects.create(
        produto=produto, canal=canal, quantidade=quantidade, referencia=referencia,
        expira_em=timezone.now() + timedelta(minutes=minutos),
    )
    logger.info("estoque_reservado sku=%s canal=%s quantidade=%d referencia=%s", produto.sku, canal.codigo, quantidade, referencia)
    return reserva


def _reserva_ativa(reserva: ReservaEstoque) -> ReservaEstoque:
    atual = ReservaEstoque.objects.select_for_update().get(pk=reserva.pk)
    if atual.status != ReservaEstoque.Status.ATIVA:
        raise ReservaInvalida(f"A reserva {atual.pk} está {atual.status}.")
    return atual


@transaction.atomic
def confirmar_reserva(reserva: ReservaEstoque) -> EstoqueMovimento:
    reserva = _reserva_ativa(reserva)
    estoque = _travar(reserva.produto)
    estoque.reservado -= reserva.quantidade
    estoque.save(update_fields=["reservado"])
    reserva.status = ReservaEstoque.Status.CONFIRMADA
    reserva.save(update_fields=["status"])
    return movimentar(reserva.produto, -reserva.quantidade, EstoqueMovimento.Motivo.VENDA, f"{reserva.canal.codigo}:{reserva.referencia}")


@transaction.atomic
def liberar_reserva(reserva: ReservaEstoque, status: str = ReservaEstoque.Status.LIBERADA) -> None:
    reserva = _reserva_ativa(reserva)
    estoque = _travar(reserva.produto)
    estoque.reservado -= reserva.quantidade
    estoque.save(update_fields=["reservado"])
    reserva.status = status
    reserva.save(update_fields=["status"])
    logger.info("estoque_reserva_encerrada sku=%s status=%s referencia=%s", reserva.produto.sku, status, reserva.referencia)


def expirar_reservas(agora=None) -> int:
    agora = agora or timezone.now()
    vencidas = ReservaEstoque.objects.filter(status=ReservaEstoque.Status.ATIVA, expira_em__lte=agora).select_related("produto")
    total = 0
    for reserva in vencidas:
        try:
            liberar_reserva(reserva, ReservaEstoque.Status.EXPIRADA)
            total += 1
        except ReservaInvalida:
            continue
    return total
