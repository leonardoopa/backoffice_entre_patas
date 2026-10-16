from django.contrib import admin


class SomenteLeitura(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


def pode_alterar_preco(request) -> bool:
    return request.user.has_perm("backoffice.alterar_preco")
