import io
import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, BinaryIO

from django.db import transaction
from openpyxl import Workbook, load_workbook

from backoffice.models import (
    Animal, Departamento, EstoqueMovimento, ImportacaoPlanilha, Marca, Produto, Subdepartamento,
)
from backoffice.texto import normalizar, slugificar

from .canais import definir_preco_site, garantir_canais
from .estoque import definir_saldo

logger = logging.getLogger(__name__)

LIMITE_LINHAS = 5000
OBRIGATORIAS = ("sku", "nome", "animal", "preco")
COLUNAS = (
    "sku", "nome", "descricao", "marca", "animal", "departamento", "subdepartamento", "gtin", "custo",
    "preco", "preco_promocional", "estoque", "ativo", "publicar_site", "tipo_arte", "cor_arte", "imagem_url",
)
APELIDOS = {
    "promocao": "preco_promocional", "publicar_no_site": "publicar_site",
    "ean": "gtin", "gtin_ean": "gtin", "quantidade": "estoque",
}
VERDADEIRO = {"sim", "s", "1", "true", "verdadeiro", "x", "yes"}
FALSO = {"nao", "n", "0", "false", "falso", "no"}


class PlanilhaInvalida(Exception):
    pass


@dataclass(frozen=True)
class ErroLinha:
    linha: int
    campo: str
    mensagem: str


@dataclass
class ResultadoImportacao:
    total: int = 0
    criados: int = 0
    atualizados: int = 0
    erros: list[ErroLinha] = field(default_factory=list)


class _Taxonomia:
    def __init__(self):
        self.animais = self._indexar(Animal.objects.all())
        self.departamentos = self._indexar(Departamento.objects.all())
        self.subdepartamentos = self._indexar(Subdepartamento.objects.select_related("departamento"))

    @staticmethod
    def _indexar(objetos) -> dict[str, Any]:
        indice = {}
        for objeto in objetos:
            indice[normalizar(objeto.slug)] = objeto
            indice[normalizar(objeto.nome)] = objeto
        return indice

    def buscar(self, indice: dict[str, Any], valor: str, campo: str):
        objeto = indice.get(normalizar(valor))
        if objeto is None:
            raise ValueError(f"{campo} '{valor}' não cadastrado.")
        return objeto


def importar_planilha(
    arquivo: BinaryIO, *, nome_arquivo: str, usuario: str, apenas_validar: bool = False,
) -> ResultadoImportacao:
    linhas = _ler_linhas(arquivo)
    resultado = ResultadoImportacao(total=len(linhas))
    taxonomia = _Taxonomia()

    with transaction.atomic():
        for numero, valores in linhas:
            try:
                with transaction.atomic():
                    criado = _aplicar_linha(valores, taxonomia, referencia=nome_arquivo)
            except ValueError as erro:
                resultado.erros.append(ErroLinha(numero, _campo_do_erro(str(erro)), str(erro)))
            except Exception as erro:  # noqa: BLE001 — uma linha ruim não derruba a planilha inteira
                logger.exception("importacao_linha_falhou linha=%d", numero)
                resultado.erros.append(ErroLinha(numero, "", f"Erro inesperado: {erro}"))
            else:
                if criado:
                    resultado.criados += 1
                else:
                    resultado.atualizados += 1
        if apenas_validar:
            transaction.set_rollback(True)

    if not apenas_validar:
        ImportacaoPlanilha.objects.create(
            arquivo=nome_arquivo[:200], usuario=usuario, total=resultado.total, criados=resultado.criados,
            atualizados=resultado.atualizados, erros=[erro.__dict__ for erro in resultado.erros],
        )
    logger.info(
        "planilha_importada arquivo=%s validar=%s total=%d criados=%d atualizados=%d erros=%d",
        nome_arquivo, apenas_validar, resultado.total, resultado.criados, resultado.atualizados, len(resultado.erros),
    )
    return resultado


