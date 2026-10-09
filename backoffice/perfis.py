from dataclasses import dataclass, field

CATALOGO = ["animal", "departamento", "subdepartamento", "marca", "produto"]
CANAIS = ["canal", "produtocanal", "vitrine", "vitrineitem"]
ESTOQUE = ["estoque", "estoquemovimento"]
VENDAS = ["pedido", "pedidoitem", "cliente", "vendaprodutocanal", "oportunidadesite"]
OPERACAO = ["anuncioexterno", "historicopreco", "importacaoplanilha", "canal"]
CUSTOMIZADAS = {"alterar_preco", "publicar_canal", "importar_planilha"}


@dataclass(frozen=True)
class Perfil:
    nome: str
    descricao: str
    permissoes: set[str] = field(default_factory=set)
    todas_do_app: bool = False
    gerencia_usuarios: bool = False


def _perm(acao: str, modelos: list[str]) -> set[str]:
    return {f"{acao}_{modelo}" for modelo in modelos}


MODELOS_DE_NEGOCIO = CATALOGO + CANAIS + ESTOQUE + VENDAS + OPERACAO

PERFIS = [
    Perfil("Administrador", "Tudo, inclusive usuários e chaves de API.", todas_do_app=True, gerencia_usuarios=True),
    Perfil(
        "Gerente comercial",
        "Catálogo, preços, publicação nos canais, vitrines e leitura de vendas.",
        _perm("view", MODELOS_DE_NEGOCIO)
        | _perm("add", CATALOGO + ["vitrineitem", "estoquemovimento"])
        | _perm("change", CATALOGO + ["produtocanal", "vitrine", "vitrineitem", "pedido", "canal"])
        | _perm("delete", ["vitrineitem"])
        | CUSTOMIZADAS,
    ),
    Perfil(
        "Catálogo e estoque",
        "Cadastra produtos, importa planilhas e movimenta estoque. Não altera preços nem publica.",
        _perm("view", CATALOGO + CANAIS + ESTOQUE + ["importacaoplanilha"])
        | _perm("add", CATALOGO + ["estoquemovimento"])
        | _perm("change", CATALOGO)
        | {"importar_planilha"},
    ),
    Perfil(
        "Atendimento",
        "Consulta pedidos e clientes e atualiza o status do pedido.",
        _perm("view", ["produto", "pedido", "pedidoitem", "cliente", "canal"]) | {"change_pedido"},
    ),
    Perfil("Leitura", "Só consulta.", _perm("view", MODELOS_DE_NEGOCIO)),
]
