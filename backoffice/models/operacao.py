from django.db import models


class ImportacaoPlanilha(models.Model):
    arquivo = models.CharField(max_length=200)
    usuario = models.CharField(max_length=150)
    total = models.IntegerField(default=0)
    criados = models.IntegerField(default=0)
    atualizados = models.IntegerField(default=0)
    erros = models.JSONField(default=list)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "importacao_planilha"
        ordering = ["-criado_em"]
        verbose_name = "importação de planilha"
        verbose_name_plural = "importações de planilha"
        default_permissions = ("view",)

    def __str__(self):
        return f"{self.arquivo} ({self.criado_em:%d/%m/%Y %H:%M})"


class ChaveApi(models.Model):
    class Escopo(models.TextChoices):
        SITE = "site", "Site (lê catálogo e envia pedidos)"
        LEITURA = "leitura", "Somente leitura"

    nome = models.CharField(max_length=80)
    prefixo = models.CharField(max_length=8, unique=True, editable=False)
    hash_chave = models.CharField(max_length=64, editable=False)
    escopo = models.CharField(max_length=10, choices=Escopo.choices)
    ativa = models.BooleanField(default=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    ultimo_uso_em = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        managed = False
        db_table = "chave_api"
        ordering = ["-criada_em"]
        verbose_name = "chave de API"
        verbose_name_plural = "chaves de API"

    def __str__(self):
        return f"{self.nome} ({self.prefixo}…)"


class Auditoria(models.Model):
    tabela = models.CharField(max_length=40)
    registro_id = models.BigIntegerField()
    acao = models.CharField(max_length=6)
    usuario = models.CharField(max_length=150)
    mudancas = models.JSONField()
    criado_em = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "auditoria"
        ordering = ["-criado_em", "-id"]
        verbose_name = "registro de auditoria"
        verbose_name_plural = "auditoria"
        default_permissions = ("view",)

    def __str__(self):
        return f"{self.tabela}#{self.registro_id} {self.acao} por {self.usuario}"
