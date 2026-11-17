"""Alertas no celular via ntfy.sh (gratuito)."""
import json
import os
import time
import urllib.request
from pathlib import Path

import db

# O tópico do ntfy funciona como senha (quem sabe o nome lê e envia alertas), por isso fica fora do git:
# variável de ambiente NTFY_TOPIC ou o arquivo config/ntfy_topic.txt (modelo em config/ntfy_topic.exemplo.txt).
_ARQ_TOPICO = Path(__file__).resolve().parent / "config" / "ntfy_topic.txt"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC") or (_ARQ_TOPICO.read_text("utf-8").strip() if _ARQ_TOPICO.exists() else "")
# Teto por rodada só para não estourar o limite do ntfy.sh; o excedente fica na fila, não é descartado.
MAX_POR_RODADA = 50
ROTULO = {"MACRO": "⭐ MACRO", "JR": "Jr", "FIN": "Finanças", "PUBLICO": "🏛 Público", "OUTRAS": "Afins"}


def payload(job):
    """Resumo serializável da vaga para a fila e o envio."""
    return {"id": job.id, "cat": job.extra.get("cat", "FIN"), "titulo": job.titulo, "empresa": job.empresa,
            "local": job.local, "fonte": job.fonte, "url": job.url}


def montar(p):
    return {
        "topic": NTFY_TOPIC,
        "title": f"[{ROTULO.get(p['cat'], p['cat'])}] {p['titulo']}"[:250],
        "message": f"{p['empresa']} · {p['local']}" + (f" · via {p['fonte']}" if p.get("fonte") else ""),
        "click": p["url"],
        "priority": 5 if p["cat"] == "MACRO" else 4 if p["cat"] in ("JR", "PUBLICO") else 3,
        "tags": ["briefcase"],
        "actions": [{"action": "view", "label": "Abrir vaga", "url": p["url"]}],
    }


def enviar(msg):
    if not msg.get("topic"):
        raise RuntimeError("tópico do ntfy não configurado (config/ntfy_topic.txt ou variável NTFY_TOPIC)")
    req = urllib.request.Request("https://ntfy.sh", data=json.dumps(msg).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def enviar_fila(conn, novos_payloads, envio=None, pausa=2):
    """Põe os alertas novos na fila e envia tudo o que estiver pendente. O que falhar ou passar do limite
    fica na fila para a próxima rodada; nenhuma vaga aderente é descartada sem virar alerta."""
    envio = envio or enviar
    db.fila_adicionar(conn, novos_payloads)
    enviadas = 0
    for p in db.fila_listar(conn):
        if enviadas >= MAX_POR_RODADA:
            break
        try:
            envio(montar(p))
        except Exception:
            continue
        db.fila_remover(conn, p["id"])
        enviadas += 1
        time.sleep(pausa)
    restantes = len(db.fila_listar(conn))
    print(f"{enviadas} alertas enviados, {restantes} na fila")
    return enviadas
