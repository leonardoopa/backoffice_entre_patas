from decimal import Decimal

from backoffice.models import Animal, Departamento, Pedido, ProdutoCanal, Subdepartamento


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


def _grupo(produto) -> dict | None:
    return None if produto.grupo is None else {"slug": produto.grupo.slug, "nome": produto.grupo.nome}


def _imagens(produto) -> list[str]:
    urls = [imagem.url for imagem in produto.imagens.all()]
    return urls or ([produto.imagem_url] if produto.imagem_url else [])


def produto(item: ProdutoCanal) -> dict:
    p = item.produto
    estoque = getattr(p, "estoque", None)
    em_promocao = bool(item.promo_ativa)
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
        "grupo": _grupo(p),
        "variacao": p.variacao,
        "preco": dinheiro(item.preco),
        "preco_promocional": dinheiro(item.preco_promocional) if em_promocao else None,
        "promocao_fim": item.promo_fim.isoformat() if em_promocao and item.promo_fim else None,
        "preco_final": dinheiro(item.valor),
        "estoque": estoque.disponivel if estoque else 0,
        "avaliacao": f"{p.avaliacao:.1f}",
        "num_avaliacoes": p.num_avaliacoes,
        "arte": {"tipo": p.tipo_arte, "cor": p.cor_arte, "imagem_url": _imagens(p)[0] if _imagens(p) else ""},
        "imagens": _imagens(p),
    }


def produto_detalhe(item: ProdutoCanal, variacoes: list[ProdutoCanal]) -> dict:
    return {
        **produto(item),
        "variacoes": [
            {
                "sku": v.produto.sku, "slug": v.produto.slug, "variacao": v.produto.variacao,
                "preco_final": dinheiro(v.valor),
                "estoque": v.produto.estoque.disponivel if getattr(v.produto, "estoque", None) else 0,
            }
            for v in variacoes
        ],
    }


def pedido(p: Pedido) -> dict:
    return {
        "numero_externo": p.numero_externo,
        "status": p.status,
        "pagamento": {"forma": p.forma_pagamento, "status": p.pagamento_status, "parcelas": p.parcelas},
        "subtotal": dinheiro(p.subtotal),
        "frete": dinheiro(p.frete),
        "total": dinheiro(p.total),
        "comprado_em": p.comprado_em.isoformat(),
        "cliente": None if p.cliente is None else {
            "id_externo": p.cliente.id_externo, "nome": p.cliente.nome, "email": p.cliente.email,
        },
        "entrega": p.entrega,
        "itens": [
            {"sku": i.sku_externo, "descricao": i.descricao, "quantidade": i.quantidade, "preco_unitario": dinheiro(i.preco_unitario)}
            for i in p.itens.all()
        ],
        "historico_status": [
            {"status": h.status_novo, "em": h.criado_em.isoformat()} for h in p.historico_status.all()
        ],
    }
