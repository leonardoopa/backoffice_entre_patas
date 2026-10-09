# EntrePatas Backoffice

Fonte única de verdade da EntrePatas. Aqui ficam catálogo, preços por canal, estoque, vitrines da home e o CRM de vendas. O site (www.entrepatas.com) e os marketplaces (Mercado Livre e Amazon) consomem os dados daqui.

```
Excel / cadastro manual ──► Backoffice (PostgreSQL + Django Admin) ──► API ──► Site
                                         ▲                                  └─► Marketplaces (fase 3)
                                         └── pedidos e anúncios dos canais voltam para o CRM
```

## Como o banco é criado

O esquema nasce em **SQL puro**, em `db/sql/V0001__schema.sql`: tabelas, restrições, índices, gatilhos e views. O Django só mostra e edita esses dados: os models têm `managed = False` e não geram tabelas.

Para o banco ser aplicado igual em desenvolvimento, testes e produção, cada arquivo `.sql` é executado por uma migração do Django (`RunSQL`). Fluxo para mudar o banco:

1. Crie `db/sql/V000N__descricao.sql` (nunca edite um arquivo que já foi aplicado em algum ambiente).
2. Atualize os models em `backoffice/models/` para refletir a mudança.
3. Rode `docker compose run --rm web python manage.py makemigrations backoffice`.
4. Abra a migração gerada e acrescente `arquivo_sql("V000N__descricao.sql")` no início de `operations` (veja `0001_initial.py`).
5. Rode os testes: `test_schema` falha se algum `.sql` não estiver ligado a uma migração.

O que o SQL garante sozinho, mesmo fora do Django: preço promocional nunca maior que o preço, estoque nunca negativo, histórico automático de mudança de preço (gatilho), `atualizado_em` do produto e as views de CRM.

## Rodando

Pré-requisito: Docker.

```bash
docker compose up --build
docker compose exec web python manage.py createsuperuser
```

Abra http://localhost:8500. No modo de desenvolvimento a primeira subida cria o banco, aplica o SQL, cria os perfis de acesso e carrega 65 produtos, estoque e 120 pedidos fictícios nos três canais.

```bash
docker compose exec web python manage.py test          # testes (PostgreSQL)
docker compose exec web python manage.py criar_perfis  # recria os perfis de acesso
docker compose exec web python manage.py criar_chave_api site-producao site
docker compose logs -f web                             # logs
```

