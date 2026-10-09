import logging
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from backoffice.models import Canal, Cliente, EstoqueMovimento, Pedido, PedidoItem, Produto, ProdutoCanal

from .estoque import EstoqueInsuficiente, movimentar

logger = logging.getLogger(__name__)

ZERO = Decimal("0")


class PedidoInvalido(Exception):
    pass


class ProdutoIndisponivel(PedidoInvalido):
    def __init__(self, sku: str):
        super().__init__(f"Produto indisponível no site: {sku}")
        self.sku = sku


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
) -> ResultadoPedido:
    if not itens:
        raise PedidoInvalido("O pedido não tem itens.")
    if frete < 0:
        raise PedidoInvalido("O frete não pode ser negativo.")
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
            entrega=dict(entrega or {}), comprado_em=timezone.now(),
        )
        PedidoItem.objects.bulk_create(
            PedidoItem(pedido=pedido, produto=produto, sku_externo=produto.sku, descricao=produto.nome,
                       quantidade=qtd, preco_unitario=preco)
            for produto, qtd, preco in linhas
        )
        for produto, qtd, _ in linhas:
            movimentar(produto, -qtd, EstoqueMovimento.Motivo.VENDA, f"site:{numero_externo}")
    logger.info("pedido_site_criado pedido=%s numero=%s itens=%d total=%s", pedido.pk, numero_externo, len(linhas), pedido.total)
    return ResultadoPedido(pedido, criado=True)


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
        for linha in ProdutoCanal.objects.select_related("produto")
        .filter(canal=canal, publicado=True, produto__ativo=True, produto__sku__in=quantidades)
    }
    linhas = []
    for sku, quantidade in quantidades.items():
        linha = publicados.get(sku)
        if linha is None:
            raise ProdutoIndisponivel(sku)
        linhas.append((linha.produto, quantidade, linha.preco_final))
    return linhas


def _obter_cliente(canal: Canal, dados: Mapping[str, str] | None) -> Cliente | None:
    if not dados or not dados.get("id_externo"):
        return None
    cliente, _ = Cliente.objects.update_or_create(
        canal=canal, id_externo=str(dados["id_externo"]),
        defaults={"nome": dados.get("nome", ""), "email": dados.get("email", ""), "telefone": dados.get("telefone", "")},
    )
    return cliente


__all__ = ["registrar_pedido_site", "PedidoInvalido", "ProdutoIndisponivel", "EstoqueInsuficiente", "ResultadoPedido"]
