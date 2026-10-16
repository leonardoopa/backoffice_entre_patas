import re
from decimal import Decimal
from pathlib import Path

from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from backoffice.models import Canal, HistoricoPreco, OportunidadeSite, Pedido, PedidoItem, ProdutoCanal, VendaProdutoCanal, Vitrine
from backoffice.services.pedidos import registrar_pedido_site

from ..support.fabricas import criar_catalogo

RAIZ = Path(__file__).resolve().parents[3]


class EsquemaSqlTests(TestCase):
    def test_todo_arquivo_sql_esta_ligado_a_uma_migracao(self):
        texto_migracoes = "\n".join(p.read_text() for p in (RAIZ / "backoffice" / "migrations").glob("0*.py"))
        for arquivo in (RAIZ / "db" / "sql").glob("V*.sql"):
            self.assertIn(arquivo.name, texto_migracoes, f"{arquivo.name} não está em nenhuma migração")

    def test_nomes_dos_arquivos_sql_seguem_o_padrao(self):
        for arquivo in (RAIZ / "db" / "sql").glob("*.sql"):
            self.assertRegex(arquivo.name, re.compile(r"^V\d{4}__[a-z0-9_]+\.sql$"))

    def test_canais_e_vitrines_iniciais(self):
        self.assertEqual(set(Canal.objects.values_list("codigo", flat=True)), {"site", "mercado_livre", "amazon"})
        self.assertEqual(
            dict(Vitrine.objects.values_list("codigo", "modo")),
            {"ofertas": "automatico", "mais_vendidos": "automatico", "destaques": "manual"},
        )

    def test_constraint_impede_promocional_maior_que_preco(self):
        c = criar_catalogo()
        linha = ProdutoCanal.objects.get(produto=c["racao"], canal__codigo="site")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProdutoCanal.objects.filter(pk=linha.pk).update(preco_promocional=Decimal("999.00"))

    def test_constraint_impede_estoque_negativo(self):
        c = criar_catalogo()
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE estoque SET quantidade = -1 WHERE produto_id = %s", [c["racao"].pk])

    def test_trigger_registra_historico_de_preco(self):
        c = criar_catalogo()
        linha = ProdutoCanal.objects.get(produto=c["racao"], canal__codigo="site")
        linha.preco, linha.preco_promocional = Decimal("120.00"), Decimal("99.00")
        linha.save()
        historico = HistoricoPreco.objects.get(produto=c["racao"])
        self.assertEqual((historico.preco_anterior, historico.preco_novo), (Decimal("100.00"), Decimal("120.00")))
        self.assertEqual((historico.promo_anterior, historico.promo_nova), (Decimal("80.00"), Decimal("99.00")))

    def test_trigger_nao_registra_quando_preco_nao_muda(self):
        c = criar_catalogo()
        ProdutoCanal.objects.filter(produto=c["racao"], canal__codigo="site").update(publicado=False)
        self.assertEqual(HistoricoPreco.objects.count(), 0)

    def test_trigger_atualiza_o_timestamp_do_produto(self):
        c = criar_catalogo()
        antes = c["racao"].atualizado_em
        c["racao"].nome = "Ração Premium Plus"
        c["racao"].save()
        c["racao"].refresh_from_db()
        self.assertGreater(c["racao"].atualizado_em, antes)


class ViewsSqlTests(TestCase):
    def test_vendas_por_produto_e_canal_ignoram_cancelados(self):
        c = criar_catalogo()
        ml = Canal.objects.get(codigo="mercado_livre")
        for numero, status, qtd in (("1", "pago", 2), ("2", "cancelado", 5)):
            pedido = Pedido.objects.create(canal=ml, numero_externo=numero, status=status, comprado_em="2026-01-01T10:00:00Z")
            PedidoItem.objects.create(pedido=pedido, produto=c["bola"], quantidade=qtd, preco_unitario=Decimal("30.00"))
        venda = VendaProdutoCanal.objects.get(produto=c["bola"], canal=ml)
        self.assertEqual((venda.unidades, venda.receita), (2, Decimal("60.00")))

    def test_oportunidade_so_para_quem_vende_em_marketplace_e_nao_esta_no_site(self):
        c = criar_catalogo()
        ml, site = Canal.objects.get(codigo="mercado_livre"), Canal.objects.get(codigo="site")
        for produto, canal, numero in ((c["oculto"], ml, "1"), (c["bola"], ml, "2"), (c["racao"], site, "3")):
            pedido = Pedido.objects.create(canal=canal, numero_externo=numero, comprado_em="2026-01-01T10:00:00Z")
            PedidoItem.objects.create(pedido=pedido, produto=produto, quantidade=3, preco_unitario=Decimal("10.00"))
        self.assertEqual(list(OportunidadeSite.objects.values_list("produto__sku", flat=True)), ["OCU-1"])
        self.assertEqual(OportunidadeSite.objects.get().unidades_marketplaces, 3)

    def test_pedido_do_site_nao_gera_oportunidade(self):
        c = criar_catalogo()
        registrar_pedido_site(numero_externo="9", itens=[{"sku": c["bola"].sku, "quantidade": 1}])
        self.assertEqual(OportunidadeSite.objects.count(), 0)
