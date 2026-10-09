from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from backoffice.auditoria import com_usuario
from backoffice.integracoes.base import AdaptadorSimulado
from backoffice.models import (
    AlertaMargem, Auditoria, Canal, Devolucao, EstoqueMovimento, FilaSync, HistoricoPreco, MargemProdutoCanal,
    Pedido, PedidoStatusHistorico, PendenciaMarketplace, ProdutoCanal, ReservaEstoque,
)
from backoffice.services import devolucoes
from backoffice.services.estoque import (
    EstoqueInsuficiente, ReservaInvalida, confirmar_reserva, definir_seguranca, disponivel, expirar_reservas,
    liberar_reserva, reservar, saldo_atual, vender,
)
from backoffice.services.pedidos import atualizar_pagamento, cancelar_pedido, registrar_pedido_site
from backoffice.services.pendencias import pendencias_marketplace
from backoffice.services.sincronizacao import MAX_TENTATIVAS, processar_fila, tentar_novamente

from .fabricas import criar_catalogo, criar_pedido_marketplace


class ReservaEEstoqueTests(TestCase):
    def setUp(self):
        self.c = criar_catalogo()
        self.produto = self.c["racao"]
        self.site = Canal.objects.get(codigo="site")

    def test_reserva_tira_do_disponivel_mas_nao_do_saldo(self):
        reservar(self.produto, 2, self.site, "carrinho-1")
        self.assertEqual((saldo_atual(self.produto), disponivel(self.produto)), (5, 3))

    def test_reserva_e_idempotente_por_referencia(self):
        primeira = reservar(self.produto, 2, self.site, "carrinho-1")
        segunda = reservar(self.produto, 2, self.site, "carrinho-1")
        self.assertEqual(primeira.pk, segunda.pk)
        self.assertEqual(disponivel(self.produto), 3)

    def test_nao_reserva_alem_do_disponivel(self):
        reservar(self.produto, 4, self.site, "a")
        with self.assertRaises(EstoqueInsuficiente) as contexto:
            reservar(self.produto, 2, self.site, "b")
        self.assertEqual(contexto.exception.disponivel, 1)

    def test_estoque_de_seguranca_nao_e_vendido(self):
        definir_seguranca(self.produto, 3)
        self.assertEqual(disponivel(self.produto), 2)
        with self.assertRaises(EstoqueInsuficiente):
            vender(self.produto, 3, "site:1")
        vender(self.produto, 2, "site:2")
        self.assertEqual((saldo_atual(self.produto), disponivel(self.produto)), (3, 0))

    def test_venda_respeita_o_que_esta_reservado(self):
        reservar(self.produto, 4, self.site, "a")
        with self.assertRaises(EstoqueInsuficiente):
            vender(self.produto, 2, "site:1")

    def test_confirmar_reserva_baixa_o_saldo_e_libera_a_reserva(self):
        reserva = reservar(self.produto, 2, self.site, "a")
        confirmar_reserva(reserva)
        self.assertEqual((saldo_atual(self.produto), disponivel(self.produto)), (3, 3))
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, "confirmada")
        self.assertEqual(self.produto.movimentos.first().referencia, "site:a")

    def test_liberar_devolve_o_disponivel(self):
        reserva = reservar(self.produto, 2, self.site, "a")
        liberar_reserva(reserva)
        self.assertEqual((saldo_atual(self.produto), disponivel(self.produto)), (5, 5))

    def test_reserva_encerrada_nao_pode_ser_usada_de_novo(self):
        reserva = reservar(self.produto, 2, self.site, "a")
        liberar_reserva(reserva)
        with self.assertRaises(ReservaInvalida):
            confirmar_reserva(reserva)
        with self.assertRaises(ReservaInvalida):
            liberar_reserva(reserva)

    def test_expirar_libera_so_as_vencidas(self):
        vencida = reservar(self.produto, 1, self.site, "velha", minutos=1)
        reservar(self.produto, 1, self.site, "nova", minutos=60)
        self.assertEqual(expirar_reservas(timezone.now() + timedelta(minutes=5)), 1)
        vencida.refresh_from_db()
        self.assertEqual(vencida.status, "expirada")
        self.assertEqual(disponivel(self.produto), 4)
        self.assertEqual(ReservaEstoque.objects.filter(status="ativa").count(), 1)

    def test_pedido_do_site_respeita_a_seguranca(self):
        definir_seguranca(self.produto, 4)
        with self.assertRaises(EstoqueInsuficiente):
            registrar_pedido_site(numero_externo="1", itens=[{"sku": "RAC-1", "quantidade": 2}])


