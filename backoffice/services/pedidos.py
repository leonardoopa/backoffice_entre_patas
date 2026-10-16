import logging
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from backoffice.models import Canal, Cliente, EstoqueMovimento, Pedido, PedidoItem, Produto, ProdutoCanal
from backoffice.repositories.precos import anotar_preco_vigente

from .estoque import EstoqueInsuficiente, movimentar, vender

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
FORMAS_DE_PAGAMENTO = {valor for valor, _ in Pedido.FormaPagamento.choices}


class PedidoInvalido(Exception):
    pass


class ProdutoIndisponivel(PedidoInvalido):
    def __init__(self, sku: str):
        super().__init__(f"Produto indisponível no site: {sku}")
        self.sku = sku


class PedidoNaoEncontrado(Exception):
    pass


@dataclass(frozen=True)
class ResultadoPedido:
    pedido: Pedido
    criado: bool


def registrar_pedido_site(
    *,
    numero_externo: str,
    itens: list[Mapping[str, Any]],
    cliente: Mapping[str, str] | None = None,
    entrega: Mapping[str, Any] | None = None,
    frete: Decimal = ZERO,
    pagamento: Mapping[str, Any] | None = None,
) -> ResultadoPedido:
    if not itens:
        raise PedidoInvalido("O pedido não tem itens.")
    if frete < 0:
        raise PedidoInvalido("O frete não pode ser negativo.")
    forma, parcelas, referencia = _ler_pagamento(pagamento)
    canal = Canal.objects.get(codigo="site")

    existente = Pedido.objects.filter(canal=canal, numero_externo=numero_externo).first()
    if existente:
        logger.info("pedido_site_repetido numero=%s", numero_externo)
        return ResultadoPedido(existente, criado=False)

    quantidades = _somar_por_sku(itens)
    with transaction.atomic():
        linhas = _carregar_linhas(canal, quantidades)
        subtotal = sum((preco * qtd for _, qtd, preco in linhas), ZERO)
        pedido = Pedido.objects.create(
            canal=canal, numero_externo=numero_externo, cliente=_obter_cliente(canal, cliente),
            subtotal=subtotal, frete=frete, total=subtotal + frete,
            forma_pagamento=forma, parcelas=parcelas, pagamento_referencia=referencia,
            entrega=dict(entrega or {}), comprado_em=timezone.now(),
        )
        PedidoItem.objects.bulk_create(
            PedidoItem(pedido=pedido, produto=produto, sku_externo=produto.sku, descricao=produto.nome,
                       quantidade=qtd, preco_unitario=preco)
            for produto, qtd, preco in linhas
        )
        for produto, qtd, _ in linhas:
            vender(produto, qtd, f"site:{numero_externo}")
    logger.info("pedido_site_criado pedido=%s numero=%s itens=%d total=%s", pedido.pk, numero_externo, len(linhas), pedido.total)
    return ResultadoPedido(pedido, criado=True)


def atualizar_pagamento(numero_externo: str, status: str, referencia: str = "") -> Pedido:
    """Aplica o retorno do gateway: aprovado marca o pedido como pago; recusado ou estornado cancela e devolve o estoque."""
    if status not in Pedido.PagamentoStatus.values:
        raise PedidoInvalido(f"Status de pagamento inválido: {status}.")
    pedido = _buscar_site(numero_externo)
    with transaction.atomic():
        pedido.pagamento_status = status
        if referencia:
            pedido.pagamento_referencia = referencia
        pedido.save(update_fields=["pagamento_status", "pagamento_referencia"])
        if status == Pedido.PagamentoStatus.APROVADO and pedido.status == Pedido.Status.NOVO:
            pedido.status = Pedido.Status.PAGO
            pedido.save(update_fields=["status"])
        elif status in (Pedido.PagamentoStatus.RECUSADO, Pedido.PagamentoStatus.ESTORNADO):
            cancelar_pedido(pedido)
    logger.info("pagamento_atualizado pedido=%s status=%s", pedido.pk, status)
    return pedido


