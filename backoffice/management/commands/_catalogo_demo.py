from typing import NamedTuple


class ProdutoDemo(NamedTuple):
    animal: str
    departamento: str
    subdepartamento: str
    nome: str
    marca: str
    preco: str
    promocional: str | None
    tipo: str
    cor: str
    estoque: int
    destaque: bool


ANIMAIS = [("Cães", "🐶"), ("Gatos", "🐱"), ("Pássaros", "🐦"), ("Peixes", "🐟"), ("Roedores", "🐹")]

DEPARTAMENTOS = {
    "racoes": "Rações",
    "petiscos": "Petiscos e Ossos",
    "higiene": "Higiene e Beleza",
    "farmacia": "Farmácia",
    "brinquedos": "Brinquedos",
    "coleiras": "Coleiras, Guias e Peitorais",
    "comedouros": "Comedouros e Bebedouros",
    "camas": "Camas e Casinhas",
    "transporte": "Transporte",
}

TEXTOS = {
    "racoes": (
        "Alimento completo e balanceado, com proteínas de qualidade, vitaminas e minerais para o dia a dia. Siga a tabela de porções da embalagem e mantenha água fresca sempre disponível."
    ),
    "petiscos": (
        "Petisco saboroso para premiar e fortalecer o vínculo com seu pet. Ofereça como complemento, sem substituir a refeição principal."
    ),
    "brinquedos": (
        "Diversão garantida para gastar energia e estimular o instinto natural. Material resistente e seguro. Supervisione as brincadeiras."
    ),
    "higiene": (
        "Cuidado e conforto para a rotina de limpeza do seu pet. Fórmula suave, indicada para uso frequente."
    ),
    "farmacia": (
        "Produto de uso veterinário. Siga a orientação do médico-veterinário e as instruções da bula."
    ),
    "coleiras": (
        "Acessório pensado para o conforto e a segurança nos passeios, com acabamento reforçado e ajuste fácil."
    ),
    "comedouros": (
        "Alimentação e hidratação com praticidade e higiene. Material resistente e fácil de limpar."
    ),
    "transporte": (
        "Segurança e conforto para levar seu pet ao veterinário, a passeios e viagens."
    ),
    "camas": (
        "Espaço macio e aconchegante para o descanso do seu pet, com tecido de fácil limpeza."
    ),
}

SUBDEPARTAMENTOS = {
    "racoes": [("racao-seca", "Ração Seca"), ("racao-umida", "Ração Úmida e Sachês"), ("racao-filhotes", "Filhotes"), ("racao-senior", "Sênior"), ("racao-light", "Light e Controle de Peso")],
    "petiscos": [("ossos-mastigaveis", "Ossos e Mastigáveis"), ("bifinhos-cremosos", "Bifinhos e Cremosos"), ("biscoitos", "Biscoitos"), ("ervas-catnip", "Ervas e Catnip")],
    "higiene": [("shampoos-condicionadores", "Shampoos e Condicionadores"), ("tapetes-areias", "Tapetes e Areias"), ("escovas-pentes", "Escovas e Pentes")],
    "farmacia": [("antipulgas-carrapatos", "Antipulgas e Carrapatos"), ("vermifugos", "Vermífugos"), ("suplementos-vitaminas", "Suplementos e Vitaminas"), ("tratamento-agua", "Tratamento de Água")],
    "brinquedos": [("bolas-frisbees", "Bolas e Frisbees"), ("cordas-mordedores", "Cordas e Mordedores"), ("pelucias", "Pelúcias"), ("arranhadores", "Arranhadores"), ("interativos-exercicio", "Interativos e Exercício")],
    "coleiras": [("coleiras-simples", "Coleiras"), ("peitorais", "Peitorais"), ("guias", "Guias")],
    "comedouros": [("comedouros-potes", "Comedouros"), ("bebedouros-fontes", "Bebedouros e Fontes")],
    "camas": [("camas-almofadas", "Camas e Almofadas"), ("casinhas-tocas", "Casinhas e Tocas")],
    "transporte": [("caixas-transporte", "Caixas de Transporte")],
}

