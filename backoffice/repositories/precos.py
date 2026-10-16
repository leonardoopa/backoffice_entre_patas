from django.db.models import BooleanField, DecimalField, F, Func, QuerySet


def anotar_preco_vigente(itens: QuerySet) -> QuerySet:
    """Acrescenta `valor` (preço em vigor) e `promo_ativa`, calculados pelo banco com as funções SQL do projeto."""
    return itens.annotate(
        valor=Func(
            F("preco"), F("preco_promocional"), F("promo_inicio"), F("promo_fim"),
            function="preco_vigente", output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
        promo_ativa=Func(
            F("preco_promocional"), F("promo_inicio"), F("promo_fim"),
            function="promocao_ativa", output_field=BooleanField(),
        ),
    )
