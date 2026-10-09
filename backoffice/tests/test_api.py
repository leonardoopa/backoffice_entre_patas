import json
from decimal import Decimal

from django.test import TestCase

from backoffice.models import Pedido, Vitrine, VitrineItem
from backoffice.services.estoque import saldo_atual

from .fabricas import cabecalho_auth, criar_catalogo

BASE = "/api/v1"


class AutenticacaoTests(TestCase):
    def test_saude_nao_exige_chave(self):
        self.assertEqual(self.client.get(f"{BASE}/saude/").json(), {"status": "ok"})

    def test_sem_chave_ou_com_chave_falsa(self):
        self.assertEqual(self.client.get(f"{BASE}/catalogo/produtos/").status_code, 401)
        resposta = self.client.get(f"{BASE}/catalogo/produtos/", HTTP_AUTHORIZATION="Bearer abcd1234.falsa")
        self.assertEqual(resposta.status_code, 401)

    def test_chave_inativa_e_recusada(self):
        from backoffice.models import ChaveApi

        cabecalho = cabecalho_auth()
        ChaveApi.objects.update(ativa=False)
        self.assertEqual(self.client.get(f"{BASE}/vitrines/", **cabecalho).status_code, 401)

    def test_chave_so_de_leitura_nao_cria_pedido(self):
        resposta = self.client.post(f"{BASE}/pedidos/", "{}", content_type="application/json", **cabecalho_auth("leitura"))
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(self.client.get(f"{BASE}/vitrines/", **cabecalho_auth("leitura")).status_code, 200)

    def test_hash_da_chave_nunca_guarda_o_texto_puro(self):
        from backoffice.models import ChaveApi
        from backoffice.services.chaves_api import gerar_chave

        registro, chave = gerar_chave("x", "site")
        self.assertNotIn(chave, registro.hash_chave)
        self.assertEqual(len(ChaveApi.objects.get(pk=registro.pk).hash_chave), 64)


class CatalogoApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.c = criar_catalogo()
        cls.auth = cabecalho_auth()

    def get(self, caminho, **params):
        return self.client.get(f"{BASE}{caminho}", params, **self.auth).json()

    def slugs(self, resposta):
        return [i["sku"] for i in resposta["itens"]]

    def test_so_lista_produtos_publicados_no_site(self):
        resposta = self.get("/catalogo/produtos/")
        self.assertEqual(set(self.slugs(resposta)), {"RAC-1", "BOL-1", "RAC-G"})
        self.assertEqual(resposta["total"], 3)

    def test_produto_inativo_some_mesmo_publicado(self):
        self.c["bola"].ativo = False
        self.c["bola"].save()
        self.assertNotIn("BOL-1", self.slugs(self.get("/catalogo/produtos/")))

    def test_campos_do_produto(self):
        item = next(i for i in self.get("/catalogo/produtos/")["itens"] if i["sku"] == "RAC-1")
        self.assertEqual((item["preco"], item["preco_promocional"], item["preco_final"]), ("100.00", "80.00", "80.00"))
        self.assertEqual((item["estoque"], item["marca"]["nome"], item["animal"]["slug"]), (5, "NutriPet", "caes"))
        self.assertEqual(item["subdepartamento"]["slug"], "racao-seca")

    def test_usa_o_preco_do_canal_site_e_nao_o_de_referencia(self):
        from backoffice.models import ProdutoCanal

        ProdutoCanal.objects.filter(produto=self.c["bola"], canal__codigo="site").update(preco=Decimal("45.00"))
        item = self.get("/catalogo/produtos/bola/".replace("produtos/bola/", "produtos/bol-1/"))
        self.assertEqual(item["preco_final"], "45.00")

    def test_filtros(self):
        self.assertEqual(self.slugs(self.get("/catalogo/produtos/", animal="gatos")), ["RAC-G"])
        self.assertEqual(self.slugs(self.get("/catalogo/produtos/", departamento="brinquedos")), ["BOL-1"])
        self.assertEqual(self.slugs(self.get("/catalogo/produtos/", subdepartamento="racao-umida")), ["RAC-G"])
        self.assertEqual(set(self.slugs(self.get("/catalogo/produtos/", marca="nutripet"))), {"RAC-1", "RAC-G"})
        self.assertEqual(self.slugs(self.get("/catalogo/produtos/", promo="1")), ["RAC-1"])
        self.assertEqual(self.slugs(self.get("/catalogo/produtos/", faixa="50-100")), ["RAC-1"])

    def test_escopo_define_a_base_das_facetas(self):
        resposta = self.get("/catalogo/produtos/", escopo_animal="caes", marca="nutripet")
        self.assertEqual(self.slugs(resposta), ["RAC-1"])
        self.assertEqual({m["slug"] for m in resposta["facetas"]["marcas"]}, {"nutripet", "patafeliz"})
        self.assertEqual([a["slug"] for a in resposta["facetas"]["animais"]], ["caes"])

    def test_subdepartamentos_so_aparecem_com_departamento(self):
        self.assertEqual(self.get("/catalogo/produtos/")["facetas"]["subdepartamentos"], [])
        subs = self.get("/catalogo/produtos/", departamento="racoes")["facetas"]["subdepartamentos"]
        self.assertEqual([s["slug"] for s in subs], ["racao-seca", "racao-umida"])

    def test_busca_ignora_acento_e_maiuscula(self):
        for termo in ("racao", "RAÇÃO", "ração premium"):
            self.assertIn("RAC-1", self.slugs(self.get("/catalogo/produtos/", q=termo)), termo)
        self.assertEqual(self.slugs(self.get("/catalogo/produtos/", q="ração premium")), ["RAC-1"])
        self.assertEqual(self.slugs(self.get("/catalogo/produtos/", q="nutripet")).count("RAC-1"), 1)

    def test_ordenacao(self):
        self.assertEqual(self.slugs(self.get("/catalogo/produtos/", ordem="menor-preco")), ["BOL-1", "RAC-1", "RAC-G"])
        self.assertEqual(self.slugs(self.get("/catalogo/produtos/", ordem="maior-preco")), ["RAC-G", "RAC-1", "BOL-1"])
        self.assertEqual(self.slugs(self.get("/catalogo/produtos/", ordem="invalida"))[0:1], self.slugs(self.get("/catalogo/produtos/"))[0:1])

    def test_paginacao(self):
        resposta = self.get("/catalogo/produtos/", tamanho=2, ordem="nome")
        self.assertEqual((len(resposta["itens"]), resposta["paginas"], resposta["total"]), (2, 2, 3))
        self.assertEqual(len(self.get("/catalogo/produtos/", tamanho=2, pagina=2, ordem="nome")["itens"]), 1)
        self.assertLessEqual(self.get("/catalogo/produtos/", tamanho=100000)["tamanho"], 100)

    def test_detalhe_e_404(self):
        self.assertEqual(self.get("/catalogo/produtos/rac-1/")["sku"], "RAC-1")
        self.assertEqual(self.client.get(f"{BASE}/catalogo/produtos/ocu-1/", **self.auth).status_code, 404)
        self.assertEqual(self.client.get(f"{BASE}/catalogo/produtos/nao-existe/", **self.auth).status_code, 404)

    def test_taxonomia_so_tem_o_que_esta_no_site(self):
        animais = {a["slug"]: a for a in self.get("/catalogo/taxonomia/")["animais"]}
        deps_caes = {d["slug"] for d in animais["caes"]["departamentos"]}
        self.assertEqual(deps_caes, {"racoes", "brinquedos"})
        racoes_gatos = next(d for d in animais["gatos"]["departamentos"] if d["slug"] == "racoes")
        self.assertEqual([s["slug"] for s in racoes_gatos["subdepartamentos"]], ["racao-umida"])