class SincronizacaoTests(TestCase):
    def setUp(self):
        self.c = criar_catalogo()
        self.ml = Canal.objects.get(codigo="mercado_livre")
        self.linha = ProdutoCanal.objects.get(produto=self.c["bola"], canal=self.ml)
        FilaSync.objects.all().delete()

    def publicar(self):
        self.linha.publicado = True
        self.linha.save()

    def test_publicar_enfileira_e_mudar_preco_tambem(self):
        self.publicar()
        self.linha.preco = Decimal("35.00")
        self.linha.save()
        self.assertEqual(set(FilaSync.objects.values_list("tipo", flat=True)), {"publicacao", "preco"})

    def test_mudanca_no_site_nao_enfileira(self):
        ProdutoCanal.objects.filter(produto=self.c["bola"], canal__codigo="site").update(preco=Decimal("31.00"))
        self.assertEqual(FilaSync.objects.count(), 0)

    def test_mudar_so_o_status_de_sync_nao_enfileira(self):
        self.linha.status_sync = "erro"
        self.linha.save()
        self.assertEqual(FilaSync.objects.count(), 0)

    def test_estoque_enfileira_so_para_marketplaces_publicados(self):
        self.publicar()
        FilaSync.objects.all().delete()
        vender(self.c["bola"], 1, "site:1")
        self.assertEqual(list(FilaSync.objects.values_list("canal__codigo", "tipo")), [("mercado_livre", "estoque")])

    def test_pedidos_pendentes_iguais_viram_um_so(self):
        self.publicar()
        for preco in ("36.00", "37.00", "38.00"):
            self.linha.preco = Decimal(preco)
            self.linha.save()
        self.assertEqual(FilaSync.objects.filter(tipo="preco").count(), 1)

    def test_mudanca_durante_o_envio_gera_novo_item(self):
        self.publicar()
        FilaSync.objects.filter(tipo="publicacao").update(status="processando")
        self.linha.publicado = False
        self.linha.save()
        self.assertEqual(FilaSync.objects.filter(tipo="publicacao").count(), 2)

    def test_processar_envia_e_marca_como_sincronizado(self):
        self.publicar()
        adaptador = AdaptadorSimulado()
        resultado = processar_fila({"mercado_livre": adaptador})
        self.assertEqual((resultado.concluidos, resultado.falhas), (1, 0))
        self.assertEqual(adaptador.enviados, [("mercado_livre", "publicacao", "BOL-1")])
        self.linha.refresh_from_db()
        self.assertEqual(self.linha.status_sync, "sincronizado")
        self.assertIsNotNone(self.linha.sincronizado_em)
        self.assertEqual(FilaSync.objects.get().status, "concluida")

    def test_falha_agenda_nova_tentativa_com_espera_crescente(self):
        self.publicar()
        agora = timezone.now()
        processar_fila({"mercado_livre": AdaptadorSimulado(falhar_com="timeout")}, agora=agora)
        item = FilaSync.objects.get()
        self.assertEqual((item.status, item.tentativas, item.ultimo_erro), ("pendente", 1, "timeout"))
        self.assertEqual(item.proxima_tentativa_em, agora + timedelta(minutes=2))
        processar_fila({"mercado_livre": AdaptadorSimulado(falhar_com="timeout")}, agora=agora + timedelta(minutes=3))
        item.refresh_from_db()
        self.assertEqual((item.tentativas, item.proxima_tentativa_em), (2, agora + timedelta(minutes=3) + timedelta(minutes=4)))
        self.linha.refresh_from_db()
        self.assertEqual((self.linha.status_sync, self.linha.erro_sync), ("erro", "timeout"))

    def test_nao_tenta_antes_da_hora(self):
        self.publicar()
        agora = timezone.now()
        processar_fila({"mercado_livre": AdaptadorSimulado(falhar_com="x")}, agora=agora)
        resultado = processar_fila({"mercado_livre": AdaptadorSimulado()}, agora=agora + timedelta(seconds=30))
        self.assertEqual((resultado.concluidos, resultado.falhas), (0, 0))

    def test_esgota_as_tentativas_e_para(self):
        self.publicar()
        agora = timezone.now()
        resultado = None
        for rodada in range(MAX_TENTATIVAS):
            resultado = processar_fila({"mercado_livre": AdaptadorSimulado(falhar_com="x")}, agora=agora + timedelta(days=rodada))
        self.assertEqual(resultado.esgotados, 1)
        self.assertEqual(FilaSync.objects.get().status, "erro")
        vazio = processar_fila({"mercado_livre": AdaptadorSimulado()}, agora=agora + timedelta(days=30))
        self.assertEqual(vazio.concluidos, 0)

    def test_tentar_de_novo_recoloca_na_fila(self):
        self.publicar()
        agora = timezone.now()
        for rodada in range(MAX_TENTATIVAS):
            processar_fila({"mercado_livre": AdaptadorSimulado(falhar_com="x")}, agora=agora + timedelta(days=rodada))
        self.assertEqual(tentar_novamente(FilaSync.objects.all()), 1)
        resultado = processar_fila({"mercado_livre": AdaptadorSimulado()})
        self.assertEqual(resultado.concluidos, 1)

    def test_canal_sem_adaptador_fica_parado_na_fila(self):
        self.publicar()
        resultado = processar_fila({"amazon": AdaptadorSimulado()})
        self.assertEqual((resultado.concluidos, FilaSync.objects.get().status), (0, "pendente"))
        self.assertEqual(processar_fila({}).concluidos, 0)

    def test_item_travado_em_processando_volta_depois_do_prazo(self):
        self.publicar()
        processar_fila({"mercado_livre": AdaptadorSimulado()}, agora=timezone.now())
        FilaSync.objects.update(status="processando", proxima_tentativa_em=timezone.now() - timedelta(minutes=1))
        resultado = processar_fila({"mercado_livre": AdaptadorSimulado()})
        self.assertEqual(resultado.concluidos, 1)


