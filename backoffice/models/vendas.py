from django.db import models

from .canais import Canal
from .catalogo import Produto


class Cliente(models.Model):
    canal = models.ForeignKey(Canal, on_delete=models.PROTECT, db_column="canal_id")
    id_externo = models.CharField(max_length=80)
    nome = models.CharField(max_length=120, blank=True)
    email = models.CharField(max_length=254, blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "cliente"
        ordering = ["-criado_em"]

    def __str__(self):
        return self.nome or self.email or self.id_externo


class Pedido(models.Model):
    class Status(models.TextChoices):
        NOVO = "novo", "Novo"
        PAGO = "pago", "Pago"
        ENVIADO = "enviado", "Enviado"
        ENTREGUE = "entregue", "Entregue"
        CANCELADO = "cancelado", "Cancelado"

    class FormaPagamento(models.TextChoices):
        NAO_INFORMADA = "", "Não informada"
        PIX = "pix", "Pix"
        CARTAO_CREDITO = "cartao_credito", "Cartão de crédito"
        CARTAO_DEBITO = "cartao_debito", "Cartão de débito"
        BOLETO = "boleto", "Boleto"
        MARKETPLACE = "marketplace", "Pago no marketplace"

    class PagamentoStatus(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        APROVADO = "aprovado", "Aprovado"
        RECUSADO = "recusado", "Recusado"
        ESTORNADO = "estornado", "Estornado"

    canal = models.ForeignKey(Canal, on_delete=models.PROTECT, db_column="canal_id", related_name="pedidos")
    numero_externo = models.CharField("número no canal", max_length=80)
    cliente = models.ForeignKey(
        Cliente, on_delete=models.SET_NULL, null=True, blank=True, db_column="cliente_id", related_name="pedidos",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NOVO)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frete = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    forma_pagamento = models.CharField(max_length=20, choices=FormaPagamento.choices, blank=True, default="")
    pagamento_status = models.CharField(max_length=10, choices=PagamentoStatus.choices, default=PagamentoStatus.PENDENTE)
    pagamento_referencia = models.CharField(max_length=120, blank=True)
    parcelas = models.SmallIntegerField(default=1)
    entrega = models.JSONField(default=dict, blank=True)
    comprado_em = models.DateTimeField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "pedido"
        ordering = ["-comprado_em"]
        constraints = [models.UniqueConstraint(fields=["canal", "numero_externo"], name="pedido_canal_numero_unico")]

    def __str__(self):
        return f"{self.canal.codigo} #{self.numero_externo}"


class PedidoItem(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, db_column="pedido_id", related_name="itens")
    produto = models.ForeignKey(
        Produto, on_delete=models.SET_NULL, null=True, blank=True, db_column="produto_id", related_name="itens_pedido",
    )
    sku_externo = models.CharField(max_length=80, blank=True)
    descricao = models.CharField(max_length=200, blank=True)
    quantidade = models.IntegerField()
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        managed = False
        db_table = "pedido_item"
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"

    @property
    def subtotal(self):
        return self.quantidade * self.preco_unitario


class PedidoStatusHistorico(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, db_column="pedido_id", related_name="historico_status")
    status_anterior = models.CharField(max_length=12, null=True, blank=True)
    status_novo = models.CharField(max_length=12)
    usuario = models.CharField(max_length=150)
    criado_em = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "pedido_status_historico"
        ordering = ["criado_em", "id"]
        verbose_name = "histórico de status"
        verbose_name_plural = "histórico de status"


class Devolucao(models.Model):
    class Motivo(models.TextChoices):
        ARREPENDIMENTO = "arrependimento", "Arrependimento"
        DEFEITO = "defeito", "Produto com defeito"
        ERRADO = "errado", "Produto errado"
        OUTRO = "outro", "Outro"

    class Status(models.TextChoices):
        SOLICITADA = "solicitada", "Solicitada"
        APROVADA = "aprovada", "Aprovada"
        RECEBIDA = "recebida", "Recebida (voltou ao estoque)"
        REEMBOLSADA = "reembolsada", "Reembolsada"
        RECUSADA = "recusada", "Recusada"

    pedido_item = models.ForeignKey(
        PedidoItem, on_delete=models.CASCADE, db_column="pedido_item_id", related_name="devolucoes",
        verbose_name="item do pedido",
    )
    quantidade = models.IntegerField()
    motivo = models.CharField(max_length=15, choices=Motivo.choices)
    observacao = models.TextField("observação", blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SOLICITADA)
    valor_reembolso = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "devolucao"
        ordering = ["-criada_em"]
        verbose_name = "devolução"
        verbose_name_plural = "devoluções"

    def __str__(self):
        return f"Devolução #{self.pk} ({self.status})"


class VendaProdutoCanal(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.DO_NOTHING, db_column="produto_id", related_name="+")
    canal = models.ForeignKey(Canal, on_delete=models.DO_NOTHING, db_column="canal_id", related_name="+")
    unidades = models.BigIntegerField()
    receita = models.DecimalField(max_digits=14, decimal_places=2)
    ultima_venda = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "vw_vendas_produto_canal"
        verbose_name = "venda por produto e canal"
        verbose_name_plural = "vendas por produto e canal"
        default_permissions = ("view",)


class OportunidadeSite(models.Model):
    produto = models.OneToOneField(Produto, on_delete=models.DO_NOTHING, db_column="produto_id", related_name="+")
    unidades_marketplaces = models.BigIntegerField()
    receita_marketplaces = models.DecimalField(max_digits=14, decimal_places=2)
    ultima_venda = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "vw_oportunidades_site"
        ordering = ["-receita_marketplaces"]
        verbose_name = "oportunidade para o site"
        verbose_name_plural = "oportunidades para o site"
        default_permissions = ("view",)
