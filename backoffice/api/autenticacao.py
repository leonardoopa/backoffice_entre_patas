import logging
from functools import wraps

from django.http import JsonResponse

from backoffice.services.chaves_api import validar_chave

logger = logging.getLogger(__name__)


def _extrair_chave(request) -> str:
    cabecalho = request.headers.get("Authorization", "")
    esquema, _, valor = cabecalho.partition(" ")
    return valor.strip() if esquema.lower() == "bearer" else ""


def exige_escopo(*escopos: str):
    def decorador(view):
        @wraps(view)
        def envolvida(request, *args, **kwargs):
            chave = validar_chave(_extrair_chave(request))
            if chave is None:
                logger.warning("api_chave_invalida caminho=%s", request.path)
                return JsonResponse({"erro": "Chave de API ausente ou inválida."}, status=401)
            if chave.escopo not in escopos:
                logger.warning("api_escopo_negado chave=%s caminho=%s", chave.pk, request.path)
                return JsonResponse({"erro": "Esta chave não tem permissão para esta operação."}, status=403)
            request.chave_api = chave
            return view(request, *args, **kwargs)
        return envolvida
    return decorador
