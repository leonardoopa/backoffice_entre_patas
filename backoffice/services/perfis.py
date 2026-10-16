from dataclasses import dataclass, field

CATALOGO = ["animal", "departamento", "subdepartamento", "marca", "grupoproduto", "produto", "produtoimagem"]
CANAIS = ["canal", "produtocanal", "vitrine", "vitrineitem"]
ESTOQUE = ["estoque", "estoquemovimento", "reservaestoque"]
VENDAS = ["pedido", "pedidoitem", "pedidostatushistorico", "devolucao", "cliente", "vendaprodutocanal", "oportunidadesite"]
ANALISE = ["margemprodutocanal", "alertamargem", "pendenciamarketplace", "historicopreco", "filasync", "anuncioexterno"]
OPERACAO = ["importacaoplanilha", "auditoria"]
CUSTOMIZADAS = {"alterar_preco", "publicar_canal", "importar_planilha"}

MODELOS_DE_NEGOCIO = CATALOGO + CANAIS + ESTOQUE + VENDAS + ANALISE + OPERACAO


@dataclass(frozen=True)
class Perfil:
    nome: str
    descricao: str
    permissoes: set[str] = field(default_factory=set)
    todas_do_app: bool = False
    gerencia_usuarios: bool = False


def _perm(acao: str, modelos: list[str]) -> set[str]:
    return {f"{acao}_{modelo}" for modelo in modelos}


PERFIS = [
    Perfil("Administrador", "Tudo, inclusive usuários e chaves de API.", todas_do_app=True, gerencia_usuarios=True),
    Perfil(
        "Gerente comercial",
        "Catálogo, preços, publicação nos canais, vitrines, devoluções e leitura de vendas e margens.",
        _perm("view", MODELOS_DE_NEGOCIO)
        | _perm("add", CATALOGO + ["vitrineitem", "estoquemovimento", "devolucao"])
        | _perm("change", CATALOGO + ["produtocanal", "vitrine", "vitrineitem", "pedido", "canal", "estoque", "devolucao"])
        | _perm("delete", ["vitrineitem", "produtoimagem"])
        | CUSTOMIZADAS,
    ),
    Perfil(
        "Catálogo e estoque",
        "Cadastra produtos, importa planilhas e movimenta estoque. Não altera preços nem publica.",
        _perm("view", CATALOGO + CANAIS + ESTOQUE + ["importacaoplanilha", "pendenciamarketplace"])
        | _perm("add", CATALOGO + ["estoquemovimento"])
        | _perm("change", CATALOGO + ["estoque"])
        | _perm("delete", ["produtoimagem"])
        | {"importar_planilha"},
    ),
    Perfil(
        "Atendimento",
        "Consulta pedidos e clientes, atualiza o status do pedido e trata devoluções.",
        _perm("view", ["produto", "pedido", "pedidoitem", "pedidostatushistorico", "cliente", "canal", "devolucao"])
        | {"change_pedido", "add_devolucao", "change_devolucao"},
    ),
    Perfil("Leitura", "Só consulta.", _perm("view", [m for m in MODELOS_DE_NEGOCIO if m != "auditoria"])),
]
