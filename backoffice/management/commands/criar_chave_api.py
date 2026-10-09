from django.core.management.base import BaseCommand

from backoffice.models import ChaveApi
from backoffice.services.chaves_api import gerar_chave


class Command(BaseCommand):
    help = "Cria uma chave de API e mostra o valor uma única vez."

    def add_arguments(self, parser):
        parser.add_argument("nome")
        parser.add_argument("escopo", choices=ChaveApi.Escopo.values)

    def handle(self, *args, nome, escopo, **options):
        _, chave = gerar_chave(nome, escopo)
        self.stdout.write(self.style.WARNING("Guarde esta chave agora. Ela não será exibida de novo:"))
        self.stdout.write(chave)