def gerar_modelo_planilha() -> bytes:
    livro = Workbook()
    produtos = livro.active
    produtos.title = "Produtos"
    produtos.append(list(COLUNAS))
    produtos.append([
        "RACAO-001", "Ração Premium Adultos 15kg", "Descrição do produto", "NutriPet", "cães", "Rações", "Ração Seca",
        "7891234567890", "120,00", "189,90", "159,90", 40, "sim", "sim", "saco", "#D96C4A", "",
    ])
    instrucoes = livro.create_sheet("Instruções")
    for linha in (
        ["Coluna", "Regra"],
        ["sku, nome, animal, preco", "Obrigatórias. O SKU identifica o produto: se já existir, ele é atualizado."],
        ["animal, departamento, subdepartamento", "Use o nome ou o código (slug) já cadastrado. Marca nova é criada sozinha."],
        ["preco, preco_promocional, custo", "Aceita 12,90 ou 12.90. O promocional não pode passar do preço. Valem para o site."],
        ["estoque", "Saldo desejado. O sistema registra a diferença como movimento de importação."],
        ["ativo, publicar_site", "sim ou não. Em branco: produto novo fica ativo e publicado."],
        ["tipo_arte", "saco, lata, frasco, bola, osso, caixa, cama, coleira ou pote."],
        ["Células vazias", "Em produto existente, célula vazia mantém o valor atual."],
    ):
        instrucoes.append(linha)
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def _ler_linhas(arquivo: BinaryIO) -> list[tuple[int, dict[str, Any]]]:
    try:
        livro = load_workbook(arquivo, read_only=True, data_only=True)
    except Exception as erro:  # noqa: BLE001 — qualquer falha de leitura vira erro de planilha
        raise PlanilhaInvalida("Não foi possível ler o arquivo. Envie um .xlsx válido.") from erro
    folha = livro.worksheets[0]
    linhas = folha.iter_rows(values_only=True)
    cabecalho = next(linhas, None)
    if cabecalho is None:
        raise PlanilhaInvalida("A planilha está vazia.")
    colunas = [_normalizar_coluna(valor) for valor in cabecalho]
    faltando = [c for c in OBRIGATORIAS if c not in colunas]
    if faltando:
        raise PlanilhaInvalida(f"Faltam as colunas obrigatórias: {', '.join(faltando)}.")

    registros = []
    for numero, valores in enumerate(linhas, start=2):
        registro = {coluna: valor for coluna, valor in zip(colunas, valores) if coluna in COLUNAS}
        if all(v is None or str(v).strip() == "" for v in registro.values()):
            continue
        registros.append((numero, registro))
    if len(registros) > LIMITE_LINHAS:
        raise PlanilhaInvalida(f"A planilha passa do limite de {LIMITE_LINHAS} linhas.")
    return registros


def _normalizar_coluna(valor: Any) -> str:
    texto = normalizar(str(valor or "")).replace(" ", "_")
    return APELIDOS.get(texto, texto)


def _campo_do_erro(mensagem: str) -> str:
    return max((campo for campo in COLUNAS if mensagem.startswith(campo)), key=len, default="")


def _texto(valores: dict[str, Any], campo: str) -> str:
    valor = valores.get(campo)
    return "" if valor is None else str(valor).strip()


def _decimal(valores: dict[str, Any], campo: str) -> Decimal | None:
    bruto = valores.get(campo)
    if bruto is None or str(bruto).strip() == "":
        return None
    texto = str(bruto).strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto).quantize(Decimal("0.01"))
    except InvalidOperation as erro:
        raise ValueError(f"{campo}: valor '{bruto}' não é um número.") from erro
    if numero < 0:
        raise ValueError(f"{campo}: não pode ser negativo.")
    return numero


def _inteiro(valores: dict[str, Any], campo: str) -> int | None:
    bruto = valores.get(campo)
    if bruto is None or str(bruto).strip() == "":
        return None
    try:
        numero = int(Decimal(str(bruto).replace(",", ".")))
    except (InvalidOperation, ValueError) as erro:
        raise ValueError(f"{campo}: valor '{bruto}' não é um número inteiro.") from erro
    if numero < 0:
        raise ValueError(f"{campo}: não pode ser negativo.")
    return numero


