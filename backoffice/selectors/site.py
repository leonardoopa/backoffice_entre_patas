from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import OuterRef, Prefetch, Q, QuerySet, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import QueryDict
from django.utils import timezone

from backoffice.models import (
    Animal, Departamento, PedidoItem, ProdutoCanal, ProdutoImagem, Subdepartamento, Vitrine, VitrineItem,
)
from backoffice.precos import anotar_preco_vigente

ORDEM_PADRAO = "relevancia"
ORDENACOES = {
    "relevancia": ("-vendidas", "produto__nome"),
    "menor-preco": ("valor", "produto__nome"),
    "maior-preco": ("-valor", "produto__nome"),
    "nome": ("produto__nome",),
    "novidades": ("-produto__criado_em", "produto__nome"),
}
FAIXAS = {"ate-50": (None, 50), "50-100": (50, 100), "100-200": (100, 200), "acima-200": (200, None)}
MAXIMO_POR_PAGINA = 100


@dataclass(frozen=True)
class Escopo:
    animal: str = ""
    departamento: str = ""
    ofertas: bool = False
    termo: str = ""
    skus: tuple[str, ...] = ()

    @classmethod
    def de_querydict(cls, params: QueryDict) -> "Escopo":
        return cls(
            animal=params.get("escopo_animal", ""),
            departamento=params.get("escopo_departamento", ""),
            ofertas=params.get("escopo_ofertas") == "1",
            termo=params.get("q", "").strip(),
            skus=tuple(params.getlist("sku")),
        )


@dataclass(frozen=True)
class Filtros:
    animais: tuple[str, ...] = ()
    departamentos: tuple[str, ...] = ()
    subdepartamentos: tuple[str, ...] = ()
    marcas: tuple[str, ...] = ()
    faixa: str = ""
    somente_ofertas: bool = False
    ordem: str = ORDEM_PADRAO

    @classmethod
    def de_querydict(cls, params: QueryDict) -> "Filtros":
        faixa, ordem = params.get("faixa", ""), params.get("ordem", ORDEM_PADRAO)
        return cls(
            animais=tuple(params.getlist("animal")),
            departamentos=tuple(params.getlist("departamento")),
            subdepartamentos=tuple(params.getlist("subdepartamento")),
            marcas=tuple(params.getlist("marca")),
            faixa=faixa if faixa in FAIXAS else "",
            somente_ofertas=params.get("promo") == "1",
            ordem=ordem if ordem in ORDENACOES else ORDEM_PADRAO,
        )


@dataclass(frozen=True)
class Facetas:
    animais: list[Animal]
    departamentos: list[Departamento]
    subdepartamentos: list[Subdepartamento]
    marcas: list[tuple[str, str]]


def itens_do_site() -> QuerySet[ProdutoCanal]:
    desde = timezone.now() - timedelta(days=settings.PERIODO_MAIS_VENDIDOS_DIAS)
    vendidas = (
        PedidoItem.objects.filter(produto=OuterRef("produto_id"), pedido__comprado_em__gte=desde)
        .exclude(pedido__status="cancelado")
        .order_by()
        .values("produto")
        .annotate(total=Sum("quantidade"))
        .values("total")
    )
    itens = (
        ProdutoCanal.objects.filter(canal__codigo="site", publicado=True, produto__ativo=True)
        .select_related(
            "produto__marca", "produto__animal", "produto__departamento", "produto__subdepartamento",
            "produto__grupo", "produto__estoque",
        )
        .prefetch_related(Prefetch("produto__imagens", queryset=ProdutoImagem.objects.order_by("posicao", "id")))
    )
    return anotar_preco_vigente(itens).annotate(vendidas=Coalesce(Subquery(vendidas), 0))


def aplicar_escopo(itens: QuerySet[ProdutoCanal], escopo: Escopo) -> QuerySet[ProdutoCanal]:
    if escopo.animal:
        itens = itens.filter(produto__animal__slug=escopo.animal)
    if escopo.departamento:
        itens = itens.filter(produto__departamento__slug=escopo.departamento)
    if escopo.ofertas:
        itens = itens.filter(promo_ativa=True)
    if escopo.skus:
        itens = itens.filter(produto__sku__in=escopo.skus)
    if escopo.termo:
        termo = escopo.termo
        itens = itens.filter(
            Q(produto__nome__unaccent__icontains=termo)
            | Q(produto__marca__nome__unaccent__icontains=termo)
            | Q(produto__descricao__unaccent__icontains=termo)
            | Q(produto__sku__iexact=termo)
        )
    return itens


