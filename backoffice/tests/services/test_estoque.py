from django.test import TestCase

from backoffice.models import Estoque, EstoqueMovimento
from backoffice.services.estoque import EstoqueInsuficiente, definir_saldo, movimentar, saldo_atual

from ..support.fabricas import criar_catalogo


class EstoqueTests(TestCase):
    def setUp(self):
        self.produto = criar_catalogo()["racao"]

    def test_entrada_e_saida_atualizam_saldo_e_historico(self):
        movimentar(self.produto, 5, "entrada", "nf-1")
        movimentar(self.produto, -3, "venda", "pedido-1")
        self.assertEqual(saldo_atual(self.produto), 7)
        self.assertEqual(EstoqueMovimento.objects.filter(produto=self.produto).count(), 3)

    def test_nao_deixa_o_saldo_ficar_negativo(self):
        with self.assertRaises(EstoqueInsuficiente) as contexto:
            movimentar(self.produto, -6, "venda")
        self.assertEqual((contexto.exception.disponivel, contexto.exception.pedido), (5, 6))
        self.assertEqual(saldo_atual(self.produto), 5)

    def test_definir_saldo_registra_so_a_diferenca(self):
        definir_saldo(self.produto, 8, "ajuste")
        movimento = EstoqueMovimento.objects.filter(produto=self.produto).first()
        self.assertEqual((movimento.quantidade, saldo_atual(self.produto)), (3, 8))

    def test_definir_o_mesmo_saldo_nao_cria_movimento(self):
        antes = EstoqueMovimento.objects.count()
        definir_saldo(self.produto, 5, "ajuste")
        self.assertEqual(EstoqueMovimento.objects.count(), antes)

    def test_produto_sem_linha_de_estoque_comeca_do_zero(self):
        Estoque.objects.filter(produto=self.produto).delete()
        self.assertEqual(saldo_atual(self.produto), 0)
        movimentar(self.produto, 4, "entrada")
        self.assertEqual(saldo_atual(self.produto), 4)
