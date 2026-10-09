import json
import logging
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from backoffice.selectors import site as consultas
from backoffice.services.estoque import EstoqueInsuficiente
from backoffice.services.pedidos import PedidoInvalido, registrar_pedido_site

from . import serializers
from .autenticacao import exige_escopo

logger = logging.getLogger(__name__)

LEITURA = ("site", "leitura")


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
                **serializers.animal(entrada["animal"]),
                "departamentos": [
                    {
                        **serializers.departamento(d["departamento"]),
                        "subdepartamentos": [serializers.subdepartamento(s) for s in d["subdepartamentos"]],
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
    escopo = consultas.Escopo.de_querydict(request.GET)
    filtros = consultas.Filtros.de_querydict(request.GET)
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
        "itens": [serializers.produto(i) for i in pagina],
        "facetas": {
            "animais": [serializers.animal(a) for a in f.animais],
            "departamentos": [serializers.departamento(d) for d in f.departamentos],
            "subdepartamentos": [serializers.subdepartamento(s) for s in f.subdepartamentos],
            "marcas": [{"slug": slug, "nome": nome} for slug, nome in f.marcas],
        },
    })


@require_GET
@exige_escopo(*LEITURA)
def produto(request, slug):
    item = consultas.item_por_slug(slug)
    if item is None:
        return JsonResponse({"erro": "Produto não encontrado."}, status=404)
    return JsonResponse(serializers.produto(item))


@require_GET
@exige_escopo(*LEITURA)
def vitrines(request):
    return JsonResponse({
        vitrine.codigo: {
            "nome": vitrine.nome,
            "itens": [serializers.produto(i) for i in consultas.itens_da_vitrine(vitrine)],
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
        )
    except EstoqueInsuficiente as erro:
        return JsonResponse(
            {"erro": "Estoque insuficiente.", "sku": erro.produto.sku, "disponivel": erro.disponivel}, status=409,
        )
    except PedidoInvalido as erro:
        return JsonResponse({"erro": str(erro), "sku": getattr(erro, "sku", None)}, status=422)

    pedido = resultado.pedido
    return JsonResponse(
        {"id": pedido.pk, "numero_externo": pedido.numero_externo, "total": serializers.dinheiro(pedido.total)},
        status=201 if resultado.criado else 200,
    )