class PedidosEPagamentoTests(TestCase):
    def setUp(self):
        self.c = criar_catalogo()

    def criar(self, numero="S-1", qtd=2, pagamento=None):
        return registrar_pedido_site(numero_externo=numero, itens=[{"sku": "BOL-1", "quantidade": qtd}], pagamento=pagamento).pedido

    def test_dados_de_pagamento_ficam_no_pedido(self):
        pedido = self.criar(pagamento={"forma": "pix", "parcelas": 1, "referencia": "tx-9"})
        self.assertEqual((pedido.forma_pagamento, pedido.pagamento_status, pedido.pagamento_referencia), ("pix", "pendente", "tx-9"))

    def test_forma_de_pagamento_invalida_e_recusada(self):
        from backoffice.services.pedidos import PedidoInvalido

        with self.assertRaises(PedidoInvalido):
            self.criar(pagamento={"forma": "fiado"})
        with self.assertRaises(PedidoInvalido):
            self.criar("S-2", pagamento={"forma": "pix", "parcelas": 0})

    def test_pagamento_aprovado_marca_como_pago(self):
        pedido = self.criar()
        atualizar_pagamento("S-1", "aprovado", "tx-1")
        pedido.refresh_from_db()
        self.assertEqual((pedido.status, pedido.pagamento_status, pedido.pagamento_referencia), ("pago", "aprovado", "tx-1"))

    def test_pagamento_recusado_cancela_e_devolve_o_estoque(self):
        self.criar(qtd=2)
        self.assertEqual(saldo_atual(self.c["bola"]), 48)
        atualizar_pagamento("S-1", "recusado")
        self.assertEqual(Pedido.objects.get().status, "cancelado")
        self.assertEqual(saldo_atual(self.c["bola"]), 50)

    def test_cancelar_duas_vezes_devolve_uma_vez(self):
        pedido = self.criar(qtd=2)
        cancelar_pedido(pedido)
        cancelar_pedido(pedido)
        self.assertEqual(saldo_atual(self.c["bola"]), 50)

    def test_historico_de_status_registra_cada_mudanca(self):
        self.criar()
        atualizar_pagamento("S-1", "aprovado")
        Pedido.objects.update(status="enviado")
        historico = list(PedidoStatusHistorico.objects.order_by("id").values_list("status_anterior", "status_novo"))
        self.assertEqual(historico, [(None, "novo"), ("novo", "pago"), ("pago", "enviado")])

    def test_status_de_pagamento_invalido(self):
        from backoffice.services.pedidos import PedidoInvalido

        self.criar()
        with self.assertRaises(PedidoInvalido):
            atualizar_pagamento("S-1", "talvez")


