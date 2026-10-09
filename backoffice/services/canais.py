import logging
from decimal import Decimal

from backoffice.models import Canal, Produto, ProdutoCanal

logger = logging.getLogger(__name__)

CODIGO_SITE = "site"


def garantir_canais(
    produto: Produto,
    preco: Decimal,
    preco_promocional: Decimal | None = None,
    publicar_site: bool = True,
) -> list[ProdutoCanal]:
    """Cria a linha do produto em cada canal ativo que ainda não a tem. O site recebe o preço informado."""
    existentes = set(ProdutoCanal.objects.filter(produto=produto).values_list("canal_id", flat=True))
    criados = []
    for canal in Canal.objects.filter(ativo=True).exclude(pk__in=existentes):
        eh_site = canal.codigo == CODIGO_SITE
        criados.append(ProdutoCanal.objects.create(
            produto=produto,
            canal=canal,
            publicado=publicar_site if eh_site else False,
            preco=preco,
            preco_promocional=preco_promocional if eh_site else None,
        ))
    if criados:
        logger.info("produto_canais_criados sku=%s canais=%d", produto.sku, len(criados))
    return criados


def definir_preco_site(produto: Produto, preco: Decimal, preco_promocional: Decimal | None, publicado: bool) -> ProdutoCanal:
    canal = Canal.objects.get(codigo=CODIGO_SITE)
    linha, criada = ProdutoCanal.objects.get_or_create(
        produto=produto, canal=canal,
        defaults={"preco": preco, "preco_promocional": preco_promocional, "publicado": publicado},
    )
    if not criada:
        linha.preco, linha.preco_promocional, linha.publicado = preco, preco_promocional, publicado
        linha.save(update_fields=["preco", "preco_promocional", "publicado"])
    return linha