Produção: `cp .env.example .env`, preencha `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `POSTGRES_PASSWORD` e rode `docker compose -f docker-compose.yml up -d --build`. Coloque um proxy com HTTPS na frente (`DJANGO_HTTPS=1`).

## Níveis de acesso

Usuários são criados em **Usuários**, com "Membro da equipe" marcado e um **perfil** (grupo). Os perfis são recriados por `criar_perfis` a cada subida.

| Perfil | Pode |
| --- | --- |
| Administrador | Tudo, inclusive usuários, perfis e chaves de API |
| Gerente comercial | Catálogo, **preços**, **publicar nos canais**, vitrines e importar planilhas; vê vendas; não vê chaves de API |
| Catálogo e estoque | Cadastrar e editar produtos, importar planilhas, movimentar estoque. **Não** altera preços nem publica |
| Atendimento | Vê pedidos e clientes e muda o status do pedido |
| Leitura | Só consulta |

Três permissões próprias controlam o que é sensível: `alterar_preco`, `publicar_canal` e `importar_planilha`. Quem não tem `alterar_preco` vê os campos de preço bloqueados; quem não tem `publicar_canal` não vê as ações de publicar.

## Importação por Excel

Em **Produtos**: "Baixar modelo" e "Importar planilha". Regras:

- O **SKU** identifica o produto: existe, atualiza; não existe, cria.
- Obrigatórias: `sku`, `nome`, `animal`, `preco`. Animal, departamento e subdepartamento aceitam nome ou código já cadastrados. Marca nova é criada sozinha.
- Preço aceita `12,90` e `1.234,56`. O promocional não pode passar do preço. Preço e promocional valem para o **site**.
- `estoque` é o saldo desejado; a diferença vira um movimento de estoque.
- Célula vazia em produto existente mantém o valor atual.
- A tela começa em "Só validar, sem gravar": mostra os erros por linha sem mexer no banco. Linhas com erro não impedem as boas. Cada importação fica registrada em "Importações de planilha".

## Canais, vitrines e CRM

- **Canais**: `site`, `mercado_livre`, `amazon`. Cada produto tem uma linha por canal com `publicado`, preço, preço promocional e ID no canal. Mudou o preço, o gatilho do banco grava o histórico.
- **Vitrines da home**: Ofertas, Mais vendidos e Destaques. Cada uma é **automática** (regra do sistema: ofertas = produtos em promoção; mais vendidos = vendas dos últimos 90 dias em todos os canais) ou **manual** (você escolhe os produtos e a ordem).
- **CRM**: Pedidos de todos os canais, Clientes, **Vendas por produto e canal** e **Oportunidades para o site** (produtos que vendem nos marketplaces e ainda não estão publicados no site, com a ação "Publicar no site").

## API para o site

`Authorization: Bearer <chave>`. Chaves são criadas em **Chaves de API** (o valor aparece uma única vez; no banco fica só o hash) ou por `criar_chave_api`. Escopos: `site` (lê e envia pedidos) e `leitura`.

| Método e caminho | O que faz |
| --- | --- |
| `GET /api/v1/saude/` | Verificação de saúde (sem chave) |
| `GET /api/v1/catalogo/taxonomia/` | Animais, departamentos e tipos que têm produto no site (menu) |
| `GET /api/v1/catalogo/produtos/` | Lista com filtros, busca, ordenação, paginação e facetas |
| `GET /api/v1/catalogo/produtos/<slug>/` | Detalhe do produto |
| `GET /api/v1/vitrines/` | Vitrines da home já resolvidas |
| `POST /api/v1/pedidos/` | Registra o pedido do site e baixa o estoque |

Filtros da lista: `escopo_animal`, `escopo_departamento`, `escopo_ofertas=1`, `q` (define a base das facetas) e `animal`, `departamento`, `subdepartamento`, `marca`, `faixa` (`ate-50`, `50-100`, `100-200`, `acima-200`), `promo=1`, `ordem` (`relevancia`, `menor-preco`, `maior-preco`, `nome`, `novidades`), `pagina`, `tamanho`.

O preço de cada item do pedido **vem do backoffice**, nunca do site. O pedido é idempotente por `numero_externo` e atômico: se faltar estoque em qualquer item, nada é gravado (`409`). SKU fora do site responde `422`.

## Estrutura

```
db/sql/            esquema do banco em SQL
backoffice/
  models/          models sem migração (managed = False)
  services/        regras: estoque, canais, pedidos, importação Excel, chaves de API
  selectors/       consultas de leitura (o que o site enxerga)
  api/             endpoints, autenticação por chave
  admin/           telas do Django Admin
  perfis.py        níveis de acesso
  integracoes/     marketplaces (fase 3)
```

## Próximas fases

1. **Site consumindo a API** (projeto `entrepatas`): trocar a leitura direta do banco por chamadas a esta API, com cache, e enviar os pedidos para cá.
2. **Mercado Livre e Amazon** (`integracoes/`): importar anúncios e pedidos para o CRM (`anuncio_externo`, `pedido`), vincular anúncios aos produtos por SKU/GTIN e publicar produto, preço e estoque a partir do backoffice. Precisa de contas de desenvolvedor: Mercado Livre (app com OAuth2) e Amazon (Selling Partner API).
3. Frete e regras comerciais (hoje o site envia o frete no pedido) passando a ser configuradas aqui.
