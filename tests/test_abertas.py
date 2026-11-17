from datetime import date, timedelta

import db
import run
from pipeline import abertas
from sources.base import Job

HOJE = date.today().isoformat()
ONTEM = (date.today() - timedelta(days=1)).isoformat()
SEMANA = (date.today() - timedelta(days=7)).isoformat()
FUTURO = (date.today() + timedelta(days=30)).isoformat()


def J(fonte, i="1", **kw):
    return Job(id=i, fonte=fonte, titulo="Analista de Fundos Jr", empresa="Banco X", url=f"https://x/{i}", **kw)


def pag(cod, texto=""):
    return lambda url: (cod, texto)


def test_prazo_vencido_encerra_qualquer_fonte():
    assert abertas.checar(J("Gupy", prazo=ONTEM), HOJE, HOJE)[0] is False


def test_listagens_que_so_mostram_vagas_abertas():
    assert abertas.checar(J("Gupy"), HOJE, HOJE)[0] is True
    assert abertas.checar(J("Glassdoor"), HOJE, ONTEM)[0] is True
    ok, motivo = abertas.checar(J("Glassdoor"), HOJE, SEMANA)
    assert ok is False and "sumiu" in motivo


def test_linkedin_encerrada_aberta_e_bloqueio():
    fechada = '<span class="closed-job closed-job__flavor">Não aceita mais candidaturas</span>'
    assert abertas.checar(J("LinkedIn", "4474411344"), HOJE, HOJE, pag(200, fechada))[0] is False
    j = J("LinkedIn", "4471832216")
    ok, _ = abertas.checar(j, HOJE, HOJE, pag(200, '<div class="show-more-less-html__markup">Requisitos</div>'))
    assert ok is True and j.descricao == "Requisitos", "aproveita a página para preencher a descrição"
    assert abertas.checar(J("LinkedIn", "9"), HOJE, HOJE, pag(404))[0] is False
    assert abertas.checar(J("LinkedIn", "9"), HOJE, HOJE, pag(429))[0] is None, "bloqueio não é encerramento"


def _ld(**campos):
    import json
    return f'<script type="application/ld+json">{json.dumps({"@type": "JobPosting", **campos})}</script>'


def test_vagas_e_catho_pela_pagina():
    j = J("Vagas.com.br")
    ok, _ = abertas.checar(j, HOJE, HOJE, pag(200, _ld(datePosted="2026-11-12", validThrough=FUTURO, description="x")))
    assert ok is True and j.publicada == "2026-11-12" and j.prazo == FUTURO
    assert abertas.checar(J("Catho"), HOJE, HOJE, pag(200, _ld(validThrough=ONTEM)))[0] is False
    assert abertas.checar(J("Catho"), HOJE, HOJE, pag(410))[0] is False


def test_fonte_que_bloqueia_para_de_ser_consultada():
    chamadas = []

    def buscar(url):
        chamadas.append(url)
        return 403, ""

    res = abertas.verificar([J("Catho", "1"), J("Catho", "2"), J("Gupy", "3")], {"3": HOJE}, HOJE,
                            buscar=buscar, dormir=lambda s: None)
    assert len(chamadas) == 1
    assert [(j.id, ok) for j, ok, _ in res] == [("1", None), ("3", True)]


def test_etapa_arquiva_as_encerradas(tmp_path, monkeypatch):
    conn = db.conectar(tmp_path / "a.db")
    jobs = [J("Gupy", "g1", prazo=ONTEM), J("Gupy", "g2", prazo=FUTURO)]
    db.upsert_vagas(conn, jobs)
    for j in jobs:
        db.atualizar_pipeline(conn, j.id, filtro_ok=1, rodada=HOJE)
    conn.commit()
    msg = run.verificar_abertas(conn, HOJE)
    assert "abertas=1" in msg and "encerradas=1" in msg
    r = {x["id"]: x for x in conn.execute("SELECT id, aberta, situacao FROM vagas")}
    assert r["g1"]["aberta"] == 0 and "prazo" in r["g1"]["situacao"] and r["g2"]["aberta"] == 1
    assert [j.id for j in run.candidatas(conn)] == ["g2"], "encerrada não vai para o ranking"
    assert "0 conferidas" in run.verificar_abertas(conn, HOJE), "uma vez por dia"