def _booleano(valores: dict[str, Any], campo: str) -> bool | None:
    bruto = valores.get(campo)
    if bruto is None or str(bruto).strip() == "":
        return None
    texto = normalizar(str(bruto))
    if texto in VERDADEIRO:
        return True
    if texto in FALSO:
        return False
    raise ValueError(f"{campo}: use sim ou não (recebido '{bruto}').")


def _aplicar_linha(valores: dict[str, Any], taxonomia: _Taxonomia, referencia: str) -> bool:
    for campo in OBRIGATORIAS:
        if not _texto(valores, campo):
            raise ValueError(f"{campo}: campo obrigatório vazio.")

    sku = _texto(valores, "sku")
    produto = Produto.objects.filter(sku=sku).first()
    criado = produto is None
    if criado:
        produto = Produto(sku=sku, slug=_slug_unico(_texto(valores, "nome")))

    produto.nome = _texto(valores, "nome")
    produto.animal = taxonomia.buscar(taxonomia.animais, _texto(valores, "animal"), "animal")
    _aplicar_departamentos(produto, valores, taxonomia)
    _aplicar_opcionais(produto, valores)

    preco, promo = _decimal(valores, "preco"), _decimal(valores, "preco_promocional")
    if preco is None:
        raise ValueError("preco: campo obrigatório vazio.")
    if promo is not None and promo > preco:
        raise ValueError("preco_promocional: não pode ser maior que o preço.")
    produto.preco = preco
    produto.save()

    publicar = _booleano(valores, "publicar_site")
    existente = None if criado else produto.canais.filter(canal__codigo="site").first()
    publicado = publicar if publicar is not None else (True if existente is None else existente.publicado)
    garantir_canais(produto, preco, promo, publicar_site=publicado)
    definir_preco_site(produto, preco, promo, publicado)

    estoque = _inteiro(valores, "estoque")
    if estoque is not None:
        definir_saldo(produto, estoque, EstoqueMovimento.Motivo.IMPORTACAO, referencia[:80])
    return criado


def _aplicar_departamentos(produto: Produto, valores: dict[str, Any], taxonomia: _Taxonomia) -> None:
    nome_sub = _texto(valores, "subdepartamento")
    nome_dep = _texto(valores, "departamento")
    if nome_sub:
        sub = taxonomia.buscar(taxonomia.subdepartamentos, nome_sub, "subdepartamento")
        if nome_dep and taxonomia.buscar(taxonomia.departamentos, nome_dep, "departamento").pk != sub.departamento_id:
            raise ValueError(f"subdepartamento: '{nome_sub}' não pertence ao departamento '{nome_dep}'.")
        produto.subdepartamento, produto.departamento = sub, sub.departamento
    elif nome_dep:
        produto.departamento = taxonomia.buscar(taxonomia.departamentos, nome_dep, "departamento")
        produto.subdepartamento = None


def _aplicar_opcionais(produto: Produto, valores: dict[str, Any]) -> None:
    for campo in ("descricao", "gtin", "imagem_url", "cor_arte"):
        if _texto(valores, campo):
            setattr(produto, campo, _texto(valores, campo))
    tipo = normalizar(_texto(valores, "tipo_arte"))
    if tipo:
        if tipo not in Produto.TipoArte.values:
            raise ValueError(f"tipo_arte: '{tipo}' inválido. Use {', '.join(Produto.TipoArte.values)}.")
        produto.tipo_arte = tipo
    nome_marca = _texto(valores, "marca")
    if nome_marca:
        produto.marca, _ = Marca.objects.get_or_create(nome=nome_marca, defaults={"slug": slugificar(nome_marca)})
    custo = _decimal(valores, "custo")
    if custo is not None:
        produto.custo = custo
    ativo = _booleano(valores, "ativo")
    if ativo is not None:
        produto.ativo = ativo
    elif produto.pk is None:
        produto.ativo = True


def _slug_unico(nome: str) -> str:
    base = slugificar(nome)[:150] or "produto"
    slug, contador = base, 2
    while Produto.objects.filter(slug=slug).exists():
        slug, contador = f"{base}-{contador}", contador + 1
    return slug