class VitrinesApiTests(TestCase):
    def setUp(self):
        self.c = criar_catalogo()
        self.auth = cabecalho_auth()

    def vitrines(self):
        return self.client.get(f"{BASE}/vitrines/", **self.auth).json()

    def skus(self, vitrine):
        return [i["sku"] for i in vitrine["itens"]]

    def test_ofertas_sao_automaticas_e_so_com_promocao(self):
        self.assertEqual(self.skus(self.vitrines()["ofertas"]), ["RAC-1"])

    def test_destaques_manuais_respeitam_posicao_e_ignoram_nao_publicados(self):
        vitrine = Vitrine.objects.get(codigo="destaques")
        for posicao, produto in ((2, self.c["bola"]), (1, self.c["gato"]), (0, self.c["oculto"])):
            VitrineItem.objects.create(vitrine=vitrine, produto=produto, posicao=posicao)
        self.assertEqual(self.skus(self.vitrines()["destaques"]), ["RAC-G", "BOL-1"])

    def test_vitrine_inativa_nao_aparece(self):
        Vitrine.objects.filter(codigo="ofertas").update(ativa=False)
        self.assertNotIn("ofertas", self.vitrines())

    def test_mais_vendidos_segue_as_vendas_reais(self):
        from backoffice.services.pedidos import registrar_pedido_site

        registrar_pedido_site(numero_externo="1", itens=[{"sku": "BOL-1", "quantidade": 3}])
        registrar_pedido_site(numero_externo="2", itens=[{"sku": "RAC-G", "quantidade": 1}])
        self.assertEqual(self.skus(self.vitrines()["mais_vendidos"]), ["BOL-1", "RAC-G"])

    def test_mais_vendidos_ignora_pedido_cancelado(self):
        from backoffice.services.pedidos import registrar_pedido_site

        resultado = registrar_pedido_site(numero_externo="1", itens=[{"sku": "BOL-1", "quantidade": 9}])
        registrar_pedido_site(numero_externo="2", itens=[{"sku": "RAC-G", "quantidade": 1}])
        Pedido.objects.filter(pk=resultado.pedido.pk).update(status="cancelado")
        self.assertEqual(self.skus(self.vitrines()["mais_vendidos"]), ["RAC-G"])

    def test_mais_vendidos_sem_vendas_usa_avaliacoes_como_reserva(self):
        self.assertEqual(len(self.vitrines()["mais_vendidos"]["itens"]), 3)

    def test_limite_da_vitrine(self):
        Vitrine.objects.filter(codigo="mais_vendidos").update(limite=1)
        self.assertEqual(len(self.vitrines()["mais_vendidos"]["itens"]), 1)

    def test_alterar_modo_para_manual_troca_a_regra(self):
        Vitrine.objects.filter(codigo="ofertas").update(modo="manual")
        self.assertEqual(self.vitrines()["ofertas"]["itens"], [])
        VitrineItem.objects.create(vitrine=Vitrine.objects.get(codigo="ofertas"), produto=self.c["bola"], posicao=0)
        self.assertEqual(self.skus(self.vitrines()["ofertas"]), ["BOL-1"])


