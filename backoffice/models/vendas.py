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

    canal = models.ForeignKey(Canal, on_delete=models.PROTECT, db_column="canal_id", related_name="pedidos")
    numero_externo = models.CharField("número no canal", max_length=80)
    cliente = models.ForeignKey(
        Cliente, on_delete=models.SET_NULL, null=True, blank=True, db_column="cliente_id", related_name="pedidos",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NOVO)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frete = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
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
