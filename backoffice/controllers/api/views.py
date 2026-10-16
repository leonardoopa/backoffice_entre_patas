import json
import logging
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db import connection
from django.http import JsonResponse, QueryDict
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from backoffice.models import Pedido
from backoffice.presenters import api as apresentador
from backoffice.repositories import site as consultas
from backoffice.services.estoque import EstoqueInsuficiente
from backoffice.services.pedidos import (
    PedidoInvalido, PedidoNaoEncontrado, atualizar_pagamento, registrar_pedido_site,
)

from .autenticacao import exige_escopo

logger = logging.getLogger(__name__)

LEITURA = ("site", "leitura")


def _escopo(params: QueryDict) -> consultas.Escopo:
    return consultas.Escopo(
        animal=params.get("escopo_animal", ""),
        departamento=params.get("escopo_departamento", ""),
        ofertas=params.get("escopo_ofertas") == "1",
        termo=params.get("q", "").strip(),
        skus=tuple(params.getlist("sku")),
    )


def _filtros(params: QueryDict) -> consultas.Filtros:
    faixa, ordem = params.get("faixa", ""), params.get("ordem", consultas.ORDEM_PADRAO)
    return consultas.Filtros(
        animais=tuple(params.getlist("animal")),
        departamentos=tuple(params.getlist("departamento")),
        subdepartamentos=tuple(params.getlist("subdepartamento")),
        marcas=tuple(params.getlist("marca")),
        faixa=faixa if faixa in consultas.FAIXAS else "",
        somente_ofertas=params.get("promo") == "1",
        ordem=ordem if ordem in consultas.ORDENACOES else consultas.ORDEM_PADRAO,
    )


def _numero(params, nome: str, padrao: int, maximo: int) -> int:
    try:
        return min(max(int(params.get(nome, padrao)), 1), maximo)
    except ValueError:
        return padrao


@require_GET
def saude(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})


@require_GET
@exige_escopo(*LEITURA)
def taxonomia(request):
    return JsonResponse({
        "animais": [
            {
                **apresentador.animal(entrada["animal"]),
                "departamentos": [
                    {
                        **apresentador.departamento(d["departamento"]),
                        "subdepartamentos": [apresentador.subdepartamento(s) for s in d["subdepartamentos"]],
                    }
                    for d in entrada["departamentos"]
                ],
            }
            for entrada in consultas.taxonomia_do_site()
        ],
    })


@require_GET
@exige_escopo(*LEITURA)
def produtos(request):
    escopo = _escopo(request.GET)
    filtros = _filtros(request.GET)
    base = consultas.aplicar_escopo(consultas.itens_do_site(), escopo)
    itens = consultas.aplicar_filtros(base, filtros)

    tamanho = _numero(request.GET, "tamanho", 24, consultas.MAXIMO_POR_PAGINA)
    pagina = Paginator(itens, tamanho).get_page(request.GET.get("pagina"))
    f = consultas.facetas(base, filtros)
    return JsonResponse({
        "total": pagina.paginator.count,
        "pagina": pagina.number,
        "paginas": pagina.paginator.num_pages,
        "tamanho": tamanho,
        "itens": [apresentador.produto(i) for i in pagina],
        "facetas": {
            "animais": [apresentador.animal(a) for a in f.animais],
            "departamentos": [apresentador.departamento(d) for d in f.departamentos],
            "subdepartamentos": [apresentador.subdepartamento(s) for s in f.subdepartamentos],
            "marcas": [{"slug": slug, "nome": nome} for slug, nome in f.marcas],
        },
    })


@require_GET
@exige_escopo(*LEITURA)
def produto(request, slug):
    item = consultas.item_por_slug(slug)
    if item is None:
        return JsonResponse({"erro": "Produto não encontrado."}, status=404)
    return JsonResponse(apresentador.produto_detalhe(item, consultas.variacoes_do_site(item)))


@require_GET
@exige_escopo(*LEITURA)
def vitrines(request):
    return JsonResponse({
        vitrine.codigo: {
            "nome": vitrine.nome,
            "itens": [apresentador.produto(i) for i in consultas.itens_da_vitrine(vitrine)],
        }
        for vitrine in consultas.vitrines_ativas()
    })


@csrf_exempt
@require_POST
@exige_escopo("site")
def criar_pedido(request):
    try:
        dados = json.loads(request.body or b"{}")
        numero = str(dados["numero_externo"]).strip()
        frete = Decimal(str(dados.get("frete", "0")))
        itens = dados["itens"]
    except (json.JSONDecodeError, KeyError, InvalidOperation, TypeError):
        return JsonResponse({"erro": "Corpo inválido: envie numero_externo, itens e frete."}, status=400)
    if not numero:
        return JsonResponse({"erro": "numero_externo é obrigatório."}, status=400)

    try:
        resultado = registrar_pedido_site(
            numero_externo=numero, itens=itens, cliente=dados.get("cliente"), entrega=dados.get("entrega"), frete=frete,
            pagamento=dados.get("pagamento"),
        )
    except EstoqueInsuficiente as erro:
        return JsonResponse(
            {"erro": "Estoque insuficiente.", "sku": erro.produto.sku, "disponivel": erro.disponivel}, status=409,
        )
    except PedidoInvalido as erro:
        return JsonResponse({"erro": str(erro), "sku": getattr(erro, "sku", None)}, status=422)

    pedido = resultado.pedido
    return JsonResponse(
        {"id": pedido.pk, "numero_externo": pedido.numero_externo, "total": apresentador.dinheiro(pedido.total)},
        status=201 if resultado.criado else 200,
    )


def _pedidos_com_detalhes():
    return Pedido.objects.select_related("canal", "cliente").prefetch_related("itens", "historico_status")


@require_GET
@exige_escopo(*LEITURA)
def pedido_detalhe(request, numero):
    try:
        pedido = _pedidos_com_detalhes().get(canal__codigo="site", numero_externo=numero)
    except Pedido.DoesNotExist:
        return JsonResponse({"erro": "Pedido não encontrado."}, status=404)
    return JsonResponse(apresentador.pedido(pedido))


@require_GET
@exige_escopo(*LEITURA)
def pedidos_do_cliente(request, id_externo):
    pedidos = _pedidos_com_detalhes().filter(canal__codigo="site", cliente__id_externo=id_externo).order_by("-comprado_em")[:100]
    return JsonResponse({"itens": [apresentador.pedido(p) for p in pedidos]})


@csrf_exempt
@require_POST
@exige_escopo("site")
def pedido_pagamento(request, numero):
    try:
        dados = json.loads(request.body or b"{}")
        status = str(dados["status"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return JsonResponse({"erro": "Corpo inválido: envie status e, se houver, referencia."}, status=400)
    try:
        pedido = atualizar_pagamento(numero, status, str(dados.get("referencia", "")))
    except PedidoNaoEncontrado:
        return JsonResponse({"erro": "Pedido não encontrado."}, status=404)
    except PedidoInvalido as erro:
        return JsonResponse({"erro": str(erro)}, status=422)
    return JsonResponse({"numero_externo": pedido.numero_externo, "status": pedido.status, "pagamento_status": pedido.pagamento_status})