class DevolucaoTests(TestCase):
    def setUp(self):
        self.c = criar_catalogo()
        registrar_pedido_site(numero_externo="S-1", itens=[{"sku": "BOL-1", "quantidade": 3}])
        self.item = Pedido.objects.get().itens.get()

    def test_solicitar_valida_a_quantidade(self):
        devolucoes.solicitar(self.item, 2, "defeito")
        with self.assertRaisesMessage(devolucoes.DevolucaoInvalida, "até 1"):
            devolucoes.solicitar(self.item, 2, "defeito")
        with self.assertRaises(devolucoes.DevolucaoInvalida):
            devolucoes.solicitar(self.item, 0, "defeito")

    def test_devolucao_recusada_libera_a_quantidade(self):
        primeira = devolucoes.solicitar(self.item, 3, "outro")
        devolucoes.recusar(primeira)
        self.assertEqual(devolucoes.solicitar(self.item, 3, "outro").quantidade, 3)

    def test_fluxo_completo_devolve_ao_estoque_e_reembolsa(self):
        antes = saldo_atual(self.c["bola"])
        devolucao = devolucoes.solicitar(self.item, 2, "arrependimento")
        devolucoes.aprovar(devolucao)
        devolucoes.receber(devolucao)
        self.assertEqual(saldo_atual(self.c["bola"]), antes + 2)
        devolucoes.reembolsar(devolucao)
        devolucao.refresh_from_db()
        self.assertEqual((devolucao.status, devolucao.valor_reembolso), ("reembolsada", Decimal("60.00")))

    def test_nao_pula_etapas(self):
        devolucao = devolucoes.solicitar(self.item, 1, "defeito")
        with self.assertRaises(devolucoes.DevolucaoInvalida):
            devolucoes.receber(devolucao)
        with self.assertRaises(devolucoes.DevolucaoInvalida):
            devolucoes.reembolsar(devolucao)
        self.assertEqual(Devolucao.objects.get().status, "solicitada")

    def test_recebimento_so_acontece_uma_vez(self):
        devolucao = devolucoes.solicitar(self.item, 1, "defeito")
        devolucoes.aprovar(devolucao)
        devolucoes.receber(devolucao)
        antes = saldo_atual(self.c["bola"])
        with self.assertRaises(devolucoes.DevolucaoInvalida):
            devolucoes.receber(devolucao)
        self.assertEqual(saldo_atual(self.c["bola"]), antes)


