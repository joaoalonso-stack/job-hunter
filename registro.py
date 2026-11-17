"""Log em arquivo para as execuções agendadas: o pythonw não tem console, então sem isto as mensagens
(bloqueios, erros de fonte) se perdem."""
import sys
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"


class _Tee:
    def __init__(self, *destinos):
        self.destinos = [d for d in destinos if d is not None]

    def write(self, texto):
        for d in self.destinos:
            d.write(texto)
            d.flush()
        return len(texto)

    def flush(self):
        for d in self.destinos:
            d.flush()


def manter_acordado():
    """Pede ao Windows para não suspender por inatividade enquanto o processo roda (a rodada de 13/11 parou
    2 h no meio por causa do Modern Standby). Não impede a suspensão ao fechar a tampa. Vale até o fim do processo."""
    if sys.platform != "win32":
        return False
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    return bool(ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED))


def configurar(nome, log_dir=None):
    """Duplica stdout/stderr para logs/<nome>_AAAA-MM-DD.log, mantendo o console quando existir."""
    log_dir = Path(log_dir or LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    arquivo = open(log_dir / f"{nome}_{datetime.now():%Y-%m-%d}.log", "a", encoding="utf-8")
    arquivo.write(f"\n===== {datetime.now():%d/%m/%Y %H:%M:%S} =====\n")
    sys.stdout = _Tee(sys.__stdout__, arquivo)
    sys.stderr = _Tee(sys.__stderr__, arquivo)
    return arquivo
