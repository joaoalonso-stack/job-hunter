"""Monta as linhas dos relatórios (página HTML e planilha) a partir do SQLite.

Abas:
- hoje:      as vagas enviadas à triagem de hoje (data/vagas_AAAA-MM-DD.jsonl);
- ativa:     aprovadas no filtro, não duplicadas, vistas nos últimos dias, com prazo em aberto e não descartadas;
- arquivada: descartadas por você, com prazo vencido ou que sumiram das fontes.
"""
import json
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]  # raiz do projeto

SQL = """
SELECT v.id, v.fonte, v.titulo, v.empresa, v.local, v.modalidade, v.senioridade, v.publicada, v.prazo, v.url,
       v.descricao, v.ultima_vez, v.primeira_vez, v.score_pre, v.motivo_filtro, v.filtro_ok, v.duplicata_de,
       v.aberta, v.verificada_em, v.situacao,
       t.nota, t.nota_base, t.trilha, t.encaixe, t.falta, t.red_flags, t.triada_em,
       s.status, s.data_aplicacao, s.observacoes, s.atualizado_em
FROM vagas v
LEFT JOIN triagens t ON t.vaga_id = v.id
LEFT JOIN status s ON s.vaga_id = v.id
WHERE v.fonte NOT LIKE 'historico:%'
  AND ((v.filtro_ok = 1 AND v.duplicata_de IS NULL) OR t.vaga_id IS NOT NULL OR COALESCE(s.status, '') <> '')
"""


def ids_de_hoje(hoje, data_dir=None):
    arq = Path(data_dir or BASE / "data") / f"vagas_{hoje}.jsonl"
    if not arq.exists():
        return []
    return [json.loads(l)["id"] for l in arq.read_text("utf-8").splitlines() if l.strip()]


def linhas(conn, prefs, hoje=None, data_dir=None):
    hoje = hoje or date.today().isoformat()
    janela = (date.fromisoformat(hoje) - timedelta(days=prefs["execucao"]["janela_publicacao_dias"])).isoformat()
    do_dia = ids_de_hoje(hoje, data_dir)
    ordem_dia = {i: n for n, i in enumerate(do_dia)}
    out = []
    for r in conn.execute(SQL):
        status = r["status"] or ""
        prazo = r["prazo"] or ""
        vencida = bool(prazo) and prazo < hoje
        sumiu = (r["ultima_vez"] or "")[:10] < janela
        encerrada = r["aberta"] == 0
        if status == "descartei" or ((vencida or encerrada) and status != "apliquei") or (sumiu and not status):
            aba = "arquivada"
        else:
            aba = "ativa"
        dias_prazo = (date.fromisoformat(prazo) - date.fromisoformat(hoje)).days if prazo else None
        out.append({
            # "Hoje" = enviadas à triagem hoje (arquivo do dia) ou triadas hoje numa rodada anterior do mesmo dia
            "id": r["id"], "hoje": r["id"] in ordem_dia or (r["triada_em"] or "")[:10] == hoje,
            "ordem_hoje": ordem_dia.get(r["id"]), "aba": aba,
            "nota": r["nota"], "nota_base": r["nota_base"], "score_pre": r["score_pre"],
            "cargo": r["titulo"], "empresa": r["empresa"], "trilha": r["trilha"] or "", "local": r["local"],
            "modalidade": r["modalidade"] or "", "fonte": r["fonte"], "senioridade": r["senioridade"] or "",
            "publicada": (r["publicada"] or "")[:10], "prazo": prazo, "dias_prazo": dias_prazo,
            "urgente_prazo": dias_prazo is not None and 0 <= dias_prazo <= prefs["limiares"]["prazo_dias"],
            "url": r["url"], "encaixe": r["encaixe"] or "", "falta": json.loads(r["falta"] or "[]"),
            "red_flags": json.loads(r["red_flags"] or "[]"), "motivo_filtro": r["motivo_filtro"] or "",
            "descricao": (r["descricao"] or "")[:900], "visto_em": (r["primeira_vez"] or "")[:10],
            "status": status, "data_aplicacao": r["data_aplicacao"] or "", "observacoes": r["observacoes"] or "",
            "status_em": r["atualizado_em"] or "",
            "aberta": r["aberta"], "verificada_em": r["verificada_em"] or "", "situacao": r["situacao"] or "",
        })
    # Vagas do dia primeiro na ordem da nota; sem nota, pela nota prévia dos embeddings.
    out.sort(key=lambda l: (-(l["nota"] if l["nota"] is not None else -1), -(l["score_pre"] or 0)))
    return out
