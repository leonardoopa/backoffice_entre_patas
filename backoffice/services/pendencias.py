from backoffice.models import PendenciaMarketplace, Produto

ROTULOS = {
    "sem_gtin": "GTIN/EAN",
    "sem_ncm": "NCM",
    "sem_peso": "peso",
    "sem_dimensoes": "dimensões (altura, largura e comprimento)",
    "sem_marca": "marca",
    "sem_imagem": "pelo menos uma imagem",
    "descricao_curta": "descrição com pelo menos 30 caracteres",
}


def pendencias_marketplace(produto: Produto) -> list[str]:
    linha = PendenciaMarketplace.objects.filter(produto=produto).first()
    if linha is None:
        return []
    return [rotulo for campo, rotulo in ROTULOS.items() if getattr(linha, campo)]