class PromocaoComPrazoEMargemTests(TestCase):
    def setUp(self):
        self.c = criar_catalogo()
        self.linha = ProdutoCanal.objects.get(produto=self.c["racao"], canal__codigo="site")

    def test_promocao_so_vale_dentro_do_prazo(self):
        agora = timezone.now()
        casos = [
            (None, None, True), (agora - timedelta(days=1), agora + timedelta(days=1), True),
            (agora + timedelta(days=1), None, False), (None, agora - timedelta(hours=1), False),
        ]
        for inicio, fim, esperado in casos:
            self.linha.promo_inicio, self.linha.promo_fim = inicio, fim
            self.assertEqual(self.linha.promocao_ativa(agora), esperado)

    def test_margem_e_alerta(self):
        from backoffice.models import Produto

        Produto.objects.filter(pk=self.c["racao"].pk).update(custo=Decimal("70.00"))
        Canal.objects.filter(codigo="site").update(comissao_percentual=Decimal("10"), margem_minima_percentual=Decimal("20"))
        margem = MargemProdutoCanal.objects.get(produto=self.c["racao"], canal__codigo="site")
        self.assertEqual(margem.preco_vigente, Decimal("80.00"))
        self.assertEqual(margem.margem_percentual, Decimal("2.50"))
        self.assertEqual(AlertaMargem.objects.get().produto_id, self.c["racao"].pk)

    def test_sem_custo_nao_ha_alerta(self):
        self.assertEqual(AlertaMargem.objects.count(), 0)

    def test_promocao_expirada_usa_o_preco_cheio_na_margem(self):
        from backoffice.models import Produto

        Produto.objects.filter(pk=self.c["racao"].pk).update(custo=Decimal("50.00"))
        self.linha.promo_fim = timezone.now() - timedelta(hours=1)
        self.linha.save()
        self.assertEqual(MargemProdutoCanal.objects.get(produto=self.c["racao"], canal__codigo="site").preco_vigente, Decimal("100.00"))

    def test_constraint_do_periodo_da_promocao(self):
        from django.db import IntegrityError, transaction

        agora = timezone.now()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProdutoCanal.objects.filter(pk=self.linha.pk).update(promo_inicio=agora, promo_fim=agora - timedelta(days=1))

    def test_pedido_usa_o_preco_vigente(self):
        self.linha.promo_fim = timezone.now() - timedelta(hours=1)
        self.linha.save()
        pedido = registrar_pedido_site(numero_externo="P-1", itens=[{"sku": "RAC-1", "quantidade": 1}]).pedido
        self.assertEqual(pedido.subtotal, Decimal("100.00"))


class DadosParaMarketplaceTests(TestCase):
    def setUp(self):
        self.c = criar_catalogo()

    def test_pendencias_listam_o_que_falta(self):
        faltando = pendencias_marketplace(self.c["racao"])
        self.assertIn("GTIN/EAN", faltando)
        self.assertIn("NCM", faltando)
        self.assertIn("pelo menos uma imagem", faltando)

    def test_produto_completo_nao_tem_pendencias(self):
        from backoffice.models import ProdutoImagem

        produto = self.c["racao"]
        produto.gtin, produto.ncm, produto.peso_g = "7891234567895", "23091000", 15000
        produto.altura_cm = produto.largura_cm = produto.comprimento_cm = Decimal("30")
        produto.descricao = "Descrição longa o bastante para o marketplace aceitar."
        produto.save()
        ProdutoImagem.objects.create(produto=produto, url="https://exemplo.com/a.jpg")
        self.assertEqual(pendencias_marketplace(produto), [])
        self.assertFalse(PendenciaMarketplace.objects.filter(produto=produto, sem_imagem=True).exists())

    def test_banco_recusa_gtin_e_ncm_invalidos(self):
        from django.db import IntegrityError, transaction

        from backoffice.models import Produto

        for campo, valor in (("gtin", "123"), ("ncm", "1234"), ("peso_g", 0)):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Produto.objects.filter(pk=self.c["racao"].pk).update(**{campo: valor})

    def test_variacao_exige_grupo_e_nao_repete_no_grupo(self):
        from django.db import IntegrityError, transaction

        from backoffice.models import GrupoProduto, Produto

        with self.assertRaises(IntegrityError), transaction.atomic():
            Produto.objects.filter(pk=self.c["racao"].pk).update(variacao="15 kg")
        grupo = GrupoProduto.objects.create(slug="g", nome="G")
        Produto.objects.filter(pk=self.c["racao"].pk).update(grupo=grupo, variacao="15 kg")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Produto.objects.filter(pk=self.c["bola"].pk).update(grupo=grupo, variacao="15 kg")


