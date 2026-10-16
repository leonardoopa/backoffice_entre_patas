import threading
from contextlib import contextmanager

from django.db import connection

_estado = threading.local()


def definir_usuario(nome: str) -> None:
    """Informa ao banco quem está agindo; os gatilhos de auditoria leem `app.usuario`."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.usuario', %s, false)", [nome])
    _estado.definido = bool(nome)


def limpar_usuario() -> None:
    if getattr(_estado, "definido", False):
        definir_usuario("")


@contextmanager
def com_usuario(nome: str):
    definir_usuario(nome)
    try:
        yield
    finally:
        definir_usuario("")
