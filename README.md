# EntrePatas Backoffice

Fonte única de verdade da EntrePatas. Aqui ficam catálogo, preços por canal, estoque, vitrines da home e o CRM de vendas. O site (www.entrepatas.com) e os marketplaces (Mercado Livre e Amazon) consomem os dados daqui.

```
Excel / cadastro manual ──► Backoffice (PostgreSQL + Django Admin) ──► API ──► Site
                                         ▲                                  └─► Marketplaces (fase 3)
                                         └── pedidos e anúncios dos canais voltam para o CRM
```

## Como o banco é criado

O esquema nasce em **SQL puro**, em `db/sql/`: `V0001__schema.sql` (catálogo, canais, vendas, vitrines) e `V0002__operacao_marketplaces.sql` (reservas de estoque, fila de sincronização, variações, margem, auditoria, devoluções). Tabelas, restrições, índices, gatilhos, funções e views. O Django só mostra e edita esses dados: os models têm `managed = False` e não geram tabelas.

Para o banco ser aplicado igual em desenvolvimento, testes e produção, cada arquivo `.sql` é executado por uma migração do Django (`RunSQL`). Fluxo para mudar o banco:

1. Crie `db/sql/V000N__descricao.sql` (nunca edite um arquivo que já foi aplicado em algum ambiente).
2. Atualize os models em `backoffice/models/` para refletir a mudança.
3. Rode `docker compose run --rm web python manage.py makemigrations backoffice`.
4. Abra a migração gerada e acrescente `arquivo_sql("V000N__descricao.sql")` no início de `operations` (veja `0001_initial.py`).
5. Rode os testes: `test_schema` falha se algum `.sql` não estiver ligado a uma migração.

O que o SQL garante sozinho, mesmo fora do Django:

- preço promocional nunca maior que o preço, período de promoção coerente, estoque nunca negativo, GTIN (8, 12, 13 ou 14 dígitos) e NCM (8 dígitos) válidos;
- histórico automático de mudança de preço, de status do pedido e auditoria de quem alterou o quê (gatilhos);
- fila de sincronização com os marketplaces alimentada por gatilho, sem duplicar item pendente;
- as views de CRM, de margem e de pendências para marketplace.

## Rodando

Pré-requisito: Docker.

```bash
docker compose up --build
docker compose exec web python manage.py createsuperuser
```

Abra http://localhost:8500. No modo de desenvolvimento a primeira subida cria o banco, aplica o SQL, cria os perfis de acesso e carrega 65 produtos, estoque e 120 pedidos fictícios nos três canais. O serviço `worker` sobe junto (veja "Estoque, fila de sincronização e worker").

```bash
docker compose exec web python manage.py test          # testes (PostgreSQL)
docker compose exec web python manage.py criar_perfis  # recria os perfis de acesso
docker compose exec web python manage.py criar_chave_api site-producao site   # a chave aparece uma única vez
docker compose exec web python manage.py executar_worker --uma-vez            # roda um ciclo do worker
docker compose logs -f web                             # logs
```

