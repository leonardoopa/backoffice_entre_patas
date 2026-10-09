import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.utils import timezone

from backoffice.models import ChaveApi

logger = logging.getLogger(__name__)

TAMANHO_PREFIXO = 8
INTERVALO_REGISTRO_USO = timedelta(minutes=1)


def _hash(chave: str) -> str:
    return hashlib.sha256(chave.encode()).hexdigest()


def gerar_chave(nome: str, escopo: str) -> tuple[ChaveApi, str]:
    """Cria a chave e devolve o texto completo, que só existe neste momento."""
    prefixo = secrets.token_hex(TAMANHO_PREFIXO // 2)
    chave = f"{prefixo}.{secrets.token_urlsafe(32)}"
    registro = ChaveApi.objects.create(nome=nome, prefixo=prefixo, hash_chave=_hash(chave), escopo=escopo)
    logger.info("chave_api_criada chave=%s escopo=%s", registro.pk, escopo)
    return registro, chave


def validar_chave(chave: str) -> ChaveApi | None:
    prefixo, _, _ = chave.partition(".")
    registro = ChaveApi.objects.filter(prefixo=prefixo, ativa=True).first()
    if registro is None or not hmac.compare_digest(registro.hash_chave, _hash(chave)):
        return None
    agora = timezone.now()
    if registro.ultimo_uso_em is None or agora - registro.ultimo_uso_em > INTERVALO_REGISTRO_USO:
        ChaveApi.objects.filter(pk=registro.pk).update(ultimo_uso_em=agora)
    return registro
