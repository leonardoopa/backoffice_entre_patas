import logging

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from backoffice.services.perfis import PERFIS, Perfil

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Cria ou atualiza os perfis de acesso (grupos) do backoffice. Pode rodar quantas vezes quiser."

    def handle(self, *args, **options):
        for perfil in PERFIS:
            grupo, criado = Group.objects.get_or_create(name=perfil.nome)
            permissoes = self._permissoes(perfil)
            grupo.permissions.set(permissoes)
            logger.info("perfil_sincronizado perfil=%s criado=%s permissoes=%d", perfil.nome, criado, len(permissoes))
            self.stdout.write(f"{perfil.nome}: {len(permissoes)} permissões")

    @staticmethod
    def _permissoes(perfil: Perfil) -> list[Permission]:
        app = Permission.objects.filter(content_type__app_label="backoffice")
        if perfil.todas_do_app:
            consulta = app
        else:
            consulta = app.filter(codename__in=perfil.permissoes)
        permissoes = list(consulta)
        if perfil.gerencia_usuarios:
            permissoes += list(Permission.objects.filter(content_type__app_label="auth", content_type__model__in=["user", "group"]))
        return permissoes
