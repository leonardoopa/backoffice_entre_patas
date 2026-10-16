import logging

from django.contrib import admin, messages

from django import forms
from django.core.exceptions import PermissionDenied

from backoffice.models import (
    Cliente, Devolucao, OportunidadeSite, Pedido, PedidoItem, PedidoStatusHistorico, VendaProdutoCanal,
)
from backoffice.services import devolucoes as servico_devolucoes
from backoffice.services.canais import definir_preco_site
from backoffice.services.pedidos import cancelar_pedido

from .base import SomenteLeitura

logger = logging.getLogger(__name__)


class PedidoItemInline(admin.TabularInline):
    model = PedidoItem
    extra = 0
    can_delete = False
    readonly_fields = ["produto", "sku_externo", "descricao", "quantidade", "preco_unitario"]

    def has_add_permission(self, request, obj=None):
        return False


class HistoricoStatusInline(admin.TabularInline):
    model = PedidoStatusHistorico
    extra = 0
    can_delete = False
    readonly_fields = ["criado_em", "status_anterior", "status_novo", "usuario"]
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ["id", "canal", "numero_externo", "cliente", "status", "total", "comprado_em"]
    list_filter = ["canal", "status", ("comprado_em", admin.DateFieldListFilter)]
    search_fields = ["numero_externo", "cliente__nome", "cliente__email"]
    list_select_related = ["canal", "cliente"]
    date_hierarchy = "comprado_em"
    inlines = [PedidoItemInline, HistoricoStatusInline]
    readonly_fields = [
        "canal", "numero_externo", "cliente", "subtotal", "frete", "total", "forma_pagamento", "pagamento_status",
        "pagamento_referencia", "parcelas", "entrega", "comprado_em",
    ]
    fields = [
        "canal", "numero_externo", "cliente", "status", "subtotal", "frete", "total", "forma_pagamento",
        "pagamento_status", "pagamento_referencia", "parcelas", "entrega", "comprado_em",
    ]

    def save_model(self, request, obj, form, change):
        if change and "status" in form.changed_data and obj.status == Pedido.Status.CANCELADO:
            cancelar_pedido(obj)
            messages.info(request, "Pedido cancelado. O estoque do site foi devolvido.")
            return
        super().save_model(request, obj, form, change)

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


class DevolucaoForm(forms.ModelForm):
    class Meta:
        model = Devolucao
        fields = ["pedido_item", "quantidade", "motivo", "observacao"]

    def clean(self):
        dados = super().clean()
        item, quantidade = dados.get("pedido_item"), dados.get("quantidade")
        if item and quantidade and not self.instance.pk:
            try:
                servico_devolucoes.validar_quantidade(item, quantidade)
            except servico_devolucoes.DevolucaoInvalida as erro:
                raise forms.ValidationError(str(erro)) from erro
        return dados


@admin.register(Devolucao)
class DevolucaoAdmin(admin.ModelAdmin):
    form = DevolucaoForm
    list_display = ["id", "criada_em", "pedido_item", "quantidade", "motivo", "status", "valor_reembolso"]
    list_filter = ["status", "motivo"]
    search_fields = ["pedido_item__pedido__numero_externo", "pedido_item__sku_externo"]
    raw_id_fields = ["pedido_item"]
    actions = ["aprovar", "recusar", "receber", "reembolsar"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        criada = servico_devolucoes.solicitar(obj.pedido_item, obj.quantidade, obj.motivo, obj.observacao)
        obj.pk, obj.status, obj.criada_em, obj.atualizada_em = criada.pk, criada.status, criada.criada_em, criada.atualizada_em
        obj._state.adding = False

    def _aplicar(self, request, queryset, funcao, rotulo):
        if not request.user.has_perm("backoffice.change_devolucao"):
            raise PermissionDenied
        feitas = 0
        for devolucao in queryset:
            try:
                funcao(devolucao)
                feitas += 1
            except servico_devolucoes.DevolucaoInvalida as erro:
                self.message_user(request, f"#{devolucao.pk}: {erro}", messages.WARNING)
        self.message_user(request, f"{feitas} devolução(ões) {rotulo}.")

    @admin.action(description="Aprovar")
    def aprovar(self, request, queryset):
        self._aplicar(request, queryset, servico_devolucoes.aprovar, "aprovada(s)")

    @admin.action(description="Recusar")
    def recusar(self, request, queryset):
        self._aplicar(request, queryset, servico_devolucoes.recusar, "recusada(s)")

    @admin.action(description="Marcar como recebida (devolve ao estoque)")
    def receber(self, request, queryset):
        self._aplicar(request, queryset, servico_devolucoes.receber, "recebida(s)")

    @admin.action(description="Marcar como reembolsada")
    def reembolsar(self, request, queryset):
        self._aplicar(request, queryset, servico_devolucoes.reembolsar, "reembolsada(s)")
