import io
from decimal import Decimal

from django.contrib.auth.models import Group, User
from openpyxl import Workbook

from backoffice.models import Animal, Canal, Departamento, Marca, Produto, Subdepartamento
from backoffice.services.canais import definir_preco_site, garantir_canais
from backoffice.services.chaves_api import gerar_chave
from backoffice.services.estoque import definir_saldo

SENHA = "Senha!Forte-123"


def criar_taxonomia():
    caes = Animal.objects.create(slug="caes", nome="Cães", emoji="🐶")
    gatos = Animal.objects.create(slug="gatos", nome="Gatos", emoji="🐱")
    racoes = Departamento.objects.create(slug="racoes", nome="Rações")
    brinquedos = Departamento.objects.create(slug="brinquedos", nome="Brinquedos")
    seca = Subdepartamento.objects.create(departamento=racoes, slug="racao-seca", nome="Ração Seca")
    umida = Subdepartamento.objects.create(departamento=racoes, slug="racao-umida", nome="Ração Úmida")
    return {"caes": caes, "gatos": gatos, "racoes": racoes, "brinquedos": brinquedos, "seca": seca, "umida": umida}


def criar_produto(sku, nome, animal, preco="100.00", promo=None, estoque=10, departamento=None, sub=None,
                  marca=None, publicado=True, slug=None, ativo=True):
    marca_obj = Marca.objects.get_or_create(nome=marca, defaults={"slug": marca.lower()})[0] if marca else None
    produto = Produto.objects.create(
        sku=sku, slug=slug or sku.lower(), nome=nome, animal=animal, departamento=departamento, subdepartamento=sub,
        marca=marca_obj, preco=Decimal(preco), ativo=ativo,
    )
    promocional = Decimal(promo) if promo else None
    garantir_canais(produto, produto.preco, promocional)
    definir_preco_site(produto, produto.preco, promocional, publicado)
    definir_saldo(produto, estoque, "entrada")
    return produto


def criar_catalogo():
    t = criar_taxonomia()
    produtos = {
        "racao": criar_produto("RAC-1", "Ração Premium", t["caes"], "100.00", "80.00", 5, t["racoes"], t["seca"], "NutriPet"),
        "bola": criar_produto("BOL-1", "Bola", t["caes"], "30.00", None, 50, t["brinquedos"], None, "PataFeliz"),
        "gato": criar_produto("RAC-G", "Ração Gato", t["gatos"], "250.00", None, 9, t["racoes"], t["umida"], "NutriPet"),
        "oculto": criar_produto("OCU-1", "Produto oculto", t["caes"], "10.00", None, 5, publicado=False),
    }
    return {**t, **produtos}


def criar_chave(escopo="site"):
    return gerar_chave(f"teste-{escopo}", escopo)[1]


def cabecalho_auth(escopo="site"):
    return {"HTTP_AUTHORIZATION": f"Bearer {criar_chave(escopo)}"}


def criar_usuario(nome="ana", grupo=None, superuser=False):
    usuario = User.objects.create_user(nome, f"{nome}@example.com", SENHA, is_staff=True, is_superuser=superuser)
    if grupo:
        usuario.groups.add(Group.objects.get(name=grupo))
    return usuario


def planilha(linhas, colunas=None):
    colunas = colunas or ["sku", "nome", "animal", "preco", "preco_promocional", "estoque", "departamento", "subdepartamento", "marca"]
    livro = Workbook()
    folha = livro.active
    folha.append(colunas)
    for linha in linhas:
        folha.append(linha)
    saida = io.BytesIO()
    livro.save(saida)
    saida.seek(0)
    return saida