class AuditoriaTests(TestCase):
    def setUp(self):
        self.c = criar_catalogo()
        self.linha = ProdutoCanal.objects.get(produto=self.c["racao"], canal__codigo="site")

    def test_historico_de_preco_guarda_quem_mudou(self):
        with com_usuario("maria"):
            self.linha.preco = Decimal("120.00")
            self.linha.save()
        self.assertEqual(HistoricoPreco.objects.get().usuario, "maria")

    def test_sem_usuario_o_autor_e_o_sistema(self):
        self.linha.preco = Decimal("120.00")
        self.linha.save()
        self.assertEqual(HistoricoPreco.objects.get().usuario, "sistema")

    def test_auditoria_guarda_so_as_colunas_alteradas(self):
        with com_usuario("maria"):
            self.linha.preco, self.linha.publicado = Decimal("120.00"), False
            self.linha.save()
        registro = Auditoria.objects.filter(tabela="produto_canal", acao="update").first()
        self.assertEqual(registro.usuario, "maria")
        self.assertEqual(set(registro.mudancas), {"preco", "publicado"})
        self.assertEqual(registro.mudancas["preco"], {"de": 100.0, "para": 120.0})

    def test_atualizacao_sem_mudanca_nao_gera_registro(self):
        antes = Auditoria.objects.count()
        self.linha.save()
        self.assertEqual(Auditoria.objects.count(), antes)

    def test_movimento_de_estoque_guarda_o_autor(self):
        with com_usuario("joao"):
            vender(self.c["bola"], 1, "site:1")
        self.assertEqual(EstoqueMovimento.objects.filter(motivo="venda").first().usuario, "joao")

    def test_hash_da_chave_nunca_vai_para_a_auditoria(self):
        from backoffice.services.chaves_api import gerar_chave

        gerar_chave("segredo", "site")
        registro = Auditoria.objects.filter(tabela="chave_api").first()
        self.assertNotIn("hash_chave", registro.mudancas)

    def test_exclusao_fica_registrada(self):
        from backoffice.models import Vitrine, VitrineItem

        item = VitrineItem.objects.create(vitrine=Vitrine.objects.get(codigo="destaques"), produto=self.c["bola"])
        with com_usuario("maria"):
            item.delete()
        self.assertEqual(Auditoria.objects.filter(tabela="vitrine_item", acao="delete").first().usuario, "maria")

    def test_contexto_nao_vaza_para_o_proximo_codigo(self):
        with com_usuario("maria"):
            pass
        self.linha.preco = Decimal("130.00")
        self.linha.save()
        self.assertEqual(HistoricoPreco.objects.get().usuario, "sistema")


class PedidoMarketplaceTests(TestCase):
    def test_cancelar_pedido_de_marketplace_nao_mexe_no_estoque_do_site(self):
        c = criar_catalogo()
        pedido, _ = criar_pedido_marketplace(c["bola"], quantidade=2)
        antes = saldo_atual(c["bola"])
        cancelar_pedido(pedido)
        self.assertEqual((Pedido.objects.get().status, saldo_atual(c["bola"])), ("cancelado", antes))
