import json
from datetime import date

import pytest

import db
import preferencias
import run
from pipeline import dedup, ranking
from pipeline.filtro import Filtro
from sources.base import Job

PREFS = preferencias.carregar()


def J(titulo, empresa="Banco X", local="Rio de Janeiro, RJ", fonte="Gupy", modalidade="", **kw):
    i = kw.pop("id", None) or f"{fonte}:{abs(hash((titulo, empresa, local, fonte))) % 10**8}"
    return Job(id=i, fonte=fonte, titulo=titulo, empresa=empresa, local=local, modalidade=modalidade, **kw)


@pytest.mark.parametrize("job,ok", [
    (J("Analista de Fundos Júnior"), True),
    (J("Economista"), True),                                                   # sem "analista": incluir não é obrigatório
    (J("Analista de FP&A Jr", empresa="Varejo SA", local="São Paulo, SP"), True),
    (J("Analista de Inteligência de Mercado", local="São Paulo, São Paulo"), True),
    (J("Analista de Risco de Mercado Pleno"), False),                          # pleno
    (J("Senior Economist"), False),
    (J("Investment Manager"), False),                                           # manager = gerente
    (J("Estagiário de Research"), False),
    (J("Analista de Fundos Jr", local="Curitiba, PR", modalidade="presencial"), False),
    (J("Analista de Fundos Jr", local="", modalidade="remoto"), True),          # remoto de qualquer lugar
    (J("Analista de Investimentos", local="Niterói, Rio de Janeiro"), True),
    (J("Analista de Marketing Jr"), False),                                     # "market" não pega marketing
    (J("Vendedor Externo"), False),
    (J("Analista de Fundos", senioridade="estágio"), False),                    # tipo da Gupy
    (J("Analista de Operações Financeiras", senioridade="PJ"), True),           # PJ passa; a /triagem marca
    (J("Concurso X - MG", local="Nacional", fonte="PCI Concursos", extra={"cat": "PUBLICO"}), True),
])
def test_filtro_yaml(job, ok):
    assert Filtro(PREFS).avaliar(job)[0] is ok


def test_dedup_prefere_a_fonte_original():
    li = J("Analista de Fundos Júnior (Asset)", "BANCO DAYCOVAL", "São Paulo, SP", fonte="LinkedIn", id="li1")
    gp = J("Analista de Fundos Júnior (Asset)", "Banco Daycoval", "São Paulo, São Paulo", fonte="Gupy", id="gp1")
    gd = J("Analista de Fundos Junior - Asset", "daycoval", "São Paulo", fonte="Glassdoor", id="gd1")
    outra = J("Analista de Fundos Júnior (Asset)", "Banco Daycoval", "Rio de Janeiro, RJ", fonte="Gupy", id="gp2")
    unicas, dups = dedup.deduplicar([li, gd, gp, outra])
    assert {j.id for j in unicas} == {"gp1", "gp2"}, "cidade diferente = vaga diferente"
    assert dups == {"li1": "gp1", "gd1": "gp1"}


def _codificador_falso(textos):
    """Vetor 2D: 'macro'/'econom' puxa para o eixo do perfil; o resto fica ortogonal."""
    out = []
    for t in textos:
        tl = t.lower()
        a = 1.0 if ("macro" in tl or "econom" in tl) else 0.2
        n = (a * a + 1) ** 0.5
        out.append([a / n, 1 / n])
    return out


def test_ranking_ordena_e_aplica_bonus():
    rj = J("Economista Júnior", local="Rio de Janeiro, RJ")
    sp = J("Economista Júnior", local="São Paulo, SP")
    outro = J("Analista de Tesouraria", local="São Paulo, SP")
    res = ranking.pontuar([outro, sp, rj], "perfil macro", PREFS, codificar=_codificador_falso)
    assert [j for _, j in res] == [rj, sp, outro]
    assert res[0][0] - res[1][0] == pytest.approx(ranking.BONUS_LOCAL_PREFERIDO)


def test_pipeline_filtra_deduplica_e_gera_top(tmp_path, monkeypatch):
    conn = db.conectar(tmp_path / "p.db")
    monkeypatch.setattr(run, "DATA_DIR", tmp_path)
    monkeypatch.setattr(run, "TOP_N", 2)
    monkeypatch.setattr(ranking, "pontuar", lambda jobs, perfil, prefs: [(90 - i, j) for i, j in enumerate(jobs)])
    hoje = date.today().isoformat()
    jobs = [J("Economista Júnior", fonte="Gupy", id="g1", descricao="macro"),
            J("Economista Júnior", fonte="LinkedIn", id="123"),                # duplicata da g1
            J("Analista de Fundos Jr", id="g2"), J("Analista Sênior de Fundos", id="g3"),
            J("Analista de Crédito Jr", id="g4")]
    db.upsert_vagas(conn, jobs)
    for j in jobs:
        db.atualizar_pipeline(conn, j.id, rodada=hoje)
    db.salvar_triagens(conn, [{"id": "g4", "nota": 70, "trilha": "credito_risco"}])  # já triada: não repete
    run.filtrar_e_deduplicar(conn, PREFS, hoje)
    linhas = {r["id"]: r for r in conn.execute("SELECT id, filtro_ok, duplicata_de FROM vagas")}
    assert linhas["g3"]["filtro_ok"] == 0 and linhas["123"]["duplicata_de"] == "g1"
    run.verificar_abertas(conn, hoje)  # Gupy listada hoje = aberta
    run.ranquear(conn, PREFS, hoje)
    top = [json.loads(l) for l in (tmp_path / f"vagas_{hoje}.jsonl").read_text("utf-8").splitlines()]
    assert [t["id"] for t in top] == ["g1", "g2"]
    assert top[0]["descricao"] == "macro" and "score_pre" in top[0]


@pytest.mark.parametrize("titulo,ok", [
    ("Assesor de Investimentos (Rio de janeiro e São Paulo)", False),
    ("Consultor Comercial de Crédito Imobiliário", False),
    ("Sales Executive Middle Market (Rio de Janeiro)", False),
    ("Analista de Controladoria III (Planejamento Financeiro)", False),
    ("Analista Administrativo Financeiro (Contas a Pagar)", False),
    ("Consultor de planejamento financeiro", False),
    ("Analista de Consultoria Econômica", True),      # consultoria segue valendo
    ("Analista de Investimentos I", True),
])
def test_exclusoes_de_vendas_e_nivel(titulo, ok):
    assert Filtro(PREFS).avaliar(J(titulo))[0] is ok


def test_descricoes_por_fonte(fixture_txt):
    from sources import descricoes
    pags = {"https://v/1": '<div class="job-tab-content job-description__text texto">Atividades:<br>conciliar</div>',
            "https://c/1": '<script type="application/ld+json">{"@type":"JobPosting","description":"<p>Fundos</p>"}'
                           '</script>'}
    jobs = [J("A", fonte="Vagas.com.br", url="https://v/1"), J("B", fonte="Catho", url="https://c/1"),
            J("C", fonte="Glassdoor", url="https://g/1")]
    feitas = descricoes.completar(jobs, buscar=lambda u, **k: pags[u], dormir=lambda s: None)
    assert feitas == {"Vagas.com.br": 1, "Catho": 1}
    assert jobs[0].descricao == "Atividades:\nconciliar" and jobs[1].descricao == "Fundos" and not jobs[2].descricao
