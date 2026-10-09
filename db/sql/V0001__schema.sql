CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE animal (
    id        SERIAL PRIMARY KEY,
    slug      VARCHAR(50) NOT NULL UNIQUE,
    nome      VARCHAR(80) NOT NULL,
    emoji     VARCHAR(8)  NOT NULL DEFAULT '',
    ordem     SMALLINT    NOT NULL DEFAULT 0,
    ativo     BOOLEAN     NOT NULL DEFAULT TRUE
);

CREATE TABLE departamento (
    id        SERIAL PRIMARY KEY,
    slug      VARCHAR(50) NOT NULL UNIQUE,
    nome      VARCHAR(80) NOT NULL,
    ordem     SMALLINT    NOT NULL DEFAULT 0,
    ativo     BOOLEAN     NOT NULL DEFAULT TRUE
);

CREATE TABLE subdepartamento (
    id              SERIAL PRIMARY KEY,
    departamento_id INTEGER     NOT NULL REFERENCES departamento (id) ON DELETE CASCADE,
    slug            VARCHAR(60) NOT NULL UNIQUE,
    nome            VARCHAR(80) NOT NULL,
    ordem           SMALLINT    NOT NULL DEFAULT 0
);

CREATE TABLE marca (
    id    SERIAL PRIMARY KEY,
    slug  VARCHAR(80) NOT NULL UNIQUE,
    nome  VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE produto (
    id                 BIGSERIAL PRIMARY KEY,
    sku                VARCHAR(60)  NOT NULL UNIQUE,
    slug               VARCHAR(160) NOT NULL UNIQUE,
    nome               VARCHAR(160) NOT NULL,
    descricao          TEXT         NOT NULL DEFAULT '',
    marca_id           INTEGER REFERENCES marca (id) ON DELETE SET NULL,
    animal_id          INTEGER      NOT NULL REFERENCES animal (id),
    departamento_id    INTEGER REFERENCES departamento (id),
    subdepartamento_id INTEGER REFERENCES subdepartamento (id),
    gtin               VARCHAR(14)  NOT NULL DEFAULT '',
    custo              NUMERIC(10, 2) CHECK (custo IS NULL OR custo >= 0),
    preco              NUMERIC(10, 2) NOT NULL CHECK (preco >= 0),
    tipo_arte          VARCHAR(10)  NOT NULL DEFAULT 'caixa',
    cor_arte           VARCHAR(7)   NOT NULL DEFAULT '#17375e',
    imagem_url         VARCHAR(500) NOT NULL DEFAULT '',
    avaliacao          NUMERIC(2, 1) NOT NULL DEFAULT 0 CHECK (avaliacao BETWEEN 0 AND 5),
    num_avaliacoes     INTEGER      NOT NULL DEFAULT 0 CHECK (num_avaliacoes >= 0),
    ativo              BOOLEAN      NOT NULL DEFAULT TRUE,
    criado_em          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    atualizado_em      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX produto_animal_idx ON produto (animal_id);
CREATE INDEX produto_departamento_idx ON produto (departamento_id);
CREATE INDEX produto_marca_idx ON produto (marca_id);
CREATE INDEX produto_gtin_idx ON produto (gtin) WHERE gtin <> '';

CREATE FUNCTION atualizar_timestamp() RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = clock_timestamp();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER produto_atualizado_em
    BEFORE UPDATE ON produto
    FOR EACH ROW EXECUTE FUNCTION atualizar_timestamp();

CREATE TABLE estoque (
    produto_id BIGINT PRIMARY KEY REFERENCES produto (id) ON DELETE CASCADE,
    quantidade INTEGER NOT NULL DEFAULT 0 CHECK (quantidade >= 0)
);

CREATE TABLE estoque_movimento (
    id         BIGSERIAL PRIMARY KEY,
    produto_id BIGINT      NOT NULL REFERENCES produto (id) ON DELETE CASCADE,
    quantidade INTEGER     NOT NULL CHECK (quantidade <> 0),
    motivo     VARCHAR(12) NOT NULL CHECK (motivo IN ('entrada', 'venda', 'ajuste', 'devolucao', 'importacao')),
    referencia VARCHAR(80) NOT NULL DEFAULT '',
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX estoque_movimento_produto_idx ON estoque_movimento (produto_id, criado_em DESC);

CREATE TABLE canal (
    id                  SERIAL PRIMARY KEY,
    codigo              VARCHAR(30) NOT NULL UNIQUE,
    nome                VARCHAR(80) NOT NULL,
    tipo                VARCHAR(12) NOT NULL CHECK (tipo IN ('site', 'marketplace')),
    comissao_percentual NUMERIC(5, 2) NOT NULL DEFAULT 0 CHECK (comissao_percentual BETWEEN 0 AND 100),
    ativo               BOOLEAN     NOT NULL DEFAULT TRUE
);

INSERT INTO canal (codigo, nome, tipo, comissao_percentual) VALUES
    ('site', 'Site EntrePatas', 'site', 0),
    ('mercado_livre', 'Mercado Livre', 'marketplace', 0),
    ('amazon', 'Amazon', 'marketplace', 0);

CREATE TABLE produto_canal (
    id                BIGSERIAL PRIMARY KEY,
    produto_id        BIGINT      NOT NULL REFERENCES produto (id) ON DELETE CASCADE,
    canal_id          INTEGER     NOT NULL REFERENCES canal (id),
    publicado         BOOLEAN     NOT NULL DEFAULT FALSE,
    preco             NUMERIC(10, 2) NOT NULL CHECK (preco >= 0),
    preco_promocional NUMERIC(10, 2) CHECK (preco_promocional IS NULL OR preco_promocional <= preco),
    id_externo        VARCHAR(80) NOT NULL DEFAULT '',
    status_sync       VARCHAR(12) NOT NULL DEFAULT 'pendente' CHECK (status_sync IN ('pendente', 'sincronizado', 'erro')),
    erro_sync         TEXT        NOT NULL DEFAULT '',
    sincronizado_em   TIMESTAMPTZ,
    UNIQUE (produto_id, canal_id)
);
CREATE INDEX produto_canal_canal_idx ON produto_canal (canal_id, publicado);

CREATE TABLE historico_preco (
    id             BIGSERIAL PRIMARY KEY,
    produto_id     BIGINT  NOT NULL REFERENCES produto (id) ON DELETE CASCADE,
    canal_id       INTEGER NOT NULL REFERENCES canal (id),
    preco_anterior NUMERIC(10, 2) NOT NULL,
    preco_novo     NUMERIC(10, 2) NOT NULL,
    promo_anterior NUMERIC(10, 2),
    promo_nova     NUMERIC(10, 2),
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX historico_preco_produto_idx ON historico_preco (produto_id, criado_em DESC);

CREATE FUNCTION registrar_historico_preco() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.preco IS DISTINCT FROM OLD.preco OR NEW.preco_promocional IS DISTINCT FROM OLD.preco_promocional THEN
        INSERT INTO historico_preco (produto_id, canal_id, preco_anterior, preco_novo, promo_anterior, promo_nova)
        VALUES (NEW.produto_id, NEW.canal_id, OLD.preco, NEW.preco, OLD.preco_promocional, NEW.preco_promocional);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER produto_canal_historico_preco
    AFTER UPDATE ON produto_canal
    FOR EACH ROW EXECUTE FUNCTION registrar_historico_preco();

CREATE TABLE vitrine (
    id     SERIAL PRIMARY KEY,
    codigo VARCHAR(30) NOT NULL UNIQUE,
    nome   VARCHAR(80) NOT NULL,
    modo   VARCHAR(10) NOT NULL DEFAULT 'automatico' CHECK (modo IN ('manual', 'automatico')),
    limite SMALLINT    NOT NULL DEFAULT 12 CHECK (limite BETWEEN 1 AND 48),
    ativa  BOOLEAN     NOT NULL DEFAULT TRUE
);

INSERT INTO vitrine (codigo, nome, modo, limite) VALUES
    ('ofertas', 'Ofertas imperdíveis', 'automatico', 12),
    ('mais_vendidos', 'Mais vendidos', 'automatico', 12),
    ('destaques', 'Destaques', 'manual', 12);

CREATE TABLE vitrine_item (
    id         BIGSERIAL PRIMARY KEY,
    vitrine_id INTEGER  NOT NULL REFERENCES vitrine (id) ON DELETE CASCADE,
    produto_id BIGINT   NOT NULL REFERENCES produto (id) ON DELETE CASCADE,
    posicao    SMALLINT NOT NULL DEFAULT 0,
    UNIQUE (vitrine_id, produto_id)
);

CREATE TABLE cliente (
    id         BIGSERIAL PRIMARY KEY,
    canal_id   INTEGER      NOT NULL REFERENCES canal (id),
    id_externo VARCHAR(80)  NOT NULL,
    nome       VARCHAR(120) NOT NULL DEFAULT '',
    email      VARCHAR(254) NOT NULL DEFAULT '',
    telefone   VARCHAR(30)  NOT NULL DEFAULT '',
    criado_em  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (canal_id, id_externo)
);

CREATE TABLE pedido (
    id             BIGSERIAL PRIMARY KEY,
    canal_id       INTEGER     NOT NULL REFERENCES canal (id),
    numero_externo VARCHAR(80) NOT NULL,
    cliente_id     BIGINT REFERENCES cliente (id) ON DELETE SET NULL,
    status         VARCHAR(12) NOT NULL DEFAULT 'novo' CHECK (status IN ('novo', 'pago', 'enviado', 'entregue', 'cancelado')),
    subtotal       NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (subtotal >= 0),
    frete          NUMERIC(10, 2) NOT NULL DEFAULT 0 CHECK (frete >= 0),
    total          NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (total >= 0),
    entrega        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    comprado_em    TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (canal_id, numero_externo)
);
CREATE INDEX pedido_comprado_em_idx ON pedido (comprado_em DESC);
CREATE INDEX pedido_canal_status_idx ON pedido (canal_id, status);

CREATE TABLE pedido_item (
    id             BIGSERIAL PRIMARY KEY,
    pedido_id      BIGINT       NOT NULL REFERENCES pedido (id) ON DELETE CASCADE,
    produto_id     BIGINT REFERENCES produto (id) ON DELETE SET NULL,
    sku_externo    VARCHAR(80)  NOT NULL DEFAULT '',
    descricao      VARCHAR(200) NOT NULL DEFAULT '',
    quantidade     INTEGER      NOT NULL CHECK (quantidade > 0),
    preco_unitario NUMERIC(10, 2) NOT NULL CHECK (preco_unitario >= 0)
);
CREATE INDEX pedido_item_produto_idx ON pedido_item (produto_id);

CREATE TABLE anuncio_externo (
    id          BIGSERIAL PRIMARY KEY,
    canal_id    INTEGER      NOT NULL REFERENCES canal (id),
    id_externo  VARCHAR(80)  NOT NULL,
    sku_externo VARCHAR(80)  NOT NULL DEFAULT '',
    titulo      VARCHAR(250) NOT NULL DEFAULT '',
    preco       NUMERIC(10, 2),
    estoque     INTEGER,
    status      VARCHAR(20)  NOT NULL DEFAULT '',
    produto_id  BIGINT REFERENCES produto (id) ON DELETE SET NULL,
    bruto       JSONB        NOT NULL DEFAULT '{}'::jsonb,
    importado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (canal_id, id_externo)
);

CREATE TABLE importacao_planilha (
    id          BIGSERIAL PRIMARY KEY,
    arquivo     VARCHAR(200) NOT NULL,
    usuario     VARCHAR(150) NOT NULL,
    total       INTEGER      NOT NULL DEFAULT 0,
    criados     INTEGER      NOT NULL DEFAULT 0,
    atualizados INTEGER      NOT NULL DEFAULT 0,
    erros       JSONB        NOT NULL DEFAULT '[]'::jsonb,
    criado_em   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE chave_api (
    id              SERIAL PRIMARY KEY,
    nome            VARCHAR(80) NOT NULL,
    prefixo         VARCHAR(8)  NOT NULL UNIQUE,
    hash_chave      CHAR(64)    NOT NULL,
    escopo          VARCHAR(10) NOT NULL CHECK (escopo IN ('site', 'leitura')),
    ativa           BOOLEAN     NOT NULL DEFAULT TRUE,
    criada_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultimo_uso_em   TIMESTAMPTZ
);

CREATE VIEW vw_vendas_produto_canal AS
SELECT
    (pi.produto_id * 100 + pe.canal_id)        AS id,
    pi.produto_id                              AS produto_id,
    pe.canal_id                                AS canal_id,
    SUM(pi.quantidade)                         AS unidades,
    SUM(pi.quantidade * pi.preco_unitario)     AS receita,
    MAX(pe.comprado_em)                        AS ultima_venda
FROM pedido_item pi
JOIN pedido pe ON pe.id = pi.pedido_id AND pe.status <> 'cancelado'
WHERE pi.produto_id IS NOT NULL
GROUP BY pi.produto_id, pe.canal_id;

CREATE VIEW vw_oportunidades_site AS
SELECT
    p.id                                       AS id,
    p.id                                       AS produto_id,
    SUM(pi.quantidade)                         AS unidades_marketplaces,
    SUM(pi.quantidade * pi.preco_unitario)     AS receita_marketplaces,
    MAX(pe.comprado_em)                        AS ultima_venda
FROM produto p
JOIN pedido_item pi ON pi.produto_id = p.id
JOIN pedido pe ON pe.id = pi.pedido_id AND pe.status <> 'cancelado'
JOIN canal c ON c.id = pe.canal_id AND c.tipo = 'marketplace'
WHERE NOT EXISTS (
    SELECT 1
    FROM produto_canal pc
    JOIN canal cs ON cs.id = pc.canal_id AND cs.codigo = 'site'
    WHERE pc.produto_id = p.id AND pc.publicado
)
GROUP BY p.id;
