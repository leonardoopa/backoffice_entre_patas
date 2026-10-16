from django.contrib import admin

from backoffice.models import Vitrine, VitrineItem


class VitrineItemInline(admin.TabularInline):
    model = VitrineItem
    extra = 1
    autocomplete_fields = ["produto"]
    ordering = ["posicao"]


@admin.register(Vitrine)
class VitrineAdmin(admin.ModelAdmin):
    list_display = ["nome", "codigo", "modo", "limite", "ativa"]
    readonly_fields = ["codigo"]
    inlines = [VitrineItemInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