Produção: `cp .env.example .env`, preencha `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `POSTGRES_PASSWORD` e rode `docker compose -f docker-compose.yml up -d --build`. Coloque um proxy com HTTPS na frente (`DJANGO_HTTPS=1`).

## Níveis de acesso

Usuários são criados em **Usuários**, com "Membro da equipe" marcado e um **perfil** (grupo). Os perfis são recriados por `criar_perfis` a cada subida.

| Perfil | Pode |
| --- | --- |
| Administrador | Tudo, inclusive usuários, perfis e chaves de API |
| Gerente comercial | Catálogo, **preços**, **publicar nos canais**, vitrines, devoluções e importar planilhas; vê vendas e margens; não vê chaves de API |
| Catálogo e estoque | Cadastrar e editar produtos, importar planilhas, movimentar estoque. **Não** altera preços nem publica |
| Atendimento | Vê pedidos e clientes, muda o status do pedido e trata devoluções |
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

- **Canais**: `site`, `mercado_livre`, `amazon`. Cada produto tem uma linha por canal com `publicado`, preço, preço promocional (com início e fim opcionais) e ID no canal. Mudou o preço, o gatilho do banco grava o histórico com o autor. Fora do período, o preço promocional deixa de valer sozinho (`preco_vigente` no SQL).
- **Margem**: cada canal tem comissão e margem mínima. A view de margem desconta comissão e custo do preço vigente; **Alertas de margem** lista o que está abaixo do mínimo.
- **Vitrines da home**: Ofertas, Mais vendidos e Destaques. Cada uma é **automática** (regra do sistema: ofertas = produtos em promoção; mais vendidos = vendas dos últimos 90 dias em todos os canais) ou **manual** (você escolhe os produtos e a ordem).
- **CRM**: Pedidos de todos os canais, Clientes, **Vendas por produto e canal** e **Oportunidades para o site** (produtos que vendem nos marketplaces e ainda não estão publicados no site, com a ação "Publicar no site").

## Estoque, fila de sincronização e worker

- **Estoque vendável** = saldo − reservado − estoque de segurança, nunca abaixo de zero. A reserva (30 minutos por padrão) segura a quantidade enquanto o pedido de um canal é fechado; a reserva vencida é liberada pelo worker.
- **Fila de sincronização** (`fila_sync`): mudar preço, publicação ou estoque de um produto publicado em marketplace enfileira o envio por gatilho. Há no máximo um item pendente por canal, produto e tipo. Falha tenta de novo com espera crescente (2, 4, 8... minutos, até 6 horas) e vira `erro` depois de 8 tentativas; o erro aparece na tela **Fila de sincronização**.
- **Worker** (`executar_worker`, serviço `worker` do compose): a cada 30 segundos libera reservas vencidas e processa a fila. Com `MARKETPLACES_SIMULADOS=1` (padrão no desenvolvimento) o envio só gera log `sync_simulada`; os adaptadores reais do Mercado Livre e da Amazon entram em `repositories/marketplaces/` na fase 3.

## Produto para marketplaces

- Dados que os marketplaces exigem: GTIN, NCM, peso (g), altura, largura e comprimento (cm), marca, descrição e várias fotos (**Imagens** no produto).
- **Pendências para marketplace** mostra o que falta em cada produto (sem GTIN, NCM, peso, dimensões, marca, imagem ou com descrição curta).
- **Variações**: produtos do mesmo **Grupo de produtos** (ex.: ração de 3 kg e de 10 kg) diferem por `variacao`, cada um com SKU, preço e estoque próprios. O site mostra as variações na página do produto.

## Pedidos, pagamento e devoluções

- Pedido guarda forma de pagamento (Pix, cartão, boleto, marketplace), status do pagamento, referência e parcelas. Toda mudança de status entra no **histórico do pedido** por gatilho.
- **Devoluções**: criadas a partir de um item do pedido, com motivo e status (solicitada, aprovada, recebida, reembolsada, recusada), só nessa ordem de transições. Não dá para devolver mais do que foi comprado. Ao marcar como recebida, o item volta ao estoque.
- **Auditoria**: alterações de produto, preço por canal, vitrines, canais, pedidos, devoluções, grupos e chaves de API gravam quem fez (usuário do admin ou `api:<nome da chave>`), o que mudou e quando. Movimentos de estoque e histórico de preço também guardam o autor. A tela **Auditoria** é só de leitura.

## API para o site

`Authorization: Bearer <chave>`. Chaves são criadas em **Chaves de API** (o valor aparece uma única vez; no banco fica só o hash) ou por `criar_chave_api`. Escopos: `site` (lê e envia pedidos) e `leitura`.

| Método e caminho | O que faz |
| --- | --- |
| `GET /api/v1/saude/` | Verificação de saúde (sem chave) |
| `GET /api/v1/catalogo/taxonomia/` | Animais, departamentos e tipos que têm produto no site (menu) |
| `GET /api/v1/catalogo/produtos/` | Lista com filtros, busca, ordenação, paginação e facetas |
| `GET /api/v1/catalogo/produtos/<slug>/` | Detalhe do produto, com fotos e variações |
| `GET /api/v1/vitrines/` | Vitrines da home já resolvidas |
| `POST /api/v1/pedidos/` | Registra o pedido do site e baixa o estoque |
| `GET /api/v1/pedidos/<numero>/` | Pedido com itens, entrega, pagamento e histórico de status |
| `POST /api/v1/pedidos/<numero>/pagamento/` | Atualiza o pagamento (`status`: pendente, aprovado, recusado, estornado; `referencia` opcional) |
| `GET /api/v1/clientes/<id>/pedidos/` | Pedidos de um cliente (o site usa o id da conta ou `visitante:<e-mail>`) |

Filtros da lista: `escopo_animal`, `escopo_departamento`, `escopo_ofertas=1`, `q` (define a base das facetas) e `animal`, `departamento`, `subdepartamento`, `marca`, `faixa` (`ate-50`, `50-100`, `100-200`, `acima-200`), `promo=1`, `ordem` (`relevancia`, `menor-preco`, `maior-preco`, `nome`, `novidades`), `pagina`, `tamanho`.

O preço de cada item do pedido **vem do backoffice**, nunca do site. O pedido é idempotente por `numero_externo` e atômico: se faltar estoque em qualquer item, nada é gravado (`409`). SKU fora do site responde `422`. Preço vigente já considera a promoção dentro do período.

## Estrutura (MVC)

Mesma organização do site: back-end em camadas dentro de `backoffice/`, front-end fora do app, em `frontend/`.

```
config/                        settings, urls raiz e configuração de logs
db/sql/                        esquema do banco em SQL
backoffice/
  models/                      M: models sem migração (managed = False)
  repositories/                M: acesso a dados
    site.py                    consultas de leitura que o site enxerga (escopo, filtros, facetas, vitrines)
    precos.py                  preço vigente calculado pelas funções SQL
    marketplaces/              adaptadores dos canais: contratos, simulado e fábrica
  services/                    M: regras de negócio
                               estoque e reservas, canais, pedidos, devoluções, fila de sincronização,
                               pendências, importação Excel, chaves de API, perfis de acesso,
                               auditoria (autor gravado nos gatilhos) e texto
  controllers/                 C: recebem a requisição e chamam os services
    api/                       endpoints JSON, rotas e autenticação por chave
    admin/                     telas do Django Admin
    middleware.py              informa ao banco quem está agindo
  presenters/                  dados prontos para a tela (api.py: JSON da API)
  management/commands/         comandos: seed_demo, criar_perfis, criar_chave_api, executar_worker
  migrations/                  uma migração por arquivo SQL (RunSQL)
  tests/                       espelha as camadas: controllers/, services/, repositories/, support/