PRODUTOS = [
    ProdutoDemo("caes", "racoes", "racao-seca", "Ração Premium Adultos Frango e Arroz 15kg", "NutriPet", "219.90", '189.90', "saco", "#D96C4A", 40, True),
    ProdutoDemo("caes", "racoes", "racao-filhotes", "Ração Filhotes Raças Pequenas 3kg", "NutriPet", "69.90", None, "saco", "#F2B544", 35, False),
    ProdutoDemo("caes", "racoes", "racao-senior", "Ração Sênior 7+ Frango 10kg", "Natu Pet", "159.90", '139.90', "saco", "#4F9D69", 22, True),
    ProdutoDemo("caes", "racoes", "racao-light", "Ração Light Controle de Peso 10kg", "Natu Pet", "149.90", None, "saco", "#7B6BB3", 18, False),
    ProdutoDemo("caes", "racoes", "racao-umida", "Alimento Úmido Carne ao Molho 280g", "Focinho Feliz", "7.90", None, "lata", "#9A6B3F", 120, False),
    ProdutoDemo("caes", "racoes", "racao-umida", "Alimento Úmido Frango com Legumes 280g", "Focinho Feliz", "7.90", '6.90', "lata", "#D8688C", 110, False),
    ProdutoDemo("caes", "petiscos", "ossos-mastigaveis", "Osso Natural Mini 100g", "Mordida Boa", "29.90", '24.90', "osso", "#F2B544", 60, True),
    ProdutoDemo("caes", "petiscos", "bifinhos-cremosos", "Bifinho Sabor Carne 500g", "Mordida Boa", "24.90", None, "saco", "#C8453B", 70, False),
    ProdutoDemo("caes", "petiscos", "biscoitos", "Biscoito Dental Cuidado Oral 7un", "Focinho Feliz", "18.90", None, "caixa", "#4F9D69", 45, False),
    ProdutoDemo("caes", "petiscos", "ossos-mastigaveis", "Palito Mastigável Frango 10un", "Mordida Boa", "32.90", '27.90', "osso", "#9A6B3F", 38, False),
    ProdutoDemo("caes", "brinquedos", "bolas-frisbees", "Bolinha de Borracha Maciça", "Pata Feliz", "19.90", None, "bola", "#F2B544", 80, True),
    ProdutoDemo("caes", "brinquedos", "cordas-mordedores", "Corda com Nós Trançada", "Pata Feliz", "24.90", '19.90', "osso", "#4A90D9", 55, False),
    ProdutoDemo("caes", "brinquedos", "cordas-mordedores", "Mordedor Osso Resistente G", "Pata Feliz", "39.90", None, "osso", "#D96C4A", 30, False),
    ProdutoDemo("caes", "brinquedos", "pelucias", "Pelúcia Camarão com Apito", "Bicho Chic", "49.90", '44.90', "bola", "#D8688C", 25, False),
    ProdutoDemo("caes", "brinquedos", "bolas-frisbees", "Frisbee Flexível", "Bicho Chic", "29.90", None, "bola", "#2E9CA6", 42, False),
    ProdutoDemo("caes", "higiene", "shampoos-condicionadores", "Shampoo Neutro Pelos Claros 500ml", "Banho Bom", "29.90", None, "frasco", "#4A90D9", 48, False),
    ProdutoDemo("caes", "higiene", "shampoos-condicionadores", "Condicionador Hidratante 500ml", "Banho Bom", "32.90", '27.90', "frasco", "#D8688C", 33, False),
    ProdutoDemo("caes", "higiene", "tapetes-areias", "Tapete Higiênico 30un", "Banho Bom", "74.90", '59.90', "caixa", "#2E9CA6", 0, False),
    ProdutoDemo("caes", "higiene", "escovas-pentes", "Escova Removedora de Pelos", "Bicho Chic", "39.90", None, "caixa", "#7B6BB3", 27, False),
    ProdutoDemo("caes", "farmacia", "antipulgas-carrapatos", "Antipulgas e Carrapatos até 10kg", "VetCare", "89.90", '74.90', "caixa", "#C8453B", 30, True),
    ProdutoDemo("caes", "farmacia", "vermifugos", "Vermífugo 4 Comprimidos", "VetCare", "54.90", None, "caixa", "#2E9CA6", 26, False),
    ProdutoDemo("caes", "farmacia", "suplementos-vitaminas", "Suplemento Articulações 60 Comprimidos", "VetCare", "119.90", '99.90', "frasco", "#7B6BB3", 15, False),
    ProdutoDemo("caes", "coleiras", "coleiras-simples", "Coleira Ajustável M", "Pata Feliz", "34.90", '27.90', "coleira", "#17375E", 40, False),
    ProdutoDemo("caes", "coleiras", "peitorais", "Peitoral Passeio Confort G", "Bicho Chic", "79.90", '69.90', "coleira", "#D96C4A", 24, False),
    ProdutoDemo("caes", "coleiras", "guias", "Guia Retrátil 5m", "Bicho Chic", "69.90", None, "coleira", "#4F9D69", 19, False),
    ProdutoDemo("caes", "comedouros", "comedouros-potes", "Comedouro Inox Antiderrapante", "Pata Feliz", "44.90", None, "pote", "#9A9FAA", 36, False),
    ProdutoDemo("caes", "comedouros", "bebedouros-fontes", "Bebedouro Portátil para Passeio 500ml", "Pata Feliz", "39.90", None, "pote", "#2E9CA6", 33, False),
    ProdutoDemo("caes", "transporte", "caixas-transporte", "Caixa de Transporte Nº 3", "Casa Pet", "169.90", '149.90', "caixa", "#17375E", 14, False),
    ProdutoDemo("caes", "camas", "camas-almofadas", "Cama Redonda Pelúcia M", "Casa Pet", "149.90", '129.90', "cama", "#F2B544", 14, True),
    ProdutoDemo("caes", "camas", "camas-almofadas", "Cama Retangular Ortopédica G", "Casa Pet", "239.90", None, "cama", "#17375E", 9, False),
    ProdutoDemo("caes", "camas", "casinhas-tocas", "Casinha Plástica Pequena", "Casa Pet", "199.90", None, "cama", "#7B6BB3", 11, False),
    ProdutoDemo("gatos", "racoes", "racao-seca", "Ração Gatos Castrados Salmão 10kg", "Miau Mix", "179.90", '159.90', "saco", "#4A90D9", 28, True),
    ProdutoDemo("gatos", "racoes", "racao-filhotes", "Ração Filhotes Frango 3kg", "Miau Mix", "74.90", None, "saco", "#F2B544", 31, False),
    ProdutoDemo("gatos", "racoes", "racao-seca", "Ração Gatos Adultos Peixes 10kg", "Miau Mix", "169.90", None, "saco", "#2E9CA6", 20, False),
    ProdutoDemo("gatos", "racoes", "racao-umida", "Sachê Atum ao Molho 85g", "Focinho Feliz", "3.90", None, "lata", "#D8688C", 200, False),
    ProdutoDemo("gatos", "racoes", "racao-senior", "Ração Sênior 7+ 3kg", "Natu Pet", "84.90", '74.90', "saco", "#4F9D69", 17, False),
    ProdutoDemo("gatos", "petiscos", "bifinhos-cremosos", "Petisco Cremoso Atum 4un", "Miau Mix", "12.90", None, "caixa", "#4A90D9", 90, False),
    ProdutoDemo("gatos", "petiscos", "biscoitos", "Biscoito Crocante Frango 60g", "Miau Mix", "9.90", None, "caixa", "#F2B544", 85, False),
    ProdutoDemo("gatos", "petiscos", "ervas-catnip", "Erva-de-Gato Natural 30g", "Natu Pet", "14.90", None, "frasco", "#4F9D69", 50, False),
    ProdutoDemo("gatos", "brinquedos", "interativos-exercicio", "Varinha com Penas", "Bicho Chic", "22.90", None, "bola", "#D8688C", 46, False),
    ProdutoDemo("gatos", "brinquedos", "pelucias", "Ratinho de Pelúcia com Catnip", "Bicho Chic", "14.90", None, "bola", "#7B6BB3", 75, False),
    ProdutoDemo("gatos", "brinquedos", "arranhadores", "Arranhador Torre 3 Andares", "Pata Feliz", "229.90", '199.90', "caixa", "#9A6B3F", 8, True),
    ProdutoDemo("gatos", "higiene", "tapetes-areias", "Areia Higiênica Grãos Finos 4kg", "Pipi Clean", "24.90", '19.90', "saco", "#F2B544", 150, True),
    ProdutoDemo("gatos", "higiene", "tapetes-areias", "Areia Sílica Perfumada 3,8kg", "Pipi Clean", "39.90", None, "saco", "#2E9CA6", 64, False),
    ProdutoDemo("gatos", "higiene", "shampoos-condicionadores", "Shampoo a Seco Gatos 150ml", "Banho Bom", "27.90", None, "frasco", "#7B6BB3", 29, False),
    ProdutoDemo("gatos", "farmacia", "antipulgas-carrapatos", "Antipulgas Gatos até 4kg", "VetCare", "79.90", '67.90', "caixa", "#C8453B", 21, False),
    ProdutoDemo("gatos", "farmacia", "suplementos-vitaminas", "Pasta Maltes para Bolas de Pelo 30g", "VetCare", "32.90", None, "frasco", "#4F9D69", 34, False),
    ProdutoDemo("gatos", "coleiras", "coleiras-simples", "Coleira com Guizo", "Pata Feliz", "17.90", None, "coleira", "#D8688C", 58, False),
    ProdutoDemo("gatos", "comedouros", "bebedouros-fontes", "Fonte Bebedouro 2L", "Casa Pet", "189.90", '159.90', "pote", "#4A90D9", 12, False),
    ProdutoDemo("gatos", "transporte", "caixas-transporte", "Caixa de Transporte M", "Casa Pet", "129.90", None, "caixa", "#17375E", 16, False),
    ProdutoDemo("gatos", "comedouros", "comedouros-potes", "Comedouro Duplo Cerâmica", "Casa Pet", "54.90", None, "pote", "#D8688C", 20, False),
    ProdutoDemo("gatos", "camas", "casinhas-tocas", "Cama Iglu Pelúcia", "Casa Pet", "119.90", None, "cama", "#D8688C", 13, False),
    ProdutoDemo("gatos", "camas", "camas-almofadas", "Almofada Cobertor Soft", "Casa Pet", "89.90", '74.90', "cama", "#4A90D9", 23, False),
    ProdutoDemo("passaros", "racoes", "racao-seca", "Mistura de Sementes Calopsita 500g", "Asa Leve", "14.90", None, "saco", "#F2B544", 52, False),
    ProdutoDemo("passaros", "racoes", "racao-seca", "Ração Extrusada Papagaio 600g", "Asa Leve", "38.90", '32.90', "saco", "#4F9D69", 26, False),
    ProdutoDemo("passaros", "brinquedos", "interativos-exercicio", "Balanço com Sino", "Asa Leve", "16.90", None, "bola", "#D96C4A", 37, False),
    ProdutoDemo("passaros", "comedouros", "bebedouros-fontes", "Bebedouro Automático 120ml", "Asa Leve", "12.90", None, "pote", "#2E9CA6", 44, False),
    ProdutoDemo("peixes", "racoes", "racao-seca", "Ração Flocos Tropicais 100g", "Aqua Vida", "12.90", None, "frasco", "#D96C4A", 70, False),
    ProdutoDemo("peixes", "racoes", "racao-seca", "Ração Granulada Bettas 30g", "Aqua Vida", "15.90", '12.90', "frasco", "#4A90D9", 66, False),
    ProdutoDemo("peixes", "farmacia", "tratamento-agua", "Condicionador de Água 120ml", "Aqua Vida", "21.90", None, "frasco", "#2E9CA6", 41, False),
    ProdutoDemo("peixes", "farmacia", "tratamento-agua", "Kit Teste de Qualidade da Água", "Aqua Vida", "59.90", None, "caixa", "#7B6BB3", 18, False),
    ProdutoDemo("roedores", "racoes", "racao-seca", "Ração Hamster e Gerbil 500g", "ZooMix", "16.90", None, "saco", "#9A6B3F", 48, False),
    ProdutoDemo("roedores", "racoes", "racao-seca", "Feno Natural Coelhos e Porquinhos 500g", "ZooMix", "18.90", None, "saco", "#4F9D69", 39, False),
    ProdutoDemo("roedores", "brinquedos", "cordas-mordedores", "Mordedor de Madeira", "ZooMix", "9.90", None, "osso", "#D96C4A", 62, False),
    ProdutoDemo("roedores", "brinquedos", "interativos-exercicio", "Roda de Exercício Silenciosa", "ZooMix", "39.90", '34.90', "bola", "#17375E", 21, False),
]
