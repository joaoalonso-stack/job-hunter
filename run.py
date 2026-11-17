"""Pipeline diário do job hunter (agendado para as 8h).

coleta -> filtro duro (YAML) -> dedup fuzzy -> descrições -> ranking por embeddings -> top 60 em
data/vagas_AAAA-MM-DD.jsonl -> /triagem (Claude Code) -> página HTML + planilha -> top 5 no celular.

Uso:
  python run.py                  # tudo
  python run.py --sem-coleta     # reaproveita o que já está no banco (útil para refazer ranking/relatórios)
  python run.py --sem-triagem    # para antes de chamar o Claude
  python run.py --so-relatorios  # só regera a página e a planilha
"""
import json
import sys
import time
import traceback
from datetime import date, timedelta

import db
import preferencias
import registro
from pipeline import abertas, dedup, ranking
from pipeline.filtro import Filtro
from sources import descricoes, gupy, linkedin_guest, portais, publico

TOP_N = 60
DATA_DIR = db.BASE / "data"


def etapa(conn, nome, func, *args, tentativas=2, **kw):
    """Roda uma etapa com retry e backoff, registrando duração e resultado no banco e no log."""
    inicio = db.agora()
    for n in range(1, tentativas + 1):
        t0 = time.time()
        try:
            res = func(*args, **kw)
            detalhe = res if isinstance(res, str) else ""
            print(f"[{nome}] ok em {time.time() - t0:.0f}s {detalhe}")
            db.registrar_execucao(conn, nome, inicio, True, detalhe)
            return res
        except Exception as e:
            print(f"[{nome}] falhou (tentativa {n}/{tentativas}): {e}")
            traceback.print_exc()
            if n == tentativas:
                db.registrar_execucao(conn, nome, inicio, False, repr(e)[:500])
                return None
            time.sleep(30 * n)


def coletar(conn, prefs, hoje):
    """Junta as fontes. Uma fonte que falha não derruba as outras."""
    termos = list(dict.fromkeys(prefs["termos"] + portais.TERMOS))
    fontes = [
        ("publico", lambda: publico.coletar()),
        ("gupy", lambda: gupy.coletar(termos, watchlist=prefs["watchlist"].get("gupy", []),
                                      janela_dias=prefs["execucao"].get("janela_gupy_dias", 60))),
        ("portais", lambda: portais.coletar(termos=portais.TERMOS, incluir_gupy=False)),
        ("linkedin", lambda: linkedin_guest.coletar()),
    ]
    total, resumo = {}, []
    for nome, f in fontes:
        try:
            jobs = f()
        except Exception as e:
            print(f"  fonte {nome} falhou: {e}")
            resumo.append(f"{nome}=erro")
            continue
        total.update({j.id: j for j in jobs})
        resumo.append(f"{nome}={len(jobs)}")
    db.upsert_vagas(conn, total.values())
    for vid in total:
        db.atualizar_pipeline(conn, vid, rodada=hoje)
    conn.commit()
    return " ".join(resumo) + f" | total={len(total)}"


def filtrar_e_deduplicar(conn, prefs, hoje):
    janela = (date.today() - timedelta(days=prefs["execucao"]["janela_publicacao_dias"])).isoformat()
    vagas = db.carregar_vagas(conn, "ultima_vez >= ? AND fonte NOT LIKE 'historico:%'", (janela,))
    f = Filtro(prefs)
    aprovadas = []
    for j in vagas:
        ok, motivo = f.avaliar(j)
        db.atualizar_pipeline(conn, j.id, filtro_ok=int(ok), motivo_filtro=motivo)
        if ok:
            aprovadas.append(j)
    unicas, dups = dedup.deduplicar(aprovadas)
    for j in aprovadas:
        db.atualizar_pipeline(conn, j.id, duplicata_de=dups.get(j.id))
    conn.commit()
    return f"{len(vagas)} na janela, {len(aprovadas)} passam no filtro, {len(unicas)} únicas"


