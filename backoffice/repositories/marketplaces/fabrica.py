from .contratos import AdaptadorCanal
from .simulado import AdaptadorSimulado


def adaptadores_padrao(simulados: bool) -> dict[str, AdaptadorCanal]:
    if not simulados:
        return {}
    adaptador = AdaptadorSimulado()
    return {"mercado_livre": adaptador, "amazon": adaptador}