@transaction.atomic
def cancelar_pedido(pedido: Pedido) -> Pedido:
    """Cancela o pedido e devolve ao estoque o que ele havia baixado. Repetir a chamada não repete a devolução."""
    pedido = Pedido.objects.select_for_update().get(pk=pedido.pk)
    if pedido.status == Pedido.Status.CANCELADO:
        return pedido
    pedido.status = Pedido.Status.CANCELADO
    pedido.save(update_fields=["status"])
    for item in pedido.itens.select_related("produto"):
        if item.produto_id and pedido.canal.codigo == "site":
            movimentar(item.produto, item.quantidade, EstoqueMovimento.Motivo.DEVOLUCAO, f"cancelamento:{pedido.numero_externo}")
    logger.info("pedido_cancelado pedido=%s canal=%s", pedido.pk, pedido.canal.codigo)
    return pedido


def buscar_pedido_do_site(numero_externo: str) -> Pedido:
    return _buscar_site(numero_externo)


def _buscar_site(numero_externo: str) -> Pedido:
    pedido = Pedido.objects.select_related("canal", "cliente").filter(canal__codigo="site", numero_externo=numero_externo).first()
    if pedido is None:
        raise PedidoNaoEncontrado(numero_externo)
    return pedido


def _ler_pagamento(pagamento: Mapping[str, Any] | None) -> tuple[str, int, str]:
    pagamento = pagamento or {}
    forma = str(pagamento.get("forma", ""))
    if forma not in FORMAS_DE_PAGAMENTO:
        raise PedidoInvalido(f"Forma de pagamento inválida: {forma}.")
    try:
        parcelas = int(pagamento.get("parcelas", 1))
    except (TypeError, ValueError) as erro:
        raise PedidoInvalido("Número de parcelas inválido.") from erro
    if parcelas < 1:
        raise PedidoInvalido("Número de parcelas inválido.")
    return forma, parcelas, str(pagamento.get("referencia", ""))[:120]


def _somar_por_sku(itens: list[Mapping[str, Any]]) -> dict[str, int]:
    quantidades: dict[str, int] = {}
    for item in itens:
        try:
            sku, quantidade = str(item["sku"]), int(item["quantidade"])
        except (KeyError, TypeError, ValueError) as erro:
            raise PedidoInvalido("Item sem sku ou quantidade válida.") from erro
        if quantidade <= 0:
            raise PedidoInvalido(f"Quantidade inválida para {sku}.")
        quantidades[sku] = quantidades.get(sku, 0) + quantidade
    return quantidades


def _carregar_linhas(canal: Canal, quantidades: dict[str, int]) -> list[tuple[Produto, int, Decimal]]:
    publicados = {
        linha.produto.sku: linha
        for linha in anotar_preco_vigente(
            ProdutoCanal.objects.select_related("produto").filter(
                canal=canal, publicado=True, produto__ativo=True, produto__sku__in=quantidades,
            )
        )
    }
    linhas = []
    for sku, quantidade in quantidades.items():
        linha = publicados.get(sku)
        if linha is None:
            raise ProdutoIndisponivel(sku)
        linhas.append((linha.produto, quantidade, linha.valor))
    return linhas


def _obter_cliente(canal: Canal, dados: Mapping[str, str] | None) -> Cliente | None:
    if not dados or not dados.get("id_externo"):
        return None
    cliente, _ = Cliente.objects.update_or_create(
        canal=canal, id_externo=str(dados["id_externo"]),
        defaults={"nome": dados.get("nome", ""), "email": dados.get("email", ""), "telefone": dados.get("telefone", "")},
    )
    return cliente


__all__ = [
    "registrar_pedido_site", "atualizar_pagamento", "cancelar_pedido", "buscar_pedido_do_site",
    "PedidoInvalido", "ProdutoIndisponivel", "PedidoNaoEncontrado", "EstoqueInsuficiente", "ResultadoPedido",
]
