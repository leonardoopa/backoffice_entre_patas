import logging

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse

from backoffice.models import (
    Animal, Departamento, Estoque, EstoqueMovimento, Marca, Produto, ProdutoCanal, Subdepartamento,
)
from backoffice.services.canais import garantir_canais
from backoffice.services.estoque import movimentar, saldo_atual
from backoffice.services.importacao_excel import PlanilhaInvalida, gerar_modelo_planilha, importar_planilha

from .base import pode_alterar_preco

logger = logging.getLogger(__name__)

TAMANHO_MAXIMO_PLANILHA = 5 * 1024 * 1024


@admin.register(Animal)
class AnimalAdmin(admin.ModelAdmin):
    list_display = ["nome", "slug", "emoji", "ordem", "ativo"]
    prepopulated_fields = {"slug": ("nome",)}


class SubdepartamentoInline(admin.TabularInline):
    model = Subdepartamento
    extra = 0
    prepopulated_fields = {"slug": ("nome",)}


@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):
    list_display = ["nome", "slug", "ordem", "ativo"]
    prepopulated_fields = {"slug": ("nome",)}
    inlines = [SubdepartamentoInline]


@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin):
    list_display = ["nome", "slug"]
    search_fields = ["nome"]
    prepopulated_fields = {"slug": ("nome",)}


class ProdutoCanalInline(admin.TabularInline):
    model = ProdutoCanal
    extra = 0
    can_delete = False
    fields = ["canal", "publicado", "preco", "preco_promocional", "id_externo", "status_sync", "sincronizado_em"]
    readonly_fields = ["canal", "id_externo", "status_sync", "sincronizado_em"]

    def get_readonly_fields(self, request, obj=None):
        extras = [] if pode_alterar_preco(request) else ["preco", "preco_promocional"]
        if not request.user.has_perm("backoffice.publicar_canal"):
            extras.append("publicado")
        return [*self.readonly_fields, *extras]

    def has_add_permission(self, request, obj=None):
        return False


