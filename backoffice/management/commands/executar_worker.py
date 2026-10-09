import logging
import os
import time

from django.core.management.base import BaseCommand

from backoffice.integracoes.base import adaptadores_padrao
from backoffice.services.estoque import expirar_reservas
from backoffice.services.sincronizacao import processar_fila

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Processa a fila de sincronização com os marketplaces e libera reservas vencidas."

    def add_arguments(self, parser):
        parser.add_argument("--uma-vez", action="store_true", help="Roda um ciclo e sai.")
        parser.add_argument("--intervalo", type=int, default=30, help="Segundos entre ciclos.")

    def handle(self, *args, uma_vez, intervalo, **options):
        adaptadores = adaptadores_padrao(simulados=os.environ.get("MARKETPLACES_SIMULADOS") == "1")
        logger.info("worker_iniciado canais=%s", ",".join(adaptadores) or "nenhum")
        while True:
            try:
                liberadas = expirar_reservas()
                resultado = processar_fila(adaptadores)
                if liberadas or resultado.concluidos or resultado.falhas:
                    logger.info(
                        "worker_ciclo reservas_liberadas=%d sync_ok=%d sync_falhas=%d",
                        liberadas, resultado.concluidos, resultado.falhas,
                    )
            except Exception:  # noqa: BLE001 — o worker não pode morrer por um ciclo ruim
                logger.exception("worker_ciclo_falhou")
            if uma_vez:
                return
            time.sleep(intervalo)
