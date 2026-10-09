from decimal import Decimal

from django.db import models


class Animal(models.Model):
    slug = models.SlugField(max_length=50, unique=True)
    nome = models.CharField(max_length=80)
    emoji = models.CharField(max_length=8, blank=True)
    ordem = models.SmallIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "animal"
        ordering = ["ordem", "nome"]
        verbose_name_plural = "animais"

    def __str__(self):
        return self.nome


class Departamento(models.Model):
    slug = models.SlugField(max_length=50, unique=True)
    nome = models.CharField(max_length=80)
    ordem = models.SmallIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "departamento"
        ordering = ["ordem", "nome"]

    def __str__(self):
        return self.nome


class Subdepartamento(models.Model):
    departamento = models.ForeignKey(
        Departamento, on_delete=models.CASCADE, db_column="departamento_id", related_name="subdepartamentos",
    )
    slug = models.SlugField(max_length=60, unique=True)
    nome = models.CharField(max_length=80)
    ordem = models.SmallIntegerField(default=0)

    class Meta:
        managed = False
        db_table = "subdepartamento"
        ordering = ["departamento__ordem", "ordem", "nome"]
        verbose_name = "subdepartamento"

    def __str__(self):
        return f"{self.departamento} / {self.nome}"


class Marca(models.Model):
    slug = models.SlugField(max_length=80, unique=True)
    nome = models.CharField(max_length=80, unique=True)

    class Meta:
        managed = False
        db_table = "marca"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Produto(models.Model):
    class TipoArte(models.TextChoices):
        SACO = "saco", "Saco"
        LATA = "lata", "Lata"
        FRASCO = "frasco", "Frasco"
        BOLA = "bola", "Bola"
        OSSO = "osso", "Osso"
        CAIXA = "caixa", "Caixa"
        CAMA = "cama", "Cama"
        COLEIRA = "coleira", "Coleira"
        POTE = "pote", "Pote"

    sku = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=160, unique=True)
    nome = models.CharField(max_length=160)
    descricao = models.TextField(blank=True)
    marca = models.ForeignKey(Marca, on_delete=models.SET_NULL, null=True, blank=True, db_column="marca_id")
    animal = models.ForeignKey(Animal, on_delete=models.PROTECT, db_column="animal_id", related_name="produtos")
    departamento = models.ForeignKey(
        Departamento, on_delete=models.PROTECT, null=True, blank=True, db_column="departamento_id", related_name="produtos",
    )
    subdepartamento = models.ForeignKey(
        Subdepartamento, on_delete=models.PROTECT, null=True, blank=True, db_column="subdepartamento_id",
        related_name="produtos",
    )
    gtin = models.CharField("GTIN/EAN", max_length=14, blank=True)
    custo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    preco = models.DecimalField("preço de referência", max_digits=10, decimal_places=2)
    tipo_arte = models.CharField(max_length=10, choices=TipoArte.choices, default=TipoArte.CAIXA)
    cor_arte = models.CharField(max_length=7, default="#17375e")
    imagem_url = models.CharField("URL da imagem", max_length=500, blank=True)
    avaliacao = models.DecimalField(max_digits=2, decimal_places=1, default=Decimal("0"))
    num_avaliacoes = models.IntegerField(default=0)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "produto"
        ordering = ["nome"]
        permissions = [
            ("alterar_preco", "Pode alterar preços"),
            ("importar_planilha", "Pode importar planilhas de produtos"),
            ("publicar_canal", "Pode publicar produtos nos canais"),
        ]

    def __str__(self):
        return f"{self.sku} · {self.nome}"


class Estoque(models.Model):
    produto = models.OneToOneField(
        Produto, on_delete=models.CASCADE, primary_key=True, db_column="produto_id", related_name="estoque",
    )
    quantidade = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "estoque"
        verbose_name_plural = "estoques"

    def __str__(self):
        return f"{self.produto.sku}: {self.quantidade}"


class EstoqueMovimento(models.Model):
    class Motivo(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        VENDA = "venda", "Venda"
        AJUSTE = "ajuste", "Ajuste"
        DEVOLUCAO = "devolucao", "Devolução"
        IMPORTACAO = "importacao", "Importação"

    produto = models.ForeignKey(
        Produto, on_delete=models.CASCADE, db_column="produto_id", related_name="movimentos",
    )
    quantidade = models.IntegerField(help_text="Positivo entra no estoque, negativo sai.")
    motivo = models.CharField(max_length=12, choices=Motivo.choices)
    referencia = models.CharField(max_length=80, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "estoque_movimento"
        ordering = ["-criado_em"]
        verbose_name = "movimento de estoque"
        verbose_name_plural = "movimentos de estoque"

    def __str__(self):
        return f"{self.produto.sku} {self.quantidade:+d} ({self.motivo})"
