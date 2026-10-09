import logging
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from backoffice.models import (
    Animal, Canal, Cliente, Departamento, EstoqueMovimento, Marca, Pedido, PedidoItem, Produto, ProdutoCanal,
    Subdepartamento, Vitrine, VitrineItem,
)
from backoffice.services.canais import definir_preco_site, garantir_canais
from backoffice.services.estoque import definir_saldo

from ._catalogo_demo import ANIMAIS, DEPARTAMENTOS, PRODUTOS, SUBDEPARTAMENTOS, TEXTOS, ProdutoDemo

logger = logging.getLogger(__name__)

PEDIDOS_DEMO = 120
CHANCE_FORA_DO_SITE = 0.15
DIAS_DE_HISTORICO = 80
SOBRETAXA_MARKETPLACE = {"mercado_livre": Decimal("1.12"), "amazon": Decimal("1.15")}


class Command(BaseCommand):
    help = "Carrega catálogo, canais, estoque e vendas fictícias para demonstração (idempotente nos produtos)."

    @transaction.atomic
    def handle(self, *args, **options):
        animais = {
            slugify(nome): Animal.objects.update_or_create(
                slug=slugify(nome), defaults={"nome": nome, "emoji": emoji, "ordem": ordem},
            )[0]
            for ordem, (nome, emoji) in enumerate(ANIMAIS)
        }
        departamentos = {
            slug: Departamento.objects.update_or_create(slug=slug, defaults={"nome": nome, "ordem": ordem})[0]
            for ordem, (slug, nome) in enumerate(DEPARTAMENTOS.items())
        }
        subdepartamentos = {
            slug: Subdepartamento.objects.update_or_create(
                slug=slug, defaults={"departamento": departamentos[dep], "nome": nome, "ordem": ordem},
            )[0]
            for dep, itens in SUBDEPARTAMENTOS.items()
            for ordem, (slug, nome) in enumerate(itens)
        }
        produtos = [self._salvar_produto(item, animais, departamentos, subdepartamentos) for item in PRODUTOS]
        self._vitrine_destaques(produtos)
        if not Pedido.objects.exists():
            self._vendas_demo(produtos)

        resumo = f"{len(produtos)} produtos, {Pedido.objects.count()} pedidos de demonstração."
        logger.info("seed_demo_concluido %s", resumo)
        self.stdout.write(self.style.SUCCESS(resumo))

    def _salvar_produto(self, item: ProdutoDemo, animais, departamentos, subdepartamentos) -> Produto:
        marca, _ = Marca.objects.get_or_create(nome=item.marca, defaults={"slug": slugify(item.marca)})
        sorteio = random.Random(item.nome)
        produto, _ = Produto.objects.update_or_create(
            sku=f"EP-{slugify(item.nome)[:40].upper()}",
            defaults={
                "slug": slugify(item.nome), "nome": item.nome, "marca": marca,
                "descricao": f"{item.nome}, da {item.marca}. {TEXTOS[item.departamento]}",
                "animal": animais[item.animal], "departamento": departamentos[item.departamento],
                "subdepartamento": subdepartamentos[item.subdepartamento],
                "custo": (Decimal(item.preco) * Decimal("0.55")).quantize(Decimal("0.01")),
                "preco": Decimal(item.preco), "tipo_arte": item.tipo, "cor_arte": item.cor,
                "avaliacao": Decimal(str(round(sorteio.uniform(3.9, 5.0), 1))), "num_avaliacoes": sorteio.randint(8, 480),
                "ativo": True,
            },
        )
        promocional = Decimal(item.promocional) if item.promocional else None
        fora_do_site = sorteio.random() < CHANCE_FORA_DO_SITE
        garantir_canais(produto, produto.preco, promocional)
        definir_preco_site(produto, produto.preco, promocional, publicado=not fora_do_site)
        self._publicar_marketplaces(produto, sorteio, obrigatorio=fora_do_site)
        definir_saldo(produto, item.estoque, EstoqueMovimento.Motivo.ENTRADA, "seed_demo")
        return produto

    @staticmethod
    def _publicar_marketplaces(produto: Produto, sorteio: random.Random, obrigatorio: bool) -> None:
        for linha in ProdutoCanal.objects.filter(produto=produto, canal__tipo=Canal.Tipo.MARKETPLACE).select_related("canal"):
            fator = SOBRETAXA_MARKETPLACE.get(linha.canal.codigo, Decimal("1"))
            linha.preco = (produto.preco * fator).quantize(Decimal("0.01"))
            linha.publicado = obrigatorio or sorteio.random() < 0.6
            linha.save(update_fields=["preco", "publicado"])

    @staticmethod
    def _vitrine_destaques(produtos: list[Produto]) -> None:
        vitrine = Vitrine.objects.get(codigo="destaques")
        if vitrine.itens.exists():
            return
        destacados = [p for p, item in zip(produtos, PRODUTOS) if item.destaque]
        VitrineItem.objects.bulk_create(
            VitrineItem(vitrine=vitrine, produto=produto, posicao=posicao) for posicao, produto in enumerate(destacados)
        )

    @staticmethod
    def _vendas_demo(produtos: list[Produto]) -> None:
        sorteio = random.Random("vendas-demo")
        canais = list(Canal.objects.filter(ativo=True))
        pesos = {"site": 3, "mercado_livre": 5, "amazon": 2}
        agora = timezone.now()
        for numero in range(1, PEDIDOS_DEMO + 1):
            canal = sorteio.choices(canais, weights=[pesos.get(c.codigo, 1) for c in canais])[0]
            cliente, _ = Cliente.objects.get_or_create(
                canal=canal, id_externo=f"demo-{sorteio.randint(1, 60)}",
                defaults={"nome": f"Cliente demo {numero}", "email": f"cliente{numero}@example.com"},
            )
            escolhidos = sorteio.sample(produtos, k=sorteio.randint(1, 3))
            itens = [(p, sorteio.randint(1, 3)) for p in escolhidos]
            linhas = {
                p: ProdutoCanal.objects.get(produto=p, canal=canal).preco_final if canal.codigo == "site"
                else ProdutoCanal.objects.get(produto=p, canal=canal).preco
                for p, _ in itens
            }
            subtotal = sum(linhas[p] * qtd for p, qtd in itens)
            frete = Decimal("0") if subtotal >= 199 else Decimal("19.90")
            pedido = Pedido.objects.create(
                canal=canal, numero_externo=f"DEMO-{canal.codigo}-{numero}", cliente=cliente,
                status=sorteio.choices(["pago", "enviado", "entregue", "cancelado"], weights=[2, 3, 6, 1])[0],
                subtotal=subtotal, frete=frete, total=subtotal + frete, entrega={"cidade": "São Paulo", "uf": "SP"},
                comprado_em=agora - timedelta(days=sorteio.randint(0, DIAS_DE_HISTORICO), hours=sorteio.randint(0, 23)),
            )
            PedidoItem.objects.bulk_create(
                PedidoItem(pedido=pedido, produto=p, sku_externo=p.sku, descricao=p.nome, quantidade=qtd, preco_unitario=linhas[p])
                for p, qtd in itens
            )
