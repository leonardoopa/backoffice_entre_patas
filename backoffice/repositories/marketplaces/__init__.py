from .contratos import AdaptadorCanal, ErroSincronizacao
from .fabrica import adaptadores_padrao
from .simulado import AdaptadorSimulado

__all__ = ["AdaptadorCanal", "AdaptadorSimulado", "ErroSincronizacao", "adaptadores_padrao"]
