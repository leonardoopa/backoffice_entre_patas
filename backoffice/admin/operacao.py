from django.contrib import admin, messages

from backoffice.models import ChaveApi, ImportacaoPlanilha
from backoffice.services.chaves_api import gerar_chave

from .base import SomenteLeitura


@admin.register(ImportacaoPlanilha)
class ImportacaoPlanilhaAdmin(SomenteLeitura):
    list_display = ["criado_em", "arquivo", "usuario", "total", "criados", "atualizados", "qtd_erros"]
    readonly_fields = ["erros"]

    @admin.display(description="Erros")
    def qtd_erros(self, obj):
        return len(obj.erros)


@admin.register(ChaveApi)
class ChaveApiAdmin(admin.ModelAdmin):
    list_display = ["nome", "prefixo", "escopo", "ativa", "criada_em", "ultimo_uso_em"]
    list_filter = ["escopo", "ativa"]

    def get_fields(self, request, obj=None):
        return ["nome", "escopo", "ativa"] if obj else ["nome", "escopo"]

    def get_readonly_fields(self, request, obj=None):
        return ["nome", "escopo", "prefixo", "ultimo_uso_em"] if obj else []

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        registro, chave = gerar_chave(obj.nome, obj.escopo)
        obj.pk, obj.prefixo, obj.hash_chave = registro.pk, registro.prefixo, registro.hash_chave
        obj._state.adding = False
        messages.warning(request, f"Chave criada. Copie agora, ela não aparece de novo: {chave}")

    def has_delete_permission(self, request, obj=None):
        return False