def candidatas(conn):
    """Aprovadas, não duplicadas, confirmadas abertas e ainda sem triagem, vistas na janela de publicação."""
    return db.carregar_vagas(conn, "filtro_ok=1 AND duplicata_de IS NULL AND aberta=1"
                                   " AND id NOT IN (SELECT vaga_id FROM triagens) AND rodada >= ?",
                             ((date.today() - timedelta(days=7)).isoformat(),))


def verificar_abertas(conn, hoje):
    """Confere se cada vaga ativa (inclusive as já triadas) ainda aceita candidaturas; uma vez por dia."""
    onde = ("filtro_ok=1 AND duplicata_de IS NULL AND COALESCE(aberta, 1)=1 AND COALESCE(verificada_em, '') < ?"
            " AND fonte NOT LIKE 'historico:%'")
    jobs = db.carregar_vagas(conn, onde, (hoje,))
    visto = {r["id"]: (r["ultima_vez"] or "")[:10] for r in conn.execute("SELECT id, ultima_vez FROM vagas")}
    res = abertas.verificar(jobs, visto, hoje)
    db.upsert_vagas(conn, [j for j, _, _ in res])  # datas, prazo e descrição lidos na página da vaga
    n = {"abertas": 0, "encerradas": 0, "sem confirmação": 0}
    for j, ok, motivo in res:
        if ok is None:
            n["sem confirmação"] += 1
            continue
        db.atualizar_pipeline(conn, j.id, aberta=int(ok), verificada_em=hoje, situacao=motivo)
        n["abertas" if ok else "encerradas"] += 1
    conn.commit()
    return f"{len(jobs)} conferidas: " + ", ".join(f"{k}={v}" for k, v in n.items())


def completar_descricoes(conn):
    jobs = [j for j in candidatas(conn) if not j.descricao]
    feitas = descricoes.completar(jobs)
    db.upsert_vagas(conn, [j for j in jobs if j.descricao])
    return "descrições: " + (", ".join(f"{f}={n}" for f, n in feitas.items()) or "nenhuma pendente")


def ranquear(conn, prefs, hoje):
    jobs = candidatas(conn)
    perfil = preferencias.PERFIL_PATH.read_text("utf-8")
    ranqueadas = ranking.pontuar(jobs, perfil, prefs)
    for score, j in ranqueadas:
        db.atualizar_pipeline(conn, j.id, score_pre=score)
    conn.commit()
    top = ranqueadas[:TOP_N]
    DATA_DIR.mkdir(exist_ok=True)
    caminho = DATA_DIR / f"vagas_{hoje}.jsonl"
    with caminho.open("w", encoding="utf-8") as f:
        for score, j in top:
            d = {k: v for k, v in j.to_dict().items() if k != "extra"}
            d["descricao"] = (d["descricao"] or "")[:3500]
            d["score_pre"] = score
            d["tipo_gupy"] = j.extra.get("tipo_gupy", "")
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    return f"{len(jobs)} candidatas, top {len(top)} em {caminho.name}"


RELATORIOS = db.BASE / "relatorios"


def triar(conn, hoje):
    import triagem
    arq = DATA_DIR / f"vagas_{hoje}.jsonl"
    if not arq.exists() or not arq.read_text("utf-8").strip():
        return "nada para triar hoje"
    return triagem.rodar(arq, conn=conn)


def importar_status(conn, prefs, hoje):
    from saidas import dados, planilha, status_import
    n_html = status_import.importar(conn)
    n_xlsx = planilha.importar_edicoes(conn, RELATORIOS / "vagas.xlsx", dados.linhas(conn, prefs, hoje))
    return f"{n_html} status da página, {n_xlsx} edições da planilha"


