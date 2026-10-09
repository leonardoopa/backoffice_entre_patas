from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from backoffice.models import ChaveApi, ImportacaoPlanilha, Produto, ProdutoCanal
from backoffice.perfis import PERFIS

from .fabricas import SENHA, criar_catalogo, criar_taxonomia, criar_usuario, planilha


class PerfisTests(TestCase):
    def setUp(self):
        call_command("criar_perfis", verbosity=0)

    def codenames(self, perfil):
        return set(Group.objects.get(name=perfil).permissions.values_list("codename", flat=True))

    def test_todos_os_perfis_existem(self):
        self.assertEqual(set(Group.objects.values_list("name", flat=True)), {p.nome for p in PERFIS})

    def test_comando_e_idempotente(self):
        antes = self.codenames("Gerente comercial")
        call_command("criar_perfis", verbosity=0)
        self.assertEqual(self.codenames("Gerente comercial"), antes)
        self.assertEqual(Group.objects.count(), len(PERFIS))

    def test_gerente_altera_preco_e_publica_mas_nao_gerencia_chaves(self):
        perms = self.codenames("Gerente comercial")
        self.assertTrue({"alterar_preco", "publicar_canal", "importar_planilha", "change_produto"} <= perms)
        self.assertFalse({"add_chaveapi", "change_chaveapi", "view_chaveapi", "add_user"} & perms)

    def test_catalogo_importa_mas_nao_altera_preco_nem_publica(self):
        perms = self.codenames("Catálogo e estoque")
        self.assertIn("importar_planilha", perms)
        self.assertFalse({"alterar_preco", "publicar_canal", "change_produtocanal", "view_pedido"} & perms)

    def test_atendimento_so_muda_status_de_pedido(self):
        perms = self.codenames("Atendimento")
        self.assertIn("change_pedido", perms)
        self.assertFalse({"change_produto", "add_produto", "alterar_preco", "delete_pedido"} & perms)

    def test_leitura_so_tem_view(self):
        perms = self.codenames("Leitura")
        self.assertTrue(perms)
        self.assertTrue(all(p.startswith("view_") for p in perms), perms)

    def test_administrador_gerencia_usuarios_e_chaves(self):
        perms = self.codenames("Administrador")
        self.assertTrue({"add_user", "change_group", "add_chaveapi", "alterar_preco"} <= perms)


