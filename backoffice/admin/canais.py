from django.contrib import admin

from backoffice.models import AlertaMargem, AnuncioExterno, Canal, FilaSync, HistoricoPreco, MargemProdutoCanal
from backoffice.services.sincronizacao import tentar_novamente

from .base import SomenteLeitura


@admin.register(Canal)
class CanalAdmin(admin.ModelAdmin):
    list_display = ["nome", "codigo", "tipo", "comissao_percentual", "margem_minima_percentual", "ativo"]
    readonly_fields = ["codigo", "tipo"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HistoricoPreco)
class HistoricoPrecoAdmin(SomenteLeitura):
    list_display = ["criado_em", "produto", "canal", "preco_anterior", "preco_novo", "promo_anterior", "promo_nova", "usuario"]
    list_filter = ["canal", "usuario"]
    search_fields = ["produto__sku", "produto__nome"]
    list_select_related = ["produto", "canal"]


@admin.register(AnuncioExterno)
class AnuncioExternoAdmin(SomenteLeitura):
    list_display = ["canal", "id_externo", "sku_externo", "titulo", "preco", "estoque", "status", "produto"]
    list_filter = ["canal", "status"]
    search_fields = ["id_externo", "sku_externo", "titulo"]
    list_select_related = ["canal", "produto"]


@admin.register(FilaSync)
class FilaSyncAdmin(SomenteLeitura):
    list_display = ["criada_em", "canal", "tipo", "produto", "status", "tentativas", "proxima_tentativa_em", "ultimo_erro"]
    list_filter = ["status", "canal", "tipo"]
    search_fields = ["produto__sku", "ultimo_erro"]
    list_select_related = ["canal", "produto"]
    actions = ["tentar_de_novo"]

    @admin.action(description="Tentar de novo os itens com erro", permissions=["reenviar"])
    def tentar_de_novo(self, request, queryset):
        self.message_user(request, f"{tentar_novamente(queryset)} item(ns) voltaram para a fila.")

    def has_reenviar_permission(self, request):
        return request.user.has_perm("backoffice.publicar_canal")


class _MargemAdmin(SomenteLeitura):
    list_display = ["produto", "canal", "preco_vigente", "custo", "comissao_percentual", "margem_percentual", "margem_minima_percentual"]
    list_filter = ["canal"]
    search_fields = ["produto__sku", "produto__nome"]
    list_select_related = ["produto", "canal"]
    ordering = ["margem_percentual"]


@admin.register(MargemProdutoCanal)
class MargemProdutoCanalAdmin(_MargemAdmin):
    pass


@admin.register(AlertaMargem)
class AlertaMargemAdmin(_MargemAdmin):
    pass
