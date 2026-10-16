-- Autor das alterações: a aplicação grava o usuário em app.usuario no início de cada requisição.
CREATE FUNCTION usuario_atual() RETURNS TEXT AS $$
    SELECT COALESCE(NULLIF(current_setting('app.usuario', true), ''), 'sistema');
$$ LANGUAGE sql STABLE;

-- Promoção com prazo: uma única definição de "preço vigente" para views e API.
CREATE FUNCTION promocao_ativa(promo NUMERIC, inicio TIMESTAMPTZ, fim TIMESTAMPTZ) RETURNS BOOLEAN AS $$
    SELECT promo IS NOT NULL AND (inicio IS NULL OR inicio <= now()) AND (fim IS NULL OR fim > now());
$$ LANGUAGE sql STABLE;

CREATE FUNCTION preco_vigente(preco NUMERIC, promo NUMERIC, inicio TIMESTAMPTZ, fim TIMESTAMPTZ) RETURNS NUMERIC AS $$
    SELECT CASE WHEN promocao_ativa(promo, inicio, fim) THEN promo ELSE preco END;
$$ LANGUAGE sql STABLE;

ALTER TABLE produto_canal
    ADD COLUMN promo_inicio TIMESTAMPTZ,
    ADD COLUMN promo_fim TIMESTAMPTZ,
    ADD CONSTRAINT promo_periodo_valido CHECK (promo_inicio IS NULL OR promo_fim IS NULL OR promo_fim > promo_inicio);

ALTER TABLE canal
    ADD COLUMN margem_minima_percentual NUMERIC(5, 2) NOT NULL DEFAULT 10
        CHECK (margem_minima_percentual BETWEEN 0 AND 100);

-- Dados exigidos pelos marketplaces e fotos.
ALTER TABLE produto
    ADD COLUMN ncm VARCHAR(8) NOT NULL DEFAULT '' CHECK (ncm = '' OR ncm ~ '^[0-9]{8}$'),
    ADD COLUMN peso_g INTEGER CHECK (peso_g IS NULL OR peso_g > 0),
    ADD COLUMN altura_cm NUMERIC(6, 1) CHECK (altura_cm IS NULL OR altura_cm > 0),
    ADD COLUMN largura_cm NUMERIC(6, 1) CHECK (largura_cm IS NULL OR largura_cm > 0),
    ADD COLUMN comprimento_cm NUMERIC(6, 1) CHECK (comprimento_cm IS NULL OR comprimento_cm > 0),
    ADD CONSTRAINT produto_gtin_valido CHECK (gtin = '' OR gtin ~ '^([0-9]{8}|[0-9]{12,14})$');

CREATE TABLE produto_imagem (
    id         BIGSERIAL PRIMARY KEY,
    produto_id BIGINT       NOT NULL REFERENCES produto (id) ON DELETE CASCADE,
    url        VARCHAR(500) NOT NULL,
    posicao    SMALLINT     NOT NULL DEFAULT 0,
    UNIQUE (produto_id, url)
);

-- Variações: produtos do mesmo grupo diferem só por tamanho, peso ou volume.
CREATE TABLE grupo_produto (
    id   SERIAL PRIMARY KEY,
    slug VARCHAR(160) NOT NULL UNIQUE,
    nome VARCHAR(160) NOT NULL
);

ALTER TABLE produto
    ADD COLUMN grupo_id INTEGER REFERENCES grupo_produto (id) ON DELETE SET NULL,
    ADD COLUMN variacao VARCHAR(40) NOT NULL DEFAULT '',
    ADD CONSTRAINT produto_variacao_exige_grupo CHECK (grupo_id IS NOT NULL OR variacao = '');
CREATE UNIQUE INDEX produto_grupo_variacao_unica ON produto (grupo_id, variacao) WHERE grupo_id IS NOT NULL;

-- Estoque: reservado e de segurança nunca são vendidos.
ALTER TABLE estoque
    ADD COLUMN reservado INTEGER NOT NULL DEFAULT 0 CHECK (reservado >= 0),
    ADD COLUMN seguranca INTEGER NOT NULL DEFAULT 0 CHECK (seguranca >= 0);

ALTER TABLE estoque_movimento ADD COLUMN usuario VARCHAR(150) NOT NULL DEFAULT 'sistema';
ALTER TABLE historico_preco ADD COLUMN usuario VARCHAR(150) NOT NULL DEFAULT 'sistema';

CREATE FUNCTION definir_usuario() RETURNS TRIGGER AS $$
BEGIN
    NEW.usuario = usuario_atual();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER estoque_movimento_usuario BEFORE INSERT ON estoque_movimento
    FOR EACH ROW EXECUTE FUNCTION definir_usuario();
