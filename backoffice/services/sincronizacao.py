import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from backoffice.integracoes.base import AdaptadorCanal
from backoffice.models import FilaSync, ProdutoCanal

logger = logging.getLogger(__name__)

MAX_TENTATIVAS = 8
ESPERA_MAXIMA_MINUTOS = 360
TEMPO_LIMITE_MINUTOS = 15


@dataclass
class ResultadoFila:
    concluidos: int = 0
    falhas: int = 0
    esgotados: int = 0


def _espera(tentativas: int) -> timedelta:
    return timedelta(minutes=min(2 ** tentativas, ESPERA_MAXIMA_MINUTOS))


def _reservar_lote(canais: list[str], limite: int, agora) -> list[FilaSync]:
    with transaction.atomic():
        itens = list(
            FilaSync.objects.select_for_update(skip_locked=True)
            .select_related("canal", "produto")
            .filter(
                status__in=[FilaSync.Status.PENDENTE, FilaSync.Status.PROCESSANDO],
                proxima_tentativa_em__lte=agora, canal__codigo__in=canais,
            )
            .order_by("proxima_tentativa_em", "id")[:limite]
        )
        for item in itens:
            item.status = FilaSync.Status.PROCESSANDO
            item.proxima_tentativa_em = agora + timedelta(minutes=TEMPO_LIMITE_MINUTOS)
            item.save(update_fields=["status", "proxima_tentativa_em"])
    return itens


def _registrar_sucesso(item: FilaSync, agora) -> None:
    item.status, item.concluida_em, item.ultimo_erro = FilaSync.Status.CONCLUIDA, agora, ""
    item.save(update_fields=["status", "concluida_em", "ultimo_erro"])
    ProdutoCanal.objects.filter(produto=item.produto, canal=item.canal).update(
        status_sync=ProdutoCanal.StatusSync.SINCRONIZADO, erro_sync="", sincronizado_em=agora,
    )


def _registrar_falha(item: FilaSync, erro: Exception, agora) -> bool:
    item.tentativas += 1
    item.ultimo_erro = str(erro)[:1000]
    esgotou = item.tentativas >= MAX_TENTATIVAS
    item.status = FilaSync.Status.ERRO if esgotou else FilaSync.Status.PENDENTE
    item.proxima_tentativa_em = agora + _espera(item.tentativas)
    item.save(update_fields=["tentativas", "ultimo_erro", "status", "proxima_tentativa_em"])
    ProdutoCanal.objects.filter(produto=item.produto, canal=item.canal).update(
        status_sync=ProdutoCanal.StatusSync.ERRO, erro_sync=item.ultimo_erro,
    )
    return esgotou


def processar_fila(adaptadores: dict[str, AdaptadorCanal], limite: int = 50, agora=None) -> ResultadoFila:
    """Envia os itens vencidos da fila. Falhou: tenta de novo com espera crescente até esgotar as tentativas."""
    resultado = ResultadoFila()
    if not adaptadores:
        return resultado
    agora = agora or timezone.now()
    for item in _reservar_lote(list(adaptadores), limite, agora):
        try:
            adaptadores[item.canal.codigo].sincronizar(item)
        except Exception as erro:  # noqa: BLE001 — qualquer falha do canal deve ser repetida
            esgotou = _registrar_falha(item, erro, agora)
            resultado.falhas += 1
            resultado.esgotados += int(esgotou)
            logger.warning(
                "sync_falhou canal=%s tipo=%s sku=%s tentativa=%d esgotou=%s erro=%s",
                item.canal.codigo, item.tipo, item.produto.sku, item.tentativas, esgotou, erro,
            )
        else:
            _registrar_sucesso(item, agora)
            resultado.concluidos += 1
    return resultado


def tentar_novamente(itens) -> int:
    return FilaSync.objects.filter(pk__in=[i.pk for i in itens], status=FilaSync.Status.ERRO).update(
        status=FilaSync.Status.PENDENTE, tentativas=0, proxima_tentativa_em=timezone.now(),
    )
