from django.contrib import admin

from backoffice.models import AnuncioExterno, Canal, HistoricoPreco

from .base import SomenteLeitura


@admin.register(Canal)
class CanalAdmin(admin.ModelAdmin):
    list_display = ["nome", "codigo", "tipo", "comissao_percentual", "ativo"]
    readonly_fields = ["codigo", "tipo"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HistoricoPreco)
class HistoricoPrecoAdmin(SomenteLeitura):
    list_display = ["criado_em", "produto", "canal", "preco_anterior", "preco_novo", "promo_anterior", "promo_nova"]
    list_filter = ["canal"]
    search_fields = ["produto__sku", "produto__nome"]
    list_select_related = ["produto", "canal"]


@admin.register(AnuncioExterno)
class AnuncioExternoAdmin(SomenteLeitura):
    list_display = ["canal", "id_externo", "sku_externo", "titulo", "preco", "estoque", "status", "produto"]
    list_filter = ["canal", "status"]
    search_fields = ["id_externo", "sku_externo", "titulo"]
    list_select_related = ["canal", "produto"]