CREATE TRIGGER historico_preco_usuario BEFORE INSERT ON historico_preco
    FOR EACH ROW EXECUTE FUNCTION definir_usuario();

CREATE TABLE reserva_estoque (
    id         BIGSERIAL PRIMARY KEY,
    produto_id BIGINT      NOT NULL REFERENCES produto (id) ON DELETE CASCADE,
    canal_id   INTEGER     NOT NULL REFERENCES canal (id),
    quantidade INTEGER     NOT NULL CHECK (quantidade > 0),
    referencia VARCHAR(80) NOT NULL,
    status     VARCHAR(10) NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa', 'confirmada', 'liberada', 'expirada')),
    expira_em  TIMESTAMPTZ NOT NULL,
    criada_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (canal_id, referencia, produto_id)
);
CREATE INDEX reserva_ativa_expiracao_idx ON reserva_estoque (expira_em) WHERE status = 'ativa';

-- Fila de sincronização com os marketplaces. Só um pedido pendente por produto e tipo; mudança durante o envio gera outro.
CREATE TABLE fila_sync (
    id                   BIGSERIAL PRIMARY KEY,
    canal_id             INTEGER     NOT NULL REFERENCES canal (id),
    produto_id           BIGINT      NOT NULL REFERENCES produto (id) ON DELETE CASCADE,
    tipo                 VARCHAR(10) NOT NULL CHECK (tipo IN ('preco', 'estoque', 'publicacao')),
    status               VARCHAR(12) NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'processando', 'concluida', 'erro')),
    tentativas           SMALLINT    NOT NULL DEFAULT 0,
    proxima_tentativa_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultimo_erro          TEXT        NOT NULL DEFAULT '',
    criada_em            TIMESTAMPTZ NOT NULL DEFAULT now(),
    concluida_em         TIMESTAMPTZ
);
CREATE UNIQUE INDEX fila_sync_pendente_unica ON fila_sync (canal_id, produto_id, tipo)
    WHERE status = 'pendente';
CREATE INDEX fila_sync_devida_idx ON fila_sync (proxima_tentativa_em) WHERE status = 'pendente';

CREATE FUNCTION enfileirar_sync(p_canal INTEGER, p_produto BIGINT, p_tipo VARCHAR) RETURNS VOID AS $$
BEGIN
    INSERT INTO fila_sync (canal_id, produto_id, tipo) VALUES (p_canal, p_produto, p_tipo)
    ON CONFLICT (canal_id, produto_id, tipo) WHERE status = 'pendente' DO NOTHING;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION produto_canal_enfileirar() RETURNS TRIGGER AS $$
DECLARE
    tipo_canal TEXT;
BEGIN
    SELECT tipo INTO tipo_canal FROM canal WHERE id = NEW.canal_id;
    IF tipo_canal IS DISTINCT FROM 'marketplace' THEN
        RETURN NEW;
    END IF;
    IF NEW.preco IS DISTINCT FROM OLD.preco
        OR NEW.preco_promocional IS DISTINCT FROM OLD.preco_promocional
        OR NEW.promo_inicio IS DISTINCT FROM OLD.promo_inicio
        OR NEW.promo_fim IS DISTINCT FROM OLD.promo_fim THEN
        PERFORM enfileirar_sync(NEW.canal_id, NEW.produto_id, 'preco');
    END IF;
    IF NEW.publicado IS DISTINCT FROM OLD.publicado THEN
        PERFORM enfileirar_sync(NEW.canal_id, NEW.produto_id, 'publicacao');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER produto_canal_fila AFTER UPDATE ON produto_canal
    FOR EACH ROW EXECUTE FUNCTION produto_canal_enfileirar();

CREATE FUNCTION estoque_enfileirar() RETURNS TRIGGER AS $$
DECLARE
    canal INTEGER;
BEGIN
    IF NEW.quantidade IS DISTINCT FROM OLD.quantidade
        OR NEW.reservado IS DISTINCT FROM OLD.reservado
        OR NEW.seguranca IS DISTINCT FROM OLD.seguranca THEN
        FOR canal IN
            SELECT pc.canal_id
            FROM produto_canal pc
            JOIN canal c ON c.id = pc.canal_id AND c.tipo = 'marketplace' AND c.ativo
            WHERE pc.produto_id = NEW.produto_id AND pc.publicado
        LOOP
            PERFORM enfileirar_sync(canal, NEW.produto_id, 'estoque');
        END LOOP;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER estoque_fila AFTER UPDATE ON estoque
    FOR EACH ROW EXECUTE FUNCTION estoque_enfileirar();

