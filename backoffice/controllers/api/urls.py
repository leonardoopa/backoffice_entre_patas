from django.urls import path

from . import views

urlpatterns = [
    path("saude/", views.saude),
    path("catalogo/taxonomia/", views.taxonomia),
    path("catalogo/produtos/", views.produtos),
    path("catalogo/produtos/<slug:slug>/", views.produto),
    path("vitrines/", views.vitrines),
    path("pedidos/", views.criar_pedido),
    path("pedidos/<str:numero>/", views.pedido_detalhe),
    path("pedidos/<str:numero>/pagamento/", views.pedido_pagamento),
    path("clientes/<str:id_externo>/pedidos/", views.pedidos_do_cliente),
]
