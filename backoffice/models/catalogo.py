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


class GrupoProduto(models.Model):
    slug = models.SlugField(max_length=160, unique=True)
    nome = models.CharField(max_length=160)

    class Meta:
        managed = False
        db_table = "grupo_produto"
        ordering = ["nome"]
        verbose_name = "grupo de variações"
        verbose_name_plural = "grupos de variações"

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
    grupo = models.ForeignKey(
        GrupoProduto, on_delete=models.SET_NULL, null=True, blank=True, db_column="grupo_id", related_name="produtos",
        verbose_name="grupo de variações",
    )
    variacao = models.CharField("variação", max_length=40, blank=True, help_text="Ex.: 10 kg, 500 ml, Tamanho M.")
    gtin = models.CharField("GTIN/EAN", max_length=14, blank=True)
    ncm = models.CharField("NCM", max_length=8, blank=True)
    peso_g = models.IntegerField("peso (g)", null=True, blank=True)
    altura_cm = models.DecimalField("altura (cm)", max_digits=6, decimal_places=1, null=True, blank=True)
    largura_cm = models.DecimalField("largura (cm)", max_digits=6, decimal_places=1, null=True, blank=True)
    comprimento_cm = models.DecimalField("comprimento (cm)", max_digits=6, decimal_places=1, null=True, blank=True)
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


class ProdutoImagem(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, db_column="produto_id", related_name="imagens")
    url = models.CharField("URL", max_length=500)
    posicao = models.SmallIntegerField("posição", default=0)

    class Meta:
        managed = False
        db_table = "produto_imagem"
        ordering = ["posicao", "id"]
        verbose_name = "imagem"
        verbose_name_plural = "imagens"

    def __str__(self):
        return self.url


class Estoque(models.Model):
    produto = models.OneToOneField(
        Produto, on_delete=models.CASCADE, primary_key=True, db_column="produto_id", related_name="estoque",
    )
    quantidade = models.IntegerField(default=0)
    reservado = models.IntegerField(default=0)
    seguranca = models.IntegerField("estoque de segurança", default=0)

    class Meta:
        managed = False
        db_table = "estoque"
        verbose_name_plural = "estoques"

    def __str__(self):
        return f"{self.produto.sku}: {self.disponivel} disponíveis"

    @property
    def disponivel(self) -> int:
        return max(self.quantidade - self.reservado - self.seguranca, 0)


class ReservaEstoque(models.Model):
    class Status(models.TextChoices):
        ATIVA = "ativa", "Ativa"
        CONFIRMADA = "confirmada", "Confirmada"
        LIBERADA = "liberada", "Liberada"
        EXPIRADA = "expirada", "Expirada"

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, db_column="produto_id", related_name="reservas")
    canal = models.ForeignKey("Canal", on_delete=models.PROTECT, db_column="canal_id")
    quantidade = models.IntegerField()
    referencia = models.CharField(max_length=80)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ATIVA)
    expira_em = models.DateTimeField()
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "reserva_estoque"
        ordering = ["-criada_em"]
        verbose_name = "reserva de estoque"
        verbose_name_plural = "reservas de estoque"
        constraints = [models.UniqueConstraint(fields=["canal", "referencia", "produto"], name="reserva_unica")]

    def __str__(self):
        return f"{self.produto.sku} x{self.quantidade} ({self.status})"


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
    usuario = models.CharField(max_length=150, default="sistema", editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "estoque_movimento"
        ordering = ["-criado_em"]
        verbose_name = "movimento de estoque"
        verbose_name_plural = "movimentos de estoque"

    def __str__(self):
        return f"{self.produto.sku} {self.quantidade:+d} ({self.motivo})"


class PendenciaMarketplace(models.Model):
    produto = models.OneToOneField(Produto, on_delete=models.DO_NOTHING, db_column="produto_id", related_name="+")
    sem_gtin = models.BooleanField()
    sem_ncm = models.BooleanField()
    sem_peso = models.BooleanField()
    sem_dimensoes = models.BooleanField()
    sem_marca = models.BooleanField()
    sem_imagem = models.BooleanField()
    descricao_curta = models.BooleanField()

    class Meta:
        managed = False
        db_table = "vw_pendencias_marketplace"
        verbose_name = "pendência para marketplaces"
        verbose_name_plural = "pendências para marketplaces"
        default_permissions = ("view",)
