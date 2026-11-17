"""Importa no SQLite os status exportados pela página (botão "Exportar status (JSON)"). O arquivo baixado vai para a
pasta Downloads; a cada execução os arquivos status_vagas_*.json de lá são lidos e movidos para data/importados/."""
import json
import shutil
from pathlib import Path

import db

DOWNLOADS = Path.home() / "Downloads"


def importar(conn, pastas=(DOWNLOADS,), destino=None):
    destino = Path(destino or db.BASE / "data" / "importados")
    n = 0
    for pasta in pastas:
        for arq in sorted(Path(pasta).glob("status_vagas_*.json")):
            try:
                itens = json.loads(arq.read_text("utf-8"))
            except (OSError, ValueError) as e:
                print(f"status: não consegui ler {arq.name}: {e}")
                continue
            for it in itens:
                if it.get("id") and it.get("status", "") in db.STATUS_VALIDOS:
                    n += db.salvar_status(conn, it["id"], status=it.get("status", ""), quando=it.get("quando"))
            destino.mkdir(parents=True, exist_ok=True)
            shutil.move(str(arq), destino / arq.name)
    return n