def aplicar_filtros(itens: QuerySet[ProdutoCanal], filtros: Filtros) -> QuerySet[ProdutoCanal]:
    if filtros.animais:
        itens = itens.filter(produto__animal__slug__in=filtros.animais)
    if filtros.departamentos:
        itens = itens.filter(produto__departamento__slug__in=filtros.departamentos)
    if filtros.subdepartamentos:
        itens = itens.filter(produto__subdepartamento__slug__in=filtros.subdepartamentos)
    if filtros.marcas:
        itens = itens.filter(produto__marca__slug__in=filtros.marcas)
    if filtros.somente_ofertas:
        itens = itens.filter(promo_ativa=True)
    if filtros.faixa:
        minimo, maximo = FAIXAS[filtros.faixa]
        if minimo is not None:
            itens = itens.filter(valor__gte=minimo)
        if maximo is not None:
            itens = itens.filter(valor__lt=maximo)
    return itens.order_by(*ORDENACOES[filtros.ordem])


def facetas(base: QuerySet[ProdutoCanal], filtros: Filtros) -> Facetas:
    departamentos = list(Departamento.objects.filter(pk__in=base.values("produto__departamento")))
    escopo_deps = list(filtros.departamentos) or ([d.slug for d in departamentos] if len(departamentos) == 1 else [])
    subs = (
        list(Subdepartamento.objects.filter(pk__in=base.values("produto__subdepartamento"), departamento__slug__in=escopo_deps))
        if escopo_deps else []
    )
    marcas = sorted(set(base.exclude(produto__marca__isnull=True).values_list("produto__marca__slug", "produto__marca__nome")), key=lambda m: m[1])
    return Facetas(
        animais=list(Animal.objects.filter(pk__in=base.values("produto__animal"))),
        departamentos=departamentos,
        subdepartamentos=subs,
        marcas=marcas,
    )


def item_por_slug(slug: str) -> ProdutoCanal | None:
    return itens_do_site().filter(produto__slug=slug).first()


def variacoes_do_site(item: ProdutoCanal) -> list[ProdutoCanal]:
    if item.produto.grupo_id is None:
        return []
    return list(itens_do_site().filter(produto__grupo_id=item.produto.grupo_id).order_by("valor", "produto__variacao"))


def taxonomia_do_site() -> list[dict]:
    combinacoes = (
        itens_do_site()
        .values_list("produto__animal_id", "produto__departamento_id", "produto__subdepartamento_id")
        .distinct()
    )
    mapa: dict[int, dict[int, set[int]]] = {}
    for animal_id, departamento_id, sub_id in combinacoes:
        if departamento_id is None:
            continue
        subs = mapa.setdefault(animal_id, {}).setdefault(departamento_id, set())
        if sub_id:
            subs.add(sub_id)

    departamentos = {d.pk: d for d in Departamento.objects.filter(ativo=True)}
    subdepartamentos = list(Subdepartamento.objects.all())
    saida = []
    for animal in Animal.objects.filter(ativo=True):
        entradas = [
            {"departamento": departamentos[dep_id], "subdepartamentos": [s for s in subdepartamentos if s.pk in subs]}
            for dep_id, subs in mapa.get(animal.pk, {}).items() if dep_id in departamentos
        ]
        entradas.sort(key=lambda e: (e["departamento"].ordem, e["departamento"].nome))
        saida.append({"animal": animal, "departamentos": entradas})
    return saida


def itens_da_vitrine(vitrine: Vitrine) -> list[ProdutoCanal]:
    itens = itens_do_site()
    if vitrine.modo == Vitrine.Modo.MANUAL:
        escolhidos = list(VitrineItem.objects.filter(vitrine=vitrine).order_by("posicao", "id").values_list("produto_id", flat=True))
        por_produto = {i.produto_id: i for i in itens.filter(produto_id__in=escolhidos)}
        return [por_produto[pk] for pk in escolhidos if pk in por_produto][: vitrine.limite]

    if vitrine.codigo == "ofertas":
        itens = itens.filter(promo_ativa=True).order_by("-vendidas", "produto__nome")
    elif vitrine.codigo == "mais_vendidos":
        itens = itens.filter(vendidas__gt=0).order_by("-vendidas", "produto__nome")
    else:
        itens = itens.order_by("-produto__num_avaliacoes", "produto__nome")
    resultado = list(itens[: vitrine.limite])
    if not resultado and vitrine.codigo == "mais_vendidos":
        resultado = list(itens_do_site().order_by("-produto__num_avaliacoes", "produto__nome")[: vitrine.limite])
    return resultado


def vitrines_ativas() -> list[Vitrine]:
    return list(Vitrine.objects.filter(ativa=True).order_by("id"))
