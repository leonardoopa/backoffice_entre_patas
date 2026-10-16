from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "EntrePatas Backoffice"
admin.site.site_title = "EntrePatas Backoffice"
admin.site.index_title = "Catálogo, canais e vendas"

urlpatterns = [
    path("api/v1/", include("backoffice.controllers.api.urls")),
    path("", admin.site.urls),
]