class PlanilhaForm(forms.Form):
    arquivo = forms.FileField(label="Planilha (.xlsx)")
    apenas_validar = forms.BooleanField(label="Só validar, sem gravar", required=False, initial=True)

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Envie um arquivo .xlsx.")
        if arquivo.size > TAMANHO_MAXIMO_PLANILHA:
            raise forms.ValidationError("O arquivo passa de 5 MB.")
        return arquivo


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ["sku", "nome", "animal", "departamento", "marca", "preco_site", "saldo", "no_site", "ativo"]
    list_filter = ["animal", "departamento", "marca", "ativo"]
    search_fields = ["sku", "nome", "gtin"]
    list_select_related = ["animal", "departamento", "marca"]
    prepopulated_fields = {"slug": ("nome",)}
    autocomplete_fields = ["marca"]
    actions = ["ativar", "desativar", "publicar_no_site", "retirar_do_site"]
    change_list_template = "admin/backoffice/produto/change_list.html"
    fieldsets = [
        ("Identificação", {"fields": ["sku", "nome", "slug", "gtin", "descricao"]}),
        ("Classificação", {"fields": ["animal", "departamento", "subdepartamento", "marca"]}),
        ("Preço de referência", {"fields": ["custo", "preco"]}),
        ("Aparência no site", {"fields": ["tipo_arte", "cor_arte", "imagem_url", "avaliacao", "num_avaliacoes"]}),
        ("Situação", {"fields": ["ativo"]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("canais__canal").select_related("estoque")

    def get_inlines(self, request, obj):
        return [ProdutoCanalInline] if obj else []

    def get_readonly_fields(self, request, obj=None):
        return [] if obj is None or pode_alterar_preco(request) else ["custo", "preco"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            garantir_canais(obj, obj.preco, publicar_site=False)
            Estoque.objects.get_or_create(produto=obj, defaults={"quantidade": 0})
            messages.info(request, "Produto criado fora do site. Revise os preços por canal e publique quando estiver pronto.")

    @admin.display(description="Preço no site")
    def preco_site(self, obj):
        linha = next((c for c in obj.canais.all() if c.canal.codigo == "site"), None)
        return f"R$ {linha.preco_final:.2f}" if linha else "—"

    @admin.display(description="Saldo")
    def saldo(self, obj):
        estoque = getattr(obj, "estoque", None)
        return estoque.quantidade if estoque else 0

    @admin.display(description="No site", boolean=True)
    def no_site(self, obj):
        return any(c.publicado and c.canal.codigo == "site" for c in obj.canais.all())

    @admin.action(description="Ativar produtos selecionados")
    def ativar(self, request, queryset):
        self.message_user(request, f"{queryset.update(ativo=True)} produto(s) ativado(s).")

    @admin.action(description="Desativar produtos selecionados")
    def desativar(self, request, queryset):
        self.message_user(request, f"{queryset.update(ativo=False)} produto(s) desativado(s).")

    @admin.action(description="Publicar no site", permissions=["publicar"])
    def publicar_no_site(self, request, queryset):
        total = ProdutoCanal.objects.filter(produto__in=queryset, canal__codigo="site").update(publicado=True)
        logger.info("publicacao_em_lote canal=site publicados=%d usuario=%s", total, request.user.pk)
        self.message_user(request, f"{total} produto(s) publicado(s) no site.")

    @admin.action(description="Retirar do site", permissions=["publicar"])
    def retirar_do_site(self, request, queryset):
        total = ProdutoCanal.objects.filter(produto__in=queryset, canal__codigo="site").update(publicado=False)
        logger.info("despublicacao_em_lote canal=site retirados=%d usuario=%s", total, request.user.pk)
        self.message_user(request, f"{total} produto(s) retirado(s) do site.")

    def has_publicar_permission(self, request):
        return request.user.has_perm("backoffice.publicar_canal")

    def get_urls(self):
        return [
            path("importar/", self.admin_site.admin_view(self.importar_view), name="backoffice_produto_importar"),
            path("modelo/", self.admin_site.admin_view(self.modelo_view), name="backoffice_produto_modelo"),
            *super().get_urls(),
        ]

    def _exigir_importacao(self, request):
        if not request.user.has_perm("backoffice.importar_planilha"):
            raise PermissionDenied

    def modelo_view(self, request):
        self._exigir_importacao(request)
        resposta = HttpResponse(
            gerar_modelo_planilha(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resposta["Content-Disposition"] = 'attachment; filename="modelo-produtos.xlsx"'
        return resposta

    def importar_view(self, request):
        self._exigir_importacao(request)
        form = PlanilhaForm(request.POST or None, request.FILES or None)
        resultado = None
        if request.method == "POST" and form.is_valid():
            arquivo = form.cleaned_data["arquivo"]
            try:
                resultado = importar_planilha(
                    arquivo, nome_arquivo=arquivo.name, usuario=request.user.get_username(),
                    apenas_validar=form.cleaned_data["apenas_validar"],
                )
            except PlanilhaInvalida as erro:
                form.add_error("arquivo", str(erro))
        contexto = {
            **self.admin_site.each_context(request), "opts": self.model._meta, "title": "Importar planilha de produtos",
            "form": form, "resultado": resultado, "apenas_validar": form.cleaned_data.get("apenas_validar") if resultado else None,
            "voltar": reverse("admin:backoffice_produto_changelist"),
        }
        return render(request, "admin/backoffice/produto/importar.html", contexto)


class EstoqueMovimentoForm(forms.ModelForm):
    class Meta:
        model = EstoqueMovimento
        fields = ["produto", "quantidade", "motivo", "referencia"]

    def clean(self):
        dados = super().clean()
        produto, quantidade = dados.get("produto"), dados.get("quantidade")
        if produto and quantidade is not None:
            if quantidade == 0:
                raise forms.ValidationError("A quantidade não pode ser zero.")
            disponivel = saldo_atual(produto)
            if disponivel + quantidade < 0:
                raise forms.ValidationError(f"Estoque insuficiente: saldo atual {disponivel}.")
        return dados


@admin.register(EstoqueMovimento)
class EstoqueMovimentoAdmin(admin.ModelAdmin):
    form = EstoqueMovimentoForm
    list_display = ["criado_em", "produto", "quantidade", "motivo", "referencia"]
    list_filter = ["motivo"]
    search_fields = ["produto__sku", "produto__nome", "referencia"]
    autocomplete_fields = ["produto"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        movimento = movimentar(obj.produto, obj.quantidade, obj.motivo, obj.referencia)
        obj.pk, obj.criado_em = movimento.pk, movimento.criado_em
        obj._state.adding = False