frontend/
  templates/admin/             V: telas do admin que sobrescrevem as padrão (importar planilha)
```

Regras de dependência (a seta aponta para quem é usado):

```
controllers -> services -> repositories -> models
controllers -> presenters -> models
services/sincronizacao usa os contratos de repositories/marketplaces
```

- `models` não importa nada do projeto. Só `controllers` conhecem `request` e `JsonResponse`; a leitura da querystring (escopo e filtros do catálogo) fica em `controllers/api/views.py`.
- O Django Admin é registrado por `BackofficeConfig.ready()`, que importa `controllers/admin`.
- Para outro marketplace, implemente `AdaptadorCanal` em `repositories/marketplaces/` e registre-o em `fabrica.py`; o worker e a fila não mudam.

## Próximas fases

1. **Mercado Livre e Amazon** (`repositories/marketplaces/`): trocar o adaptador simulado por adaptadores reais que publicam produto, preço e estoque a partir da fila e importam anúncios e pedidos para o CRM (`anuncio_externo`, `pedido`), vinculando por SKU/GTIN. Precisa de contas de desenvolvedor: Mercado Livre (app com OAuth2) e Amazon (Selling Partner API). Alternativa: integrar um ERP (Bling, Tiny) que já fala com os dois.
2. Frete e regras comerciais (hoje o site calcula o frete e o envia no pedido) passando a ser configuradas aqui.
3. Gateway de pagamento chamando `POST /pedidos/<numero>/pagamento/`, nota fiscal e limite de requisições por chave na API.
