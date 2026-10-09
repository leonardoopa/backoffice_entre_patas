import logging

from django.contrib import admin, messages

from backoffice.models import Cliente, OportunidadeSite, Pedido, PedidoItem, VendaProdutoCanal
from backoffice.services.canais import definir_preco_site

from .base import SomenteLeitura

logger = logging.getLogger(__name__)


class PedidoItemInline(admin.TabularInline):
    model = PedidoItem
    extra = 0
    can_delete = False
    readonly_fields = ["produto", "sku_externo", "descricao", "quantidade", "preco_unitario"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ["id", "canal", "numero_externo", "cliente", "status", "total", "comprado_em"]
    list_filter = ["canal", "status", ("comprado_em", admin.DateFieldListFilter)]
    search_fields = ["numero_externo", "cliente__nome", "cliente__email"]
    list_select_related = ["canal", "cliente"]
    date_hierarchy = "comprado_em"
    inlines = [PedidoItemInline]
    readonly_fields = ["canal", "numero_externo", "cliente", "subtotal", "frete", "total", "entrega", "comprado_em"]
    fields = ["canal", "numero_externo", "cliente", "status", "subtotal", "frete", "total", "entrega", "comprado_em"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Cliente)
class ClienteAdmin(SomenteLeitura):
    list_display = ["nome", "email", "telefone", "canal", "criado_em"]
    list_filter = ["canal"]
    search_fields = ["nome", "email", "id_externo"]


@admin.register(VendaProdutoCanal)
class VendaProdutoCanalAdmin(SomenteLeitura):
    list_display = ["produto", "canal", "unidades", "receita", "ultima_venda"]
    list_filter = ["canal"]
    search_fields = ["produto__sku", "produto__nome"]
    list_select_related = ["produto", "canal"]
    ordering = ["-receita"]


@admin.register(OportunidadeSite)
class OportunidadeSiteAdmin(SomenteLeitura):
    list_display = ["produto", "unidades_marketplaces", "receita_marketplaces", "ultima_venda"]
    search_fields = ["produto__sku", "produto__nome"]
    list_select_related = ["produto"]
    actions = ["publicar_no_site"]

    @admin.action(description="Publicar no site com o preço de referência", permissions=["publicar"])
    def publicar_no_site(self, request, queryset):
        for oportunidade in queryset.select_related("produto"):
            produto = oportunidade.produto
            definir_preco_site(produto, produto.preco, None, publicado=True)
        logger.info("oportunidades_publicadas total=%d usuario=%s", queryset.count(), request.user.pk)
        self.message_user(request, f"{queryset.count()} produto(s) publicado(s) no site.", messages.SUCCESS)

    def has_publicar_permission(self, request):
        return request.user.has_perm("backoffice.publicar_canal")