class AdminAcessoTests(TestCase):
    def setUp(self):
        call_command("criar_perfis", verbosity=0)
        self.c = criar_catalogo()

    def entrar(self, usuario):
        self.assertTrue(self.client.login(username=usuario.username, password=SENHA))

    def test_superusuario_abre_todas_as_listagens(self):
        self.entrar(criar_usuario("root", superuser=True))
        for modelo in ("animal", "departamento", "marca", "produto", "estoquemovimento", "canal", "historicopreco",
                       "anuncioexterno", "vitrine", "pedido", "cliente", "vendaprodutocanal", "oportunidadesite",
                       "importacaoplanilha", "chaveapi"):
            resposta = self.client.get(reverse(f"admin:backoffice_{modelo}_changelist"))
            self.assertEqual(resposta.status_code, 200, modelo)

    def test_paginas_de_edicao_do_produto(self):
        self.entrar(criar_usuario("root", superuser=True))
        self.assertEqual(self.client.get(reverse("admin:backoffice_produto_change", args=[self.c["racao"].pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:backoffice_produto_add")).status_code, 200)

    def test_sem_perfil_nao_ve_nada(self):
        self.entrar(criar_usuario("sem-perfil"))
        self.assertEqual(self.client.get(reverse("admin:backoffice_produto_changelist")).status_code, 403)

    def test_catalogo_nao_edita_preco_mas_gerente_edita(self):
        url = reverse("admin:backoffice_produto_change", args=[self.c["racao"].pk])
        self.entrar(criar_usuario("cat", "Catálogo e estoque"))
        html = self.client.get(url).content.decode()
        self.assertNotIn('name="preco"', html)
        self.assertNotIn('name="canais-0-preco"', html)
        self.client.logout()
        self.entrar(criar_usuario("ger", "Gerente comercial"))
        html = self.client.get(url).content.decode()
        self.assertIn('name="preco"', html)
        self.assertIn('name="canais-0-preco"', html)

    def test_catalogo_nao_consegue_forcar_preco_por_post(self):
        self.entrar(criar_usuario("cat", "Catálogo e estoque"))
        url = reverse("admin:backoffice_produto_change", args=[self.c["racao"].pk])
        dados = self.client.get(url).context["adminform"].form.initial
        self.client.post(url, {**{k: ("" if v is None else v) for k, v in dados.items() if v is not None}, "preco": "1.00", "nome": "Hack"})
        self.c["racao"].refresh_from_db()
        self.assertEqual(str(self.c["racao"].preco), "100.00")

    def test_leitura_nao_pode_alterar(self):
        self.entrar(criar_usuario("leitor", "Leitura"))
        url = reverse("admin:backoffice_produto_change", args=[self.c["racao"].pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {"nome": "x"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:backoffice_produto_add")).status_code, 403)

    def test_criar_produto_pelo_admin_nasce_fora_do_site_com_canais_e_estoque(self):
        self.entrar(criar_usuario("ger", "Gerente comercial"))
        resposta = self.client.post(reverse("admin:backoffice_produto_add"), {
            "sku": "NOVO-1", "nome": "Novo", "slug": "novo", "animal": self.c["caes"].pk, "preco": "50.00",
            "tipo_arte": "caixa", "cor_arte": "#17375e", "avaliacao": "0", "num_avaliacoes": "0", "ativo": "on",
        })
        self.assertEqual(resposta.status_code, 302)
        produto = Produto.objects.get(sku="NOVO-1")
        self.assertEqual(ProdutoCanal.objects.filter(produto=produto).count(), 3)
        self.assertFalse(ProdutoCanal.objects.filter(produto=produto, publicado=True).exists())
        self.assertEqual(produto.estoque.quantidade, 0)

    def test_publicar_e_retirar_do_site_em_lote(self):
        self.entrar(criar_usuario("ger", "Gerente comercial"))
        url = reverse("admin:backoffice_produto_changelist")
        self.client.post(url, {"action": "retirar_do_site", "_selected_action": [self.c["racao"].pk]})
        self.assertFalse(ProdutoCanal.objects.get(produto=self.c["racao"], canal__codigo="site").publicado)
        self.client.post(url, {"action": "publicar_no_site", "_selected_action": [self.c["racao"].pk]})
        self.assertTrue(ProdutoCanal.objects.get(produto=self.c["racao"], canal__codigo="site").publicado)

    def test_catalogo_nao_tem_a_acao_de_publicar(self):
        self.entrar(criar_usuario("cat", "Catálogo e estoque"))
        html = self.client.get(reverse("admin:backoffice_produto_changelist")).content.decode()
        self.assertNotIn("publicar_no_site", html)

    def test_movimento_de_estoque_pelo_admin_e_validado(self):
        self.entrar(criar_usuario("cat", "Catálogo e estoque"))
        url = reverse("admin:backoffice_estoquemovimento_add")
        invalido = self.client.post(url, {"produto": self.c["racao"].pk, "quantidade": -99, "motivo": "ajuste", "referencia": ""})
        self.assertEqual(invalido.status_code, 200)
        self.assertContains(invalido, "Estoque insuficiente")
        ok = self.client.post(url, {"produto": self.c["racao"].pk, "quantidade": 4, "motivo": "entrada", "referencia": "nf"})
        self.assertEqual(ok.status_code, 302)
        self.assertEqual(self.c["racao"].estoque.__class__.objects.get(produto=self.c["racao"]).quantidade, 9)


class ImportacaoAdminTests(TestCase):
    def setUp(self):
        call_command("criar_perfis", verbosity=0)
        criar_taxonomia()
        self.url = reverse("admin:backoffice_produto_importar")

    def entrar(self, usuario):
        self.client.login(username=usuario.username, password=SENHA)

    def enviar(self, linhas, validar):
        arquivo = planilha(linhas)
        arquivo.name = "produtos.xlsx"
        dados = {"arquivo": arquivo}
        if validar:
            dados["apenas_validar"] = "on"
        return self.client.post(self.url, dados)

    def test_so_quem_tem_permissao_importa(self):
        self.entrar(criar_usuario("atend", "Atendimento"))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:backoffice_produto_modelo")).status_code, 403)

    def test_baixar_modelo(self):
        self.entrar(criar_usuario("cat", "Catálogo e estoque"))
        resposta = self.client.get(reverse("admin:backoffice_produto_modelo"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("spreadsheetml", resposta["Content-Type"])

    def test_validar_nao_grava_e_importar_grava(self):
        self.entrar(criar_usuario("cat", "Catálogo e estoque"))
        linhas = [["A-1", "Produto A", "caes", "10", "", 3, "", "", ""]]
        resposta = self.enviar(linhas, validar=True)
        self.assertContains(resposta, "nada foi gravado")
        self.assertEqual(Produto.objects.count(), 0)
        resposta = self.enviar(linhas, validar=False)
        self.assertContains(resposta, "Importação concluída")
        self.assertEqual((Produto.objects.count(), ImportacaoPlanilha.objects.count()), (1, 1))

    def test_erros_aparecem_na_tela(self):
        self.entrar(criar_usuario("cat", "Catálogo e estoque"))
        resposta = self.enviar([["A-1", "Produto A", "dragoes", "10", "", "", "", "", ""]], validar=False)
        self.assertContains(resposta, "animal")
        self.assertContains(resposta, "não cadastrado")

    def test_rejeita_arquivo_que_nao_e_xlsx(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.entrar(criar_usuario("cat", "Catálogo e estoque"))
        resposta = self.client.post(self.url, {"arquivo": SimpleUploadedFile("x.csv", b"a,b")})
        self.assertContains(resposta, "Envie um arquivo .xlsx")


class ChaveApiAdminTests(TestCase):
    def test_chave_nova_aparece_uma_vez_e_so_o_hash_fica_guardado(self):
        usuario = criar_usuario("root", superuser=True)
        self.client.login(username=usuario.username, password=SENHA)
        resposta = self.client.post(reverse("admin:backoffice_chaveapi_add"), {"nome": "Site", "escopo": "site"}, follow=True)
        mensagens = [str(m) for m in resposta.context["messages"]]
        chave = mensagens[0].split(": ")[-1]
        registro = ChaveApi.objects.get(nome="Site")
        self.assertTrue(chave.startswith(registro.prefixo + "."))
        self.assertNotIn(chave, registro.hash_chave)
        self.assertEqual(self.client.get("/api/v1/vitrines/", HTTP_AUTHORIZATION=f"Bearer {chave}").status_code, 200)