def gerar_relatorios(conn, prefs, hoje):
    from saidas import dados, pagina, planilha
    linhas = dados.linhas(conn, prefs, hoje)
    pagina.gerar(linhas, prefs, RELATORIOS / "vagas.html", hoje)
    salvo = planilha.gerar(conn, linhas, prefs, RELATORIOS / "vagas.xlsx", hoje)
    return f"{len(linhas)} vagas; {sum(l['hoje'] for l in linhas)} hoje; planilha em {salvo.name}"


def avisar_top(conn, prefs, hoje, n=5):
    """Top 5 do dia no celular (mais qualquer uma >= limiar urgente), só acima da nota mínima. Sem triagem, não avisa."""
    import notify
    from saidas import dados
    do_dia = [l for l in dados.linhas(conn, prefs, hoje) if l["hoje"] and l["aba"] == "ativa"]
    triadas = [l for l in do_dia if l["nota"] is not None]
    if triadas:
        minimo = prefs["limiares"].get("minimo_alerta", 40)  # dia fraco: manda menos de 5 em vez de lixo
        ordem = sorted((l for l in triadas if l["nota"] >= minimo), key=lambda l: -l["nota"])
        escolhidas = ordem[:n] + [l for l in ordem[n:] if l["nota"] >= prefs["limiares"]["urgente"]]
    else:  # triagem falhou: a nota prévia deixa passar vendas e call center; as vagas são triadas e avisadas amanhã
        return "0 alertas: triagem indisponível hoje"
    ja = db.ja_vistas(conn, ["top:" + l["id"] for l in escolhidas])
    novas = [l for l in escolhidas if "top:" + l["id"] not in ja]
    for l in novas:
        nota = f"{l['nota']}" if l["nota"] is not None else f"pré {round(l['score_pre'] or 0)} (sem triagem)"
        msg = {"topic": notify.NTFY_TOPIC, "title": f"[{nota}] {l['cargo']}"[:250],
               "message": f"{l['empresa']} · {l['local']}" + (f"\n{l['encaixe']}" if l["encaixe"] else ""),
               "click": l["url"], "tags": ["dart"],
               "priority": 5 if (l["nota"] or 0) >= prefs["limiares"]["urgente"] else 4,
               "actions": [{"action": "view", "label": "Candidatar", "url": l["url"]}]}
        try:
            notify.enviar(msg)
            db.marcar_vistas(conn, ["top:" + l["id"]])
            time.sleep(2)
        except Exception as e:
            print(f"ntfy falhou para {l['id']}: {e}")
    return f"{len(novas)} alertas do top do dia"


def main(argv=sys.argv):
    hoje = date.today().isoformat()
    conn = db.conectar()
    db.migrar_legado(conn)
    prefs = preferencias.carregar()
    etapa(conn, "importar_status", importar_status, conn, prefs, hoje, tentativas=1)
    if "--so-relatorios" not in argv:
        if "--sem-coleta" not in argv:
            etapa(conn, "coleta", coletar, conn, prefs, hoje, tentativas=1)
        etapa(conn, "filtro_dedup", filtrar_e_deduplicar, conn, prefs, hoje)
        etapa(conn, "abertas", verificar_abertas, conn, hoje, tentativas=1)
        etapa(conn, "descricoes", completar_descricoes, conn, tentativas=1)
        etapa(conn, "ranking", ranquear, conn, prefs, hoje)
        if "--sem-triagem" not in argv:
            # se o Claude falhar, a página sai com a nota prévia e as vagas ficam para a próxima triagem
            etapa(conn, "triagem", triar, conn, hoje)
    etapa(conn, "relatorios", gerar_relatorios, conn, prefs, hoje)
    if "--so-relatorios" not in argv and "--sem-aviso" not in argv:
        etapa(conn, "aviso_top", avisar_top, conn, prefs, hoje, tentativas=1)
    return conn


if __name__ == "__main__":
    registro.configurar("diario")
    registro.manter_acordado()
    main()
