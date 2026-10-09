from django.db import models
from django.utils import timezone

from .catalogo import Produto


class Canal(models.Model):
    class Tipo(models.TextChoices):
        SITE = "site", "Site"
        MARKETPLACE = "marketplace", "Marketplace"

    codigo = models.SlugField(max_length=30, unique=True)
    nome = models.CharField(max_length=80)
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    comissao_percentual = models.DecimalField("comissão (%)", max_digits=5, decimal_places=2, default=0)
    margem_minima_percentual = models.DecimalField("margem mínima (%)", max_digits=5, decimal_places=2, default=10)
    ativo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "canal"
        ordering = ["id"]

    def __str__(self):
        return self.nome


class ProdutoCanal(models.Model):
    class StatusSync(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        SINCRONIZADO = "sincronizado", "Sincronizado"
        ERRO = "erro", "Erro"

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, db_column="produto_id", related_name="canais")
    canal = models.ForeignKey(Canal, on_delete=models.PROTECT, db_column="canal_id", related_name="produtos")
    publicado = models.BooleanField(default=False)
    preco = models.DecimalField(max_digits=10, decimal_places=2)
    preco_promocional = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    promo_inicio = models.DateTimeField("promoção começa em", null=True, blank=True)
    promo_fim = models.DateTimeField("promoção termina em", null=True, blank=True)
    id_externo = models.CharField("ID no canal", max_length=80, blank=True)
    status_sync = models.CharField(max_length=12, choices=StatusSync.choices, default=StatusSync.PENDENTE)
    erro_sync = models.TextField(blank=True)
    sincronizado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "produto_canal"
        ordering = ["canal_id"]
        verbose_name = "produto no canal"
        verbose_name_plural = "produtos nos canais"
        constraints = [models.UniqueConstraint(fields=["produto", "canal"], name="produto_canal_unico")]

    def __str__(self):
        return f"{self.produto.sku} @ {self.canal.codigo}"

    def promocao_ativa(self, agora=None) -> bool:
        agora = agora or timezone.now()
        return (
            self.preco_promocional is not None
            and (self.promo_inicio is None or self.promo_inicio <= agora)
            and (self.promo_fim is None or self.promo_fim > agora)
        )

    @property
    def preco_vigente(self):
        return self.preco_promocional if self.promocao_ativa() else self.preco


class HistoricoPreco(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, db_column="produto_id", related_name="historico_precos")
    canal = models.ForeignKey(Canal, on_delete=models.PROTECT, db_column="canal_id")
    preco_anterior = models.DecimalField(max_digits=10, decimal_places=2)
    preco_novo = models.DecimalField(max_digits=10, decimal_places=2)
    promo_anterior = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    promo_nova = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    usuario = models.CharField(max_length=150)
    criado_em = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "historico_preco"
        ordering = ["-criado_em"]
        verbose_name = "histórico de preço"
        verbose_name_plural = "histórico de preços"


class AnuncioExterno(models.Model):
    canal = models.ForeignKey(Canal, on_delete=models.PROTECT, db_column="canal_id")
    id_externo = models.CharField(max_length=80)
    sku_externo = models.CharField(max_length=80, blank=True)
    titulo = models.CharField(max_length=250, blank=True)
    preco = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    estoque = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, blank=True)
    produto = models.ForeignKey(
        Produto, on_delete=models.SET_NULL, null=True, blank=True, db_column="produto_id", related_name="anuncios",
    )
    bruto = models.JSONField(default=dict)
    importado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "anuncio_externo"
        ordering = ["-importado_em"]
        verbose_name = "anúncio externo"
        verbose_name_plural = "anúncios externos"

    def __str__(self):
        return f"{self.canal.codigo}:{self.id_externo}"


class FilaSync(models.Model):
    class Tipo(models.TextChoices):
        PRECO = "preco", "Preço"
        ESTOQUE = "estoque", "Estoque"
        PUBLICACAO = "publicacao", "Publicação"

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        PROCESSANDO = "processando", "Processando"
        CONCLUIDA = "concluida", "Concluída"
        ERRO = "erro", "Erro (esgotou as tentativas)"

    canal = models.ForeignKey(Canal, on_delete=models.PROTECT, db_column="canal_id")
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, db_column="produto_id", related_name="fila_sync")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDENTE)
    tentativas = models.SmallIntegerField(default=0)
    proxima_tentativa_em = models.DateTimeField(default=timezone.now)
    ultimo_erro = models.TextField(blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    concluida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "fila_sync"
        ordering = ["-criada_em"]
        verbose_name = "item da fila de sincronização"
        verbose_name_plural = "fila de sincronização"

    def __str__(self):
        return f"{self.canal.codigo}:{self.tipo}:{self.produto.sku}"


class _Margem(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.DO_NOTHING, db_column="produto_id", related_name="+")
    canal = models.ForeignKey(Canal, on_delete=models.DO_NOTHING, db_column="canal_id", related_name="+")
    preco_vigente = models.DecimalField(max_digits=10, decimal_places=2)
    custo = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    comissao_percentual = models.DecimalField(max_digits=5, decimal_places=2)
    margem_minima_percentual = models.DecimalField(max_digits=5, decimal_places=2)
    margem_percentual = models.DecimalField(max_digits=8, decimal_places=2, null=True)

    class Meta:
        abstract = True
        managed = False


class MargemProdutoCanal(_Margem):
    class Meta:
        managed = False
        db_table = "vw_margem_produto_canal"
        verbose_name = "margem por canal"
        verbose_name_plural = "margens por canal"
        default_permissions = ("view",)


class AlertaMargem(_Margem):
    class Meta:
        managed = False
        db_table = "vw_alerta_margem"
        ordering = ["margem_percentual"]
        verbose_name = "alerta de margem"
        verbose_name_plural = "alertas de margem"
        default_permissions = ("view",)
