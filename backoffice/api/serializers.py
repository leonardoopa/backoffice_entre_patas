from decimal import Decimal

from backoffice.models import Animal, Departamento, ProdutoCanal, Subdepartamento


def dinheiro(valor: Decimal | None) -> str | None:
    return None if valor is None else f"{valor:.2f}"


def _basico(objeto) -> dict | None:
    return None if objeto is None else {"slug": objeto.slug, "nome": objeto.nome}


def animal(a: Animal) -> dict:
    return {"slug": a.slug, "nome": a.nome, "emoji": a.emoji}


def departamento(d: Departamento) -> dict:
    return {"slug": d.slug, "nome": d.nome}


def subdepartamento(s: Subdepartamento) -> dict:
    return {"slug": s.slug, "nome": s.nome, "departamento": s.departamento.slug}


def produto(item: ProdutoCanal) -> dict:
    p = item.produto
    estoque = getattr(p, "estoque", None)
    return {
        "sku": p.sku,
        "slug": p.slug,
        "nome": p.nome,
        "descricao": p.descricao,
        "gtin": p.gtin,
        "marca": _basico(p.marca),
        "animal": animal(p.animal),
        "departamento": _basico(p.departamento),
        "subdepartamento": _basico(p.subdepartamento),
        "preco": dinheiro(item.preco),
        "preco_promocional": dinheiro(item.preco_promocional),
        "preco_final": dinheiro(item.preco_final),
        "estoque": estoque.quantidade if estoque else 0,
        "avaliacao": f"{p.avaliacao:.1f}",
        "num_avaliacoes": p.num_avaliacoes,
        "arte": {"tipo": p.tipo_arte, "cor": p.cor_arte, "imagem_url": p.imagem_url},
    }