-- Pedido completo: pagamento, histórico de status e devolução.
ALTER TABLE pedido
    ADD COLUMN forma_pagamento VARCHAR(20) NOT NULL DEFAULT ''
        CHECK (forma_pagamento IN ('', 'pix', 'cartao_credito', 'cartao_debito', 'boleto', 'marketplace')),
    ADD COLUMN pagamento_status VARCHAR(10) NOT NULL DEFAULT 'pendente'
        CHECK (pagamento_status IN ('pendente', 'aprovado', 'recusado', 'estornado')),
    ADD COLUMN pagamento_referencia VARCHAR(120) NOT NULL DEFAULT '',
    ADD COLUMN parcelas SMALLINT NOT NULL DEFAULT 1 CHECK (parcelas >= 1);

CREATE TABLE pedido_status_historico (
    id              BIGSERIAL PRIMARY KEY,
    pedido_id       BIGINT      NOT NULL REFERENCES pedido (id) ON DELETE CASCADE,
    status_anterior VARCHAR(12),
    status_novo     VARCHAR(12) NOT NULL,
    usuario         VARCHAR(150) NOT NULL DEFAULT 'sistema',
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX pedido_status_historico_idx ON pedido_status_historico (pedido_id, criado_em);

CREATE FUNCTION registrar_status_pedido() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO pedido_status_historico (pedido_id, status_anterior, status_novo, usuario)
        VALUES (NEW.id, NULL, NEW.status, usuario_atual());
    ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO pedido_status_historico (pedido_id, status_anterior, status_novo, usuario)
        VALUES (NEW.id, OLD.status, NEW.status, usuario_atual());
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER pedido_historico_status AFTER INSERT OR UPDATE OF status ON pedido
    FOR EACH ROW EXECUTE FUNCTION registrar_status_pedido();

CREATE TABLE devolucao (
    id              BIGSERIAL PRIMARY KEY,
    pedido_item_id  BIGINT      NOT NULL REFERENCES pedido_item (id) ON DELETE CASCADE,
    quantidade      INTEGER     NOT NULL CHECK (quantidade > 0),
    motivo          VARCHAR(15) NOT NULL CHECK (motivo IN ('arrependimento', 'defeito', 'errado', 'outro')),
    observacao      TEXT        NOT NULL DEFAULT '',
    status          VARCHAR(12) NOT NULL DEFAULT 'solicitada'
        CHECK (status IN ('solicitada', 'aprovada', 'recebida', 'reembolsada', 'recusada')),
    valor_reembolso NUMERIC(10, 2) CHECK (valor_reembolso IS NULL OR valor_reembolso >= 0),
    criada_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizada_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX devolucao_item_idx ON devolucao (pedido_item_id);

CREATE FUNCTION atualizar_devolucao_timestamp() RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizada_em = clock_timestamp();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER devolucao_atualizada_em BEFORE UPDATE ON devolucao
    FOR EACH ROW EXECUTE FUNCTION atualizar_devolucao_timestamp();

-- Auditoria geral: quem mudou o quê (só as colunas alteradas).
CREATE TABLE auditoria (
    id          BIGSERIAL PRIMARY KEY,
    tabela      VARCHAR(40)  NOT NULL,
    registro_id BIGINT       NOT NULL,
    acao        VARCHAR(6)   NOT NULL CHECK (acao IN ('insert', 'update', 'delete')),
    usuario     VARCHAR(150) NOT NULL,
    mudancas    JSONB        NOT NULL,
    criado_em   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX auditoria_registro_idx ON auditoria (tabela, registro_id, criado_em DESC);
CREATE INDEX auditoria_usuario_idx ON auditoria (usuario, criado_em DESC);

CREATE FUNCTION registrar_auditoria() RETURNS TRIGGER AS $$
DECLARE
    registro BIGINT;
    mudancas JSONB;
BEGIN
    IF TG_OP = 'INSERT' THEN
        registro := NEW.id;
        mudancas := to_jsonb(NEW) - 'atualizado_em' - 'hash_chave';
    ELSIF TG_OP = 'UPDATE' THEN
        registro := NEW.id;
        SELECT COALESCE(jsonb_object_agg(n.key, jsonb_build_object('de', o.value, 'para', n.value)), '{}'::jsonb)
        INTO mudancas
        FROM jsonb_each(to_jsonb(NEW)) n
        JOIN jsonb_each(to_jsonb(OLD)) o ON o.key = n.key
        WHERE n.value IS DISTINCT FROM o.value AND n.key NOT IN ('atualizado_em', 'hash_chave', 'ultimo_uso_em');
        IF mudancas = '{}'::jsonb THEN
            RETURN NEW;
        END IF;
    ELSE
        registro := OLD.id;
        mudancas := to_jsonb(OLD) - 'atualizado_em' - 'hash_chave';
    END IF;
    INSERT INTO auditoria (tabela, registro_id, acao, usuario, mudancas)
    VALUES (TG_TABLE_NAME, registro, lower(TG_OP), usuario_atual(), mudancas);
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER auditoria_produto AFTER INSERT OR UPDATE OR DELETE ON produto
    FOR EACH ROW EXECUTE FUNCTION registrar_auditoria();
CREATE TRIGGER auditoria_produto_canal AFTER INSERT OR UPDATE OR DELETE ON produto_canal
    FOR EACH ROW EXECUTE FUNCTION registrar_auditoria();
CREATE TRIGGER auditoria_vitrine AFTER INSERT OR UPDATE OR DELETE ON vitrine
    FOR EACH ROW EXECUTE FUNCTION registrar_auditoria();
CREATE TRIGGER auditoria_vitrine_item AFTER INSERT OR UPDATE OR DELETE ON vitrine_item
    FOR EACH ROW EXECUTE FUNCTION registrar_auditoria();
CREATE TRIGGER auditoria_canal AFTER INSERT OR UPDATE OR DELETE ON canal
    FOR EACH ROW EXECUTE FUNCTION registrar_auditoria();
CREATE TRIGGER auditoria_pedido AFTER INSERT OR UPDATE OR DELETE ON pedido
    FOR EACH ROW EXECUTE FUNCTION registrar_auditoria();
CREATE TRIGGER auditoria_devolucao AFTER INSERT OR UPDATE OR DELETE ON devolucao
    FOR EACH ROW EXECUTE FUNCTION registrar_auditoria();
CREATE TRIGGER auditoria_grupo_produto AFTER INSERT OR UPDATE OR DELETE ON grupo_produto
    FOR EACH ROW EXECUTE FUNCTION registrar_auditoria();
CREATE TRIGGER auditoria_chave_api AFTER INSERT OR UPDATE OR DELETE ON chave_api
    FOR EACH ROW EXECUTE FUNCTION registrar_auditoria();

-- Margem por canal: preço vigente menos comissão menos custo.
CREATE VIEW vw_margem_produto_canal AS
SELECT
    x.*,
    CASE
        WHEN x.custo IS NULL OR x.preco_vigente = 0 THEN NULL
        ELSE ROUND((x.preco_vigente * (1 - x.comissao_percentual / 100) - x.custo) / x.preco_vigente * 100, 2)
    END AS margem_percentual
FROM (
    SELECT
        pc.id                                                                             AS id,
        pc.produto_id                                                                     AS produto_id,
        pc.canal_id                                                                       AS canal_id,
        preco_vigente(pc.preco, pc.preco_promocional, pc.promo_inicio, pc.promo_fim)      AS preco_vigente,
        p.custo                                                                           AS custo,
        c.comissao_percentual                                                             AS comissao_percentual,
        c.margem_minima_percentual                                                        AS margem_minima_percentual
    FROM produto_canal pc
    JOIN produto p ON p.id = pc.produto_id AND p.ativo
    JOIN canal c ON c.id = pc.canal_id
    WHERE pc.publicado
) x;

CREATE VIEW vw_alerta_margem AS
SELECT * FROM vw_margem_produto_canal
WHERE margem_percentual IS NOT NULL AND margem_percentual < margem_minima_percentual;

-- O que falta para o produto poder ir a um marketplace.
CREATE VIEW vw_pendencias_marketplace AS
SELECT
    p.id                                                             AS id,
    p.id                                                             AS produto_id,
    (p.gtin = '')                                                    AS sem_gtin,
    (p.ncm = '')                                                     AS sem_ncm,
    (p.peso_g IS NULL)                                               AS sem_peso,
    (p.altura_cm IS NULL OR p.largura_cm IS NULL OR p.comprimento_cm IS NULL) AS sem_dimensoes,
    (p.marca_id IS NULL)                                             AS sem_marca,
    (p.imagem_url = '' AND NOT EXISTS (SELECT 1 FROM produto_imagem i WHERE i.produto_id = p.id)) AS sem_imagem,
    (length(p.descricao) < 30)                                       AS descricao_curta
FROM produto p
WHERE p.ativo;
