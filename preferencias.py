"""Leitura do config/preferencias.yaml (usado pelo pipeline diário; o monitor de 3h não depende dele)."""
from pathlib import Path

BASE = Path(__file__).resolve().parent
PREFS_PATH = BASE / "config" / "preferencias.yaml"
PERFIL_PATH = BASE / "docs" / "perfil.md"


def carregar(path=PREFS_PATH):
    import yaml  # só no venv; mantém o monitor de 3h livre de dependências externas
    with open(path, encoding="utf-8") as f:
        prefs = yaml.safe_load(f)
    obrig = ["locais", "modalidade", "incluir", "excluir", "termos", "trilhas", "watchlist", "limiares", "execucao"]
    faltando = [k for k in obrig if k not in prefs]
    if faltando:
        raise ValueError(f"preferencias.yaml sem as chaves: {', '.join(faltando)}")
    return prefs
