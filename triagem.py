"""Roda a /triagem pelo Claude Code em modo automático (claude -p, com a assinatura do usuário) e grava as notas
no SQLite. A nota final = nota_base dada pelo Claude x peso da trilha no preferencias.yaml.

Uso:
  python triagem.py rodar [data/vagas_AAAA-MM-DD.jsonl]
  python triagem.py importar data/triagem_AAAA-MM-DD.json
"""
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import db
import preferencias

BASE = Path(__file__).resolve().parent
TIMEOUT_S = 40 * 60


def claude_exe():
    """Usa o claude do PATH, se houver; senão o binário que vem com a extensão do VS Code (a versão no nome da
    pasta muda a cada atualização, por isso o glob)."""
    from shutil import which
    if which("claude"):
        return which("claude")
    achados = sorted(glob.glob(os.path.expanduser(
        "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe")))
    if not achados:
        raise FileNotFoundError("Claude Code não encontrado (nem no PATH, nem na extensão do VS Code)")
    return achados[-1]


def extrair_json(texto):
    m = re.search(r"```json\s*(\[.*?\])\s*```", texto, re.S) or re.search(r"(\[\s*\{.*\}\s*\])", texto, re.S)
    if not m:
        raise ValueError("a resposta da /triagem não trouxe um array JSON")
    return json.loads(m.group(1))


def validar(itens, ids_esperados, prefs):
    """Confere o formato e calcula a nota final ponderada pela trilha."""
    pesos = prefs["trilhas"]
    saida = []
    for t in itens:
        if t.get("id") not in ids_esperados:
            continue
        trilha = t.get("trilha") if t.get("trilha") in pesos else "outro"
        base = max(0, min(100, int(t.get("nota_base", t.get("nota", 0)))))
        saida.append({"id": t["id"], "nota_base": base, "nota": round(base * pesos[trilha]), "trilha": trilha,
                      "encaixe": str(t.get("encaixe", "")).strip(),
                      "falta": [str(x) for x in t.get("falta") or []],
                      "red_flags": [str(x) for x in t.get("red_flags") or []]})
    return saida


def importar(caminho_json, caminho_jsonl=None, conn=None):
    conn = conn or db.conectar()
    itens = json.loads(Path(caminho_json).read_text("utf-8"))
    if caminho_jsonl:
        ids = {json.loads(l)["id"] for l in Path(caminho_jsonl).read_text("utf-8").splitlines() if l.strip()}
    else:
        ids = {t.get("id") for t in itens}
    validos = validar(itens, ids, preferencias.carregar())
    db.salvar_triagens(conn, validos)
    return validos


def rodar(caminho_jsonl, conn=None, executar=subprocess.run):
    """Chama `claude -p "/triagem <arquivo> --so-json"`; só a ferramenta Read é liberada."""
    caminho_jsonl = Path(caminho_jsonl)
    rel = caminho_jsonl.resolve().relative_to(BASE).as_posix()
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # garante a assinatura, nunca a API paga
    proc = executar([claude_exe(), "-p", f"/triagem {rel} --so-json", "--output-format", "json",
                     "--allowedTools", "Read"], cwd=BASE, capture_output=True, text=True, encoding="utf-8",
                    timeout=TIMEOUT_S, env=env, stdin=subprocess.DEVNULL,  # sem console na tarefa agendada
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        resposta = json.loads(proc.stdout)
    except ValueError:
        resposta = {}
    if proc.returncode != 0 or resposta.get("is_error"):
        motivo = {k: resposta.get(k) for k in ("subtype", "num_turns", "result", "errors") if resposta.get(k)}
        raise RuntimeError(f"claude -p saiu com código {proc.returncode}: {motivo or (proc.stderr or proc.stdout)[:500]}")
    itens = extrair_json(resposta.get("result", ""))
    destino = caminho_jsonl.with_name(caminho_jsonl.name.replace("vagas_", "triagem_").replace(".jsonl", ".json"))
    destino.write_text(json.dumps(itens, ensure_ascii=False, indent=1), "utf-8")
    validos = importar(destino, caminho_jsonl, conn)
    return f"{len(validos)} vagas triadas ({destino.name})"


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "importar":
        print(f"{len(importar(sys.argv[2]))} triagens gravadas no banco")
    elif len(sys.argv) >= 2 and sys.argv[1] == "rodar":
        alvo = sys.argv[2] if len(sys.argv) > 2 else sorted((BASE / "data").glob("vagas_*.jsonl"))[-1]
        print(rodar(alvo))
    else:
        print(__doc__)
