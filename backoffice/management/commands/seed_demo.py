import logging
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from backoffice.models import (
    Animal, Canal, Cliente, Departamento, EstoqueMovimento, GrupoProduto, Marca, Pedido, PedidoItem, Produto,
    ProdutoCanal, Subdepartamento, Vitrine, VitrineItem,
)
from backoffice.services.canais import definir_preco_site, garantir_canais
from backoffice.services import devolucoes
from backoffice.services.estoque import definir_saldo, definir_seguranca

from ._catalogo_demo import ANIMAIS, DEPARTAMENTOS, PRODUTOS, SUBDEPARTAMENTOS, TEXTOS, ProdutoDemo

logger = logging.getLogger(__name__)

PEDIDOS_DEMO = 120
CHANCE_FORA_DO_SITE = 0.15
CHANCE_DADOS_LOGISTICOS = 0.6
COMISSOES = {"mercado_livre": (Decimal("16"), Decimal("15")), "amazon": (Decimal("15"), Decimal("15"))}
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
        self._configurar_canais()
        produtos = [self._salvar_produto(item, animais, departamentos, subdepartamentos) for item in PRODUTOS]
        self._vitrine_destaques(produtos)
        if not Pedido.objects.exists():
            self._vendas_demo(produtos)
            self._devolucoes_demo()

        resumo = f"{len(produtos)} produtos, {Pedido.objects.count()} pedidos de demonstração."
        logger.info("seed_demo_concluido %s", resumo)
        self.stdout.write(self.style.SUCCESS(resumo))

    @staticmethod
    def _configurar_canais() -> None:
        for codigo, (comissao, margem) in COMISSOES.items():
            Canal.objects.filter(codigo=codigo).update(comissao_percentual=comissao, margem_minima_percentual=margem)

    def _salvar_produto(self, item: ProdutoDemo, animais, departamentos, subdepartamentos) -> Produto:
        marca, _ = Marca.objects.get_or_create(nome=item.marca, defaults={"slug": slugify(item.marca)})
        sorteio = random.Random(item.nome)
        produto, _ = Produto.objects.update_or_create(
            slug=slugify(item.nome),
            defaults={
                "sku": f"EP-{slugify(item.nome)[:52].upper()}", "nome": item.nome, "marca": marca,
                "descricao": f"{item.nome}, da {item.marca}. {TEXTOS[item.departamento]}",
                "animal": animais[item.animal], "departamento": departamentos[item.departamento],
                "subdepartamento": subdepartamentos[item.subdepartamento],
                "custo": (Decimal(item.preco) * Decimal(str(sorteio.choice([0.5, 0.55, 0.6, 0.9])))).quantize(Decimal("0.01")),
                "preco": Decimal(item.preco), "tipo_arte": item.tipo, "cor_arte": item.cor,
                "avaliacao": Decimal(str(round(sorteio.uniform(3.9, 5.0), 1))), "num_avaliacoes": sorteio.randint(8, 480),
                "ativo": True,
            },
        )
        self._dados_logisticos(produto, sorteio)
        if item.grupo:
            grupo, _ = GrupoProduto.objects.get_or_create(slug=slugify(item.grupo), defaults={"nome": item.grupo})
            Produto.objects.filter(pk=produto.pk).update(grupo=grupo, variacao=item.variacao)
        promocional = Decimal(item.promocional) if item.promocional else None
        fora_do_site = sorteio.random() < CHANCE_FORA_DO_SITE
        garantir_canais(produto, produto.preco, promocional)
        definir_preco_site(produto, produto.preco, promocional, publicado=not fora_do_site)
        self._publicar_marketplaces(produto, sorteio, obrigatorio=fora_do_site)
        self._prazo_da_promocao(produto, sorteio)
        definir_saldo(produto, item.estoque, EstoqueMovimento.Motivo.ENTRADA, "seed_demo")
        definir_seguranca(produto, sorteio.choice([0, 0, 2, 3]))
        return produto

    @staticmethod
    def _dados_logisticos(produto: Produto, sorteio: random.Random) -> None:
        if sorteio.random() >= CHANCE_DADOS_LOGISTICOS:
            return
        Produto.objects.filter(pk=produto.pk).update(
            gtin=f"789{sorteio.randint(10**9, 10**10 - 1)}", ncm=sorteio.choice(["23091000", "42010000", "39269090"]),
            peso_g=sorteio.randint(150, 15000), altura_cm=Decimal(sorteio.randint(5, 45)),
            largura_cm=Decimal(sorteio.randint(5, 40)), comprimento_cm=Decimal(sorteio.randint(8, 60)),
        )

    @staticmethod
    def _prazo_da_promocao(produto: Produto, sorteio: random.Random) -> None:
        agora = timezone.now()
        ProdutoCanal.objects.filter(produto=produto, canal__codigo="site", preco_promocional__isnull=False).update(
            promo_inicio=agora - timedelta(days=2), promo_fim=sorteio.choice([None, agora + timedelta(days=5), agora + timedelta(days=12)]),
        )

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
                p: ProdutoCanal.objects.get(produto=p, canal=canal).preco_vigente if canal.codigo == "site"
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

    @staticmethod
    def _devolucoes_demo() -> None:
        sorteio = random.Random("devolucoes-demo")
        itens = list(PedidoItem.objects.filter(pedido__status="entregue", produto__isnull=False)[:40])
        for item in sorteio.sample(itens, k=min(4, len(itens))):
            devolucao = devolucoes.solicitar(item, 1, sorteio.choice(["arrependimento", "defeito", "errado"]))
            if sorteio.random() < 0.5:
                devolucoes.aprovar(devolucao)