class PedidosApiTests(TestCase):
    def setUp(self):
        self.c = criar_catalogo()
        self.auth = cabecalho_auth()

    def post(self, dados, bruto=None):
        corpo = bruto if bruto is not None else json.dumps(dados)
        return self.client.post(f"{BASE}/pedidos/", corpo, content_type="application/json", **self.auth)

    def test_cria_pedido_com_preco_do_backoffice_e_baixa_estoque(self):
        resposta = self.post({
            "numero_externo": "S-1", "frete": "19.90",
            "cliente": {"id_externo": "u1", "nome": "Ana", "email": "ana@example.com"},
            "entrega": {"cidade": "SP"},
            "itens": [{"sku": "RAC-1", "quantidade": 2, "preco_unitario": "0.01"}, {"sku": "BOL-1", "quantidade": 1}],
        })
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.json()["total"], "209.90")
        pedido = Pedido.objects.get(numero_externo="S-1")
        self.assertEqual((pedido.subtotal, pedido.frete, pedido.cliente.email, pedido.canal.codigo), (Decimal("190.00"), Decimal("19.90"), "ana@example.com", "site"))
        self.assertEqual(pedido.itens.get(sku_externo="RAC-1").preco_unitario, Decimal("80.00"))
        self.assertEqual((saldo_atual(self.c["racao"]), saldo_atual(self.c["bola"])), (3, 49))

    def test_pedido_repetido_nao_baixa_estoque_de_novo(self):
        corpo = {"numero_externo": "S-1", "itens": [{"sku": "RAC-1", "quantidade": 2}]}
        self.assertEqual(self.post(corpo).status_code, 201)
        self.assertEqual(self.post(corpo).status_code, 200)
        self.assertEqual((Pedido.objects.count(), saldo_atual(self.c["racao"])), (1, 3))

    def test_estoque_insuficiente_desfaz_tudo(self):
        resposta = self.post({"numero_externo": "S-2", "itens": [{"sku": "BOL-1", "quantidade": 1}, {"sku": "RAC-1", "quantidade": 6}]})
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(resposta.json()["sku"], "RAC-1")
        self.assertEqual((Pedido.objects.count(), saldo_atual(self.c["bola"])), (0, 50))

    def test_sku_inexistente_ou_fora_do_site(self):
        for sku in ("NAO-EXISTE", "OCU-1"):
            resposta = self.post({"numero_externo": f"S-{sku}", "itens": [{"sku": sku, "quantidade": 1}]})
            self.assertEqual((resposta.status_code, resposta.json()["sku"]), (422, sku))

    def test_corpo_invalido(self):
        self.assertEqual(self.post(None, bruto="lixo").status_code, 400)
        self.assertEqual(self.post({"itens": []}).status_code, 400)
        self.assertEqual(self.post({"numero_externo": "X", "itens": []}).status_code, 422)
        self.assertEqual(self.post({"numero_externo": "X", "itens": [{"sku": "RAC-1", "quantidade": 0}]}).status_code, 422)
        self.assertEqual(self.post({"numero_externo": "X", "itens": [{"sku": "RAC-1"}]}).status_code, 422)
        self.assertEqual(self.post({"numero_externo": "X", "frete": "-5", "itens": [{"sku": "RAC-1", "quantidade": 1}]}).status_code, 422)

    def test_skus_repetidos_no_pedido_sao_somados(self):
        self.post({"numero_externo": "S-3", "itens": [{"sku": "BOL-1", "quantidade": 1}, {"sku": "BOL-1", "quantidade": 2}]})
        self.assertEqual(Pedido.objects.get().itens.get().quantidade, 3)
        self.assertEqual(saldo_atual(self.c["bola"]), 47)

    def test_pedido_cria_movimento_de_venda_com_referencia(self):
        self.post({"numero_externo": "S-4", "itens": [{"sku": "BOL-1", "quantidade": 1}]})
        movimento = self.c["bola"].movimentos.first()
        self.assertEqual((movimento.motivo, movimento.referencia, movimento.quantidade), ("venda", "site:S-4", -1))

    def test_get_no_endpoint_de_pedidos_nao_e_permitido(self):
        self.assertEqual(self.client.get(f"{BASE}/pedidos/", **self.auth).status_code, 405)
