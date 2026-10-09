from django.db import models

from .catalogo import Produto


class Vitrine(models.Model):
    class Modo(models.TextChoices):
        MANUAL = "manual", "Manual (produtos escolhidos)"
        AUTOMATICO = "automatico", "Automático (regra do sistema)"

    codigo = models.SlugField(max_length=30, unique=True)
    nome = models.CharField(max_length=80)
    modo = models.CharField(max_length=10, choices=Modo.choices, default=Modo.AUTOMATICO)
    limite = models.SmallIntegerField(default=12)
    ativa = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "vitrine"
        ordering = ["id"]

    def __str__(self):
        return self.nome


class VitrineItem(models.Model):
    vitrine = models.ForeignKey(Vitrine, on_delete=models.CASCADE, db_column="vitrine_id", related_name="itens")
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, db_column="produto_id", related_name="vitrines")
    posicao = models.SmallIntegerField(default=0)

    class Meta:
        managed = False
        db_table = "vitrine_item"
        ordering = ["posicao", "id"]
        verbose_name = "item da vitrine"
        verbose_name_plural = "itens da vitrine"
        constraints = [models.UniqueConstraint(fields=["vitrine", "produto"], name="vitrine_item_unico")]

    def __str__(self):
        return f"{self.vitrine.codigo}: {self.produto.sku}"
